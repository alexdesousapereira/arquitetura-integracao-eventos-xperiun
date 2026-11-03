from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from contratos import EventoPedido
from simulador.dominio.gerador import Gerador
from simulador.dominio.pedido import PedidoSimulado

AGORA = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class Relogio:
    def __init__(self, inicio: datetime = AGORA) -> None:
        self.atual = inicio

    def __call__(self) -> datetime:
        return self.atual

    def avancar(self, **delta: float) -> None:
        self.atual += timedelta(**delta)


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


def jornada(seed: int, inicio: datetime = AGORA, prob_falha: float = 0.0) -> list[EventoPedido]:
    """Todos os eventos de um pedido simulado, 1 s entre eventos."""
    pedido = PedidoSimulado.nova(Gerador(random.Random(seed)), prob_falha=prob_falha)
    eventos = []
    instante = inicio
    while (evento := pedido.proximo_evento(instante)) is not None:
        eventos.append(evento)
        instante += timedelta(seconds=1)
    return eventos


@pytest.fixture
def gerar_jornada() -> Callable[..., list[EventoPedido]]:
    return jornada
