"""Projeção em memória do status dos pedidos (data-model.md §5).

Roda inteiramente no event loop do FastAPI (sem threads), portanto não usa locks.
"""

from __future__ import annotations

import bisect
import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from uuid import UUID

from pydantic import BaseModel, Field

from contratos import (
    STATUS_POR_TIPO,
    EventoCriado,
    EventoPedido,
    Localidade,
    StatusPedido,
)


class PedidoNaoEncontradaError(Exception):
    """Pedido inexistente ou com todos os eventos fora da janela de retenção."""


class Resultado(Enum):
    """Desfecho da aplicação de um evento na projeção."""

    APLICADO = auto()
    DUPLICADO = auto()
    EXPIRADO = auto()


class Pedido(BaseModel):
    """Status atual de um pedido."""

    pedido_id: str
    status: StatusPedido
    cliente: str | None = None
    valor: float | None = None
    origem: Localidade | None = None
    destino: Localidade | None = None
    peso_kg: float | None = None
    descricao: str | None = None
    tentativas_entrega: int = Field(ge=0)
    ultima_atualizacao: datetime
    total_eventos: int = Field(ge=1)
    correlation_id: str


class PaginaPedidos(BaseModel):
    """Página da listagem de pedidos."""

    itens: list[Pedido]
    page: int
    size: int
    total: int


class Resumo(BaseModel):
    """Indicadores agregados."""

    total_pedidos: int
    total_eventos: int
    pedidos_por_status: dict[str, int] = Field(
        description="Todas as chaves de StatusPedido presentes (0 quando vazio)"
    )
    eventos_duplicados_descartados: int
    eventos_enviados_dlq: int
    atualizado_em: datetime


def _chave(evento: EventoPedido) -> tuple[datetime, str]:
    return evento.occurred_at, str(evento.event_id)


@dataclass
class _EstadoPedido:
    pedido_id: str
    eventos: list[EventoPedido] = field(default_factory=list)
    ids: set[UUID] = field(default_factory=set)
    visao: Pedido | None = None

    def inserir(self, evento: EventoPedido) -> None:
        bisect.insort(self.eventos, evento, key=_chave)
        self.ids.add(evento.event_id)
        self.visao = None

    def remover(self, event_id: UUID) -> bool:
        if event_id not in self.ids:
            return False
        self.ids.discard(event_id)
        self.eventos = [e for e in self.eventos if e.event_id != event_id]
        self.visao = None
        return True

    def montar(self) -> Pedido:
        if self.visao is None:
            ultimo = self.eventos[-1]
            criado = next((e for e in self.eventos if isinstance(e, EventoCriado)), None)
            tentativas = [
                t for e in self.eventos if (t := getattr(e.payload, "tentativa", None)) is not None
            ]
            self.visao = Pedido(
                pedido_id=self.pedido_id,
                status=STATUS_POR_TIPO[ultimo.event_type],
                cliente=criado.payload.cliente if criado else None,
                valor=criado.payload.valor if criado else None,
                origem=criado.payload.origem if criado else None,
                destino=criado.payload.destino if criado else None,
                peso_kg=criado.payload.peso_kg if criado else None,
                descricao=criado.payload.descricao if criado else None,
                tentativas_entrega=max(tentativas, default=0),
                ultima_atualizacao=ultimo.occurred_at,
                total_eventos=len(self.eventos),
                correlation_id=str(self.eventos[0].correlation_id),
            )
        return self.visao


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class Projecao:
    """Visão em memória dos pedidos, limitada à janela de retenção (FR-022a)."""

    def __init__(self, retencao: timedelta, agora: Callable[[], datetime] = _agora_utc) -> None:
        self.retencao = retencao
        self._agora = agora
        self._pedidos: dict[str, _EstadoPedido] = {}
        self._vencimentos: list[tuple[datetime, str, UUID]] = []
        self._total_eventos = 0
        self.duplicados = 0
        self.enviados_dlq = 0

    def _limite(self, agora: datetime | None = None) -> datetime:
        return (agora or self._agora()) - self.retencao

    def aplicar(self, evento: EventoPedido) -> Resultado:
        """Insere o evento; ignora duplicados e eventos já fora da janela de retenção."""
        if evento.occurred_at < self._limite():
            return Resultado.EXPIRADO
        estado = self._pedidos.get(evento.pedido_id)
        if estado is None:
            estado = self._pedidos[evento.pedido_id] = _EstadoPedido(evento.pedido_id)
        elif evento.event_id in estado.ids:
            self.duplicados += 1
            return Resultado.DUPLICADO
        estado.inserir(evento)
        heapq.heappush(self._vencimentos, (evento.occurred_at, evento.pedido_id, evento.event_id))
        self._total_eventos += 1
        return Resultado.APLICADO

    def registrar_dlq(self) -> None:
        """Contabiliza uma mensagem enviada ao DLQ."""
        self.enviados_dlq += 1

    def expirar(self, agora: datetime | None = None) -> int:
        """Remove eventos fora da janela e pedidos que ficaram vazias; retorna quantos saíram."""
        limite = self._limite(agora)
        removidos = 0
        while self._vencimentos and self._vencimentos[0][0] < limite:
            _, pedido_id, event_id = heapq.heappop(self._vencimentos)
            estado = self._pedidos.get(pedido_id)
            if estado is None or not estado.remover(event_id):
                continue
            removidos += 1
            self._total_eventos -= 1
            if not estado.eventos:
                del self._pedidos[pedido_id]
        return removidos

    def _estado(self, pedido_id: str) -> _EstadoPedido:
        estado = self._pedidos.get(pedido_id)
        if estado is None:
            raise PedidoNaoEncontradaError(pedido_id)
        return estado

    def obter_pedido(self, pedido_id: str) -> Pedido:
        """Status atual do pedido."""
        return self._estado(pedido_id).montar()

    def historico(self, pedido_id: str) -> list[EventoPedido]:
        """Eventos do pedido em ordem cronológica, sem duplicatas."""
        return list(self._estado(pedido_id).eventos)

    def listar(self, status: StatusPedido | None, page: int, size: int) -> PaginaPedidos:
        """Pedidos filtradas por status, mais recentes primeiro, paginadas."""
        visoes = (e.montar() for e in self._pedidos.values())
        filtradas = [c for c in visoes if status is None or c.status is status]
        filtradas.sort(key=lambda c: (c.ultima_atualizacao, c.pedido_id), reverse=True)
        inicio = (page - 1) * size
        return PaginaPedidos(
            itens=filtradas[inicio : inicio + size], page=page, size=size, total=len(filtradas)
        )

    def resumo(self) -> Resumo:
        """Contagens agregadas da projeção."""
        por_status = {s.value: 0 for s in StatusPedido}
        for estado in self._pedidos.values():
            por_status[estado.montar().status.value] += 1
        return Resumo(
            total_pedidos=len(self._pedidos),
            total_eventos=self._total_eventos,
            pedidos_por_status=por_status,
            eventos_duplicados_descartados=self.duplicados,
            eventos_enviados_dlq=self.enviados_dlq,
            atualizado_em=self._agora(),
        )
