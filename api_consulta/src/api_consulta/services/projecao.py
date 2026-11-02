"""Projeção em memória do status das cargas (data-model.md §5).

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
    EventoCarga,
    EventoRecebida,
    Localidade,
    StatusCarga,
)


class CargaNaoEncontradaError(Exception):
    """Carga inexistente ou com todos os eventos fora da janela de retenção."""


class Resultado(Enum):
    """Desfecho da aplicação de um evento na projeção."""

    APLICADO = auto()
    DUPLICADO = auto()
    EXPIRADO = auto()


class Carga(BaseModel):
    """Status atual de uma carga."""

    carga_id: str
    status: StatusCarga
    origem: Localidade | None = None
    destino: Localidade | None = None
    peso_kg: float | None = None
    descricao: str | None = None
    tentativas_entrega: int = Field(ge=0)
    ultima_atualizacao: datetime
    total_eventos: int = Field(ge=1)
    correlation_id: str


class PaginaCargas(BaseModel):
    """Página da listagem de cargas."""

    itens: list[Carga]
    page: int
    size: int
    total: int


class Resumo(BaseModel):
    """Indicadores agregados."""

    total_cargas: int
    total_eventos: int
    cargas_por_status: dict[str, int] = Field(
        description="Todas as chaves de StatusCarga presentes (0 quando vazio)"
    )
    eventos_duplicados_descartados: int
    eventos_enviados_dlq: int
    atualizado_em: datetime


def _chave(evento: EventoCarga) -> tuple[datetime, str]:
    return evento.occurred_at, str(evento.event_id)


@dataclass
class _EstadoCarga:
    carga_id: str
    eventos: list[EventoCarga] = field(default_factory=list)
    ids: set[UUID] = field(default_factory=set)
    visao: Carga | None = None

    def inserir(self, evento: EventoCarga) -> None:
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

    def montar(self) -> Carga:
        if self.visao is None:
            ultimo = self.eventos[-1]
            recebida = next((e for e in self.eventos if isinstance(e, EventoRecebida)), None)
            tentativas = [
                t for e in self.eventos if (t := getattr(e.payload, "tentativa", None)) is not None
            ]
            self.visao = Carga(
                carga_id=self.carga_id,
                status=STATUS_POR_TIPO[ultimo.event_type],
                origem=recebida.payload.origem if recebida else None,
                destino=recebida.payload.destino if recebida else None,
                peso_kg=recebida.payload.peso_kg if recebida else None,
                descricao=recebida.payload.descricao if recebida else None,
                tentativas_entrega=max(tentativas, default=0),
                ultima_atualizacao=ultimo.occurred_at,
                total_eventos=len(self.eventos),
                correlation_id=str(self.eventos[0].correlation_id),
            )
        return self.visao


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class Projecao:
    """Visão em memória das cargas, limitada à janela de retenção (FR-022a)."""

    def __init__(self, retencao: timedelta, agora: Callable[[], datetime] = _agora_utc) -> None:
        self.retencao = retencao
        self._agora = agora
        self._cargas: dict[str, _EstadoCarga] = {}
        self._vencimentos: list[tuple[datetime, str, UUID]] = []
        self._total_eventos = 0
        self.duplicados = 0
        self.enviados_dlq = 0

    def _limite(self, agora: datetime | None = None) -> datetime:
        return (agora or self._agora()) - self.retencao

    def aplicar(self, evento: EventoCarga) -> Resultado:
        """Insere o evento; ignora duplicados e eventos já fora da janela de retenção."""
        if evento.occurred_at < self._limite():
            return Resultado.EXPIRADO
        estado = self._cargas.get(evento.carga_id)
        if estado is None:
            estado = self._cargas[evento.carga_id] = _EstadoCarga(evento.carga_id)
        elif evento.event_id in estado.ids:
            self.duplicados += 1
            return Resultado.DUPLICADO
        estado.inserir(evento)
        heapq.heappush(self._vencimentos, (evento.occurred_at, evento.carga_id, evento.event_id))
        self._total_eventos += 1
        return Resultado.APLICADO

    def registrar_dlq(self) -> None:
        """Contabiliza uma mensagem enviada ao DLQ."""
        self.enviados_dlq += 1

    def expirar(self, agora: datetime | None = None) -> int:
        """Remove eventos fora da janela e cargas que ficaram vazias; retorna quantos saíram."""
        limite = self._limite(agora)
        removidos = 0
        while self._vencimentos and self._vencimentos[0][0] < limite:
            _, carga_id, event_id = heapq.heappop(self._vencimentos)
            estado = self._cargas.get(carga_id)
            if estado is None or not estado.remover(event_id):
                continue
            removidos += 1
            self._total_eventos -= 1
            if not estado.eventos:
                del self._cargas[carga_id]
        return removidos

    def _estado(self, carga_id: str) -> _EstadoCarga:
        estado = self._cargas.get(carga_id)
        if estado is None:
            raise CargaNaoEncontradaError(carga_id)
        return estado

    def obter_carga(self, carga_id: str) -> Carga:
        """Status atual da carga."""
        return self._estado(carga_id).montar()

    def historico(self, carga_id: str) -> list[EventoCarga]:
        """Eventos da carga em ordem cronológica, sem duplicatas."""
        return list(self._estado(carga_id).eventos)

    def listar(self, status: StatusCarga | None, page: int, size: int) -> PaginaCargas:
        """Cargas filtradas por status, mais recentes primeiro, paginadas."""
        visoes = (e.montar() for e in self._cargas.values())
        filtradas = [c for c in visoes if status is None or c.status is status]
        filtradas.sort(key=lambda c: (c.ultima_atualizacao, c.carga_id), reverse=True)
        inicio = (page - 1) * size
        return PaginaCargas(
            itens=filtradas[inicio : inicio + size], page=page, size=size, total=len(filtradas)
        )

    def resumo(self) -> Resumo:
        """Contagens agregadas da projeção."""
        por_status = {s.value: 0 for s in StatusCarga}
        for estado in self._cargas.values():
            por_status[estado.montar().status.value] += 1
        return Resumo(
            total_cargas=len(self._cargas),
            total_eventos=self._total_eventos,
            cargas_por_status=por_status,
            eventos_duplicados_descartados=self.duplicados,
            eventos_enviados_dlq=self.enviados_dlq,
            atualizado_em=self._agora(),
        )
