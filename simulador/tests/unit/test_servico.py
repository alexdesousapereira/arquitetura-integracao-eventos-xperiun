from __future__ import annotations

import itertools
import random
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contratos import EventoPedido
from simulador.config import ConfigSimulador
from simulador.dominio.gerador import Gerador
from simulador.servico import Simulacao


class EscritorMemoria:
    def __init__(self) -> None:
        self.eventos: list[EventoPedido] = []

    def gravar(self, evento: EventoPedido) -> Path:
        self.eventos.append(evento)
        return Path(f"{evento.event_id}.json")


class RelogioFalso:
    def __init__(self) -> None:
        self.monotonico = 0.0
        self.inicio = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

    def agora(self) -> datetime:
        return self.inicio + timedelta(seconds=self.monotonico)

    def mono(self) -> float:
        return self.monotonico

    def dormir(self, segundos: float) -> None:
        self.monotonico += segundos


def _simulacao(
    escritor: EscritorMemoria,
    relogio: RelogioFalso,
    parar: threading.Event | None = None,
    **cfg: int | bool,
) -> Simulacao:
    config = ConfigSimulador(seed=10, **cfg)  # type: ignore[arg-type]
    return Simulacao(
        config,
        escritor,
        gerador=Gerador(random.Random(10)),
        agora=relogio.agora,
        monotonico=relogio.mono,
        dormir=relogio.dormir,
        parar=parar or threading.Event(),
    )


def test_respeita_max_eventos() -> None:
    escritor = EscritorMemoria()
    resumo = _simulacao(escritor, RelogioFalso(), pedidos=5, max_eventos=37).executar()
    assert resumo.eventos_gerados == 37
    assert len(escritor.eventos) == 37


def test_padrao_gera_dez_eventos_e_encerra() -> None:
    escritor = EscritorMemoria()
    resumo = _simulacao(escritor, RelogioFalso()).executar()
    assert resumo.eventos_gerados == 10
    assert len(escritor.eventos) == 10


def test_respeita_duracao() -> None:
    relogio = RelogioFalso()
    _simulacao(
        EscritorMemoria(), relogio, pedidos=3, intervalo_ms=500, duracao_s=10, max_eventos=1000
    ).executar()
    assert 10 <= relogio.monotonico < 11


def test_mantem_n_pedidos_ativas_e_repoe_concluidos() -> None:
    escritor = EscritorMemoria()
    simulacao = _simulacao(escritor, RelogioFalso(), pedidos=4, max_eventos=400)
    resumo = simulacao.executar()
    assert simulacao.pedidos_ativos == 4
    assert resumo.pedidos_concluidos > 4
    assert len({e.pedido_id for e in escritor.eventos}) > 4


def test_eventos_de_pedidos_distintas_intercalados() -> None:
    escritor = EscritorMemoria()
    _simulacao(escritor, RelogioFalso(), pedidos=10, max_eventos=60).executar()
    primeiras = [e.pedido_id for e in escritor.eventos[:20]]
    trocas = sum(1 for a, b in itertools.pairwise(primeiras) if a != b)
    assert trocas >= 5


def test_parada_solicitada_encerra_apos_ciclo() -> None:
    parar = threading.Event()
    relogio = RelogioFalso()
    original = relogio.dormir

    def dormir_e_parar(segundos: float) -> None:
        original(segundos)
        if relogio.monotonico >= 2:
            parar.set()

    relogio.dormir = dormir_e_parar  # type: ignore[method-assign]
    escritor = EscritorMemoria()
    _simulacao(escritor, relogio, parar, pedidos=3, intervalo_ms=500).executar()
    assert parar.is_set()
    assert 0 < len(escritor.eventos) < 20


def test_continuo_ignora_limites_ate_a_parada() -> None:
    parar = threading.Event()
    relogio = RelogioFalso()
    original = relogio.dormir

    def dormir_e_parar(segundos: float) -> None:
        original(segundos)
        if relogio.monotonico >= 30:
            parar.set()

    relogio.dormir = dormir_e_parar  # type: ignore[method-assign]
    escritor = EscritorMemoria()
    simulacao = _simulacao(
        escritor, relogio, parar, pedidos=3, intervalo_ms=500, duracao_s=5, continuo=True
    )
    simulacao.executar()
    assert relogio.monotonico >= 30  # ignorou duracao_s=5
    assert len(escritor.eventos) > 10  # ignorou o padrão de 10 eventos


def test_ordem_por_pedido_preservada() -> None:
    escritor = EscritorMemoria()
    _simulacao(escritor, RelogioFalso(), pedidos=6, max_eventos=200).executar()
    por_pedido: dict[str, list[datetime]] = {}
    for evento in escritor.eventos:
        por_pedido.setdefault(evento.pedido_id, []).append(evento.occurred_at)
    for ocorrencias in por_pedido.values():
        assert ocorrencias == sorted(ocorrencias)
