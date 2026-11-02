"""Loop da simulação: mantém N cargas ativas e grava seus eventos."""

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

from contratos import EventoCarga
from simulador.config import ConfigSimulador
from simulador.dominio.carga import CargaSimulada
from simulador.dominio.gerador import Gerador
from simulador.observabilidade import CARGAS_ATIVAS, EVENTOS_GERADOS

INTERVALO_RESUMO_S = 10.0
FRACAO_POR_CICLO = 10  # a cada ciclo avançam ~1/10 das cargas (mínimo 1)

log = structlog.get_logger()


class Escritor(Protocol):
    """Destino dos eventos gerados."""

    def gravar(self, evento: EventoCarga) -> Path:
        """Persiste o evento e retorna onde ele foi gravado."""
        ...


@dataclass(frozen=True, slots=True)
class Resumo:
    """Totais ao final da simulação."""

    eventos_gerados: int
    cargas_concluidas: int


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
        self._ativas: list[CargaSimulada] = []
        self._eventos = 0
        self._concluidas = 0

    @property
    def cargas_ativas(self) -> int:
        """Quantidade de cargas em andamento."""
        return len(self._ativas)

    def _nova_carga(self) -> CargaSimulada:
        return CargaSimulada.nova(self.gerador, self.config.prob_falha)

    def _limite_atingido(self, inicio: float) -> bool:
        cfg = self.config
        if cfg.continuo:
            return False
        if self._eventos >= cfg.max_eventos:
            return True
        return bool(cfg.duracao_s and self._monotonico() - inicio >= cfg.duracao_s)

    def _ciclo(self, inicio: float) -> None:
        quantidade = max(1, len(self._ativas) // FRACAO_POR_CICLO)
        for indice in self.gerador.rng.sample(range(len(self._ativas)), quantidade):
            if self._limite_atingido(inicio):
                return
            carga = self._ativas[indice]
            evento = carga.proximo_evento(self._agora())
            if evento is not None:
                self.escritor.gravar(evento)
                self._eventos += 1
                EVENTOS_GERADOS.labels(event_type=evento.event_type.value).inc()
                log.debug(
                    "evento_gerado",
                    event_id=str(evento.event_id),
                    carga_id=evento.carga_id,
                    correlation_id=str(evento.correlation_id),
                    event_type=evento.event_type.value,
                )
            if carga.concluida:
                self._concluidas += 1
                self._ativas[indice] = self._nova_carga()

    def executar(self) -> Resumo:
        """Roda a simulação e retorna os totais."""
        self._ativas = [self._nova_carga() for _ in range(self.config.cargas)]
        CARGAS_ATIVAS.set(len(self._ativas))
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
        return Resumo(self._eventos, self._concluidas)

    def _logar_resumo(self, mensagem: str) -> None:
        log.info(
            mensagem,
            eventos_gerados=self._eventos,
            cargas_ativas=len(self._ativas),
            cargas_concluidas=self._concluidas,
        )
