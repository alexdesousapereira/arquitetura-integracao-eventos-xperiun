from __future__ import annotations

import itertools
import random
from datetime import UTC, datetime, timedelta

from contratos import StatusPedido, TipoEvento
from contratos.status import STATUS_POR_TIPO
from simulador.dominio.gerador import Gerador
from simulador.dominio.pedido import PedidoSimulado

AGORA = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _jornada(seed: int, prob_falha: float = 0.15) -> list[TipoEvento]:
    pedido = PedidoSimulado.nova(Gerador(random.Random(seed)), prob_falha=prob_falha)
    tipos: list[TipoEvento] = []
    agora = AGORA
    while (evento := pedido.proximo_evento(agora)) is not None:
        tipos.append(evento.event_type)
        agora += timedelta(seconds=1)
    return tipos


def test_sequencia_feliz_sem_falhas() -> None:
    assert _jornada(seed=1, prob_falha=0) == [
        TipoEvento.CRIADO,
        TipoEvento.PAGAMENTO_APROVADO,
        TipoEvento.ENVIADO,
    ]


def test_recusa_encerra_sem_envio() -> None:
    assert _jornada(seed=7, prob_falha=1) == [TipoEvento.CRIADO, TipoEvento.PAGAMENTO_RECUSADO]


def test_occurred_at_estritamente_crescente_mesmo_com_relogio_parado() -> None:
    pedido = PedidoSimulado.nova(Gerador(random.Random(3)), prob_falha=0.3)
    ocorrencias = []
    while (evento := pedido.proximo_evento(AGORA)) is not None:
        ocorrencias.append(evento.occurred_at)
    assert all(a < b for a, b in itertools.pairwise(ocorrencias))


def test_correlation_id_e_pedido_id_constantes() -> None:
    pedido = PedidoSimulado.nova(Gerador(random.Random(4)), prob_falha=0.3)
    eventos = []
    while (evento := pedido.proximo_evento(AGORA)) is not None:
        eventos.append(evento)
    assert len({e.correlation_id for e in eventos}) == 1
    assert len({e.pedido_id for e in eventos}) == 1
    assert len({e.event_id for e in eventos}) == len(eventos)


def test_status_atual_acompanha_ultimo_evento() -> None:
    pedido = PedidoSimulado.nova(Gerador(random.Random(5)), prob_falha=0.0)
    assert pedido.status is None
    evento = pedido.proximo_evento(AGORA)
    assert evento is not None
    assert pedido.status is StatusPedido.CRIADO
    assert STATUS_POR_TIPO[evento.event_type] is pedido.status


def test_deterministico_com_mesma_seed() -> None:
    def gerar() -> list[str]:
        pedido = PedidoSimulado.nova(Gerador(random.Random(42)), prob_falha=0.2)
        saida = []
        while (evento := pedido.proximo_evento(AGORA)) is not None:
            saida.append(evento.model_dump_json())
        return saida

    assert gerar() == gerar()
