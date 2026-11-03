"""Loop da simulação: mantém N pedidos ativos e grava seus eventos."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import structlog

from contratos import EventoPedido
from simulador.config import ConfigSimulador
from simulador.dominio.gerador import Gerador
from simulador.dominio.pedido import PedidoSimulado
from simulador.observabilidade import EVENTOS_GERADOS, PEDIDOS_ATIVOS

INTERVALO_RESUMO_S = 10.0
FRACAO_POR_CICLO = 10  # a cada ciclo avançam ~1/10 dos pedidos (mínimo 1)

log = structlog.get_logger()


class Escritor(Protocol):
    """Destino dos eventos gerados."""

    def gravar(self, evento: EventoPedido) -> Path:
        """Persiste o evento e retorna onde ele foi gravado."""
        ...


@dataclass(frozen=True, slots=True)
class Resumo:
    """Totais ao final da simulação."""

    eventos_gerados: int
    pedidos_concluidos: int


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class Simulacao:
    """Executa a simulação até a parada, a duração ou o limite de eventos."""

    def __init__(
        self,
        config: ConfigSimulador,
        escritor: Escritor,
        *,
        gerador: Gerador | None = None,
        agora: Callable[[], datetime] = _agora_utc,
        monotonico: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] | None = None,
        parar: threading.Event | None = None,
    ) -> None:
        self.config = config
        self.escritor = escritor
        self.gerador = gerador or Gerador(random.Random(config.seed))  # noqa: S311
        self._agora = agora
        self._monotonico = monotonico
        self.parar = parar or threading.Event()
        self._dormir = dormir or self.parar.wait
        self._ativos: list[PedidoSimulado] = []
        self._eventos = 0
        self._concluidos = 0

    @property
    def pedidos_ativos(self) -> int:
        """Quantidade de pedidos em andamento."""
        return len(self._ativos)

    def _novo_pedido(self) -> PedidoSimulado:
        return PedidoSimulado.nova(self.gerador, self.config.prob_falha)

    def _limite_atingido(self, inicio: float) -> bool:
        cfg = self.config
        if cfg.continuo:
            return False
        if self._eventos >= cfg.max_eventos:
            return True
        return bool(cfg.duracao_s and self._monotonico() - inicio >= cfg.duracao_s)

    def _ciclo(self, inicio: float) -> None:
        quantidade = max(1, len(self._ativos) // FRACAO_POR_CICLO)
        for indice in self.gerador.rng.sample(range(len(self._ativos)), quantidade):
            if self._limite_atingido(inicio):
                return
            pedido = self._ativos[indice]
            evento = pedido.proximo_evento(self._agora())
            if evento is not None:
                self.escritor.gravar(evento)
                self._eventos += 1
                EVENTOS_GERADOS.labels(event_type=evento.event_type.value).inc()
                log.debug(
                    "evento_gerado",
                    event_id=str(evento.event_id),
                    pedido_id=evento.pedido_id,
                    correlation_id=str(evento.correlation_id),
                    event_type=evento.event_type.value,
                )
            if pedido.concluido:
                self._concluidos += 1
                self._ativos[indice] = self._novo_pedido()

    def executar(self) -> Resumo:
        """Roda a simulação e retorna os totais."""
        self._ativos = [self._novo_pedido() for _ in range(self.config.pedidos)]
        PEDIDOS_ATIVOS.set(len(self._ativos))
        inicio = self._monotonico()
        ultimo_resumo = inicio
        log.info("simulacao_iniciada", **self.config.model_dump(mode="json"))
        while not self.parar.is_set() and not self._limite_atingido(inicio):
            self._ciclo(inicio)
            if self._monotonico() - ultimo_resumo >= INTERVALO_RESUMO_S:
                ultimo_resumo = self._monotonico()
                self._logar_resumo("simulacao_resumo")
            if self._limite_atingido(inicio):
                break
            self._dormir(self.config.intervalo_ms / 1000)
        self._logar_resumo("simulacao_encerrada")
        return Resumo(self._eventos, self._concluidos)

    def _logar_resumo(self, mensagem: str) -> None:
        log.info(
            mensagem,
            eventos_gerados=self._eventos,
            pedidos_ativos=len(self._ativos),
            pedidos_concluidos=self._concluidos,
        )
