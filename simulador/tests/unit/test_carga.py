from __future__ import annotations

import itertools
import random
from datetime import UTC, datetime, timedelta

from contratos import StatusCarga, TipoEvento
from contratos.status import STATUS_POR_TIPO
from simulador.dominio.carga import CargaSimulada
from simulador.dominio.gerador import Gerador

AGORA = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _jornada(seed: int, prob_falha: float = 0.15) -> list[TipoEvento]:
    carga = CargaSimulada.nova(Gerador(random.Random(seed)), prob_falha=prob_falha)
    tipos: list[TipoEvento] = []
    agora = AGORA
    while (evento := carga.proximo_evento(agora)) is not None:
        tipos.append(evento.event_type)
        agora += timedelta(seconds=1)
    return tipos


def test_sequencia_feliz_sem_falhas() -> None:
    tipos = _jornada(seed=1, prob_falha=0.0)
    assert tipos[0] == TipoEvento.RECEBIDA
    assert tipos[1] == TipoEvento.SAIU_PARA_TRANSPORTE
    transitos = [t for t in tipos if t == TipoEvento.EM_TRANSITO]
    assert 1 <= len(transitos) <= 5
    assert tipos[2 : 2 + len(transitos)] == transitos
    assert tipos[-2:] == [TipoEvento.SAIU_PARA_ENTREGA, TipoEvento.ENTREGUE]


def test_falha_sempre_gera_tres_tentativas_e_termina() -> None:
    carga = CargaSimulada.nova(Gerador(random.Random(7)), prob_falha=1.0)
    eventos = []
    agora = AGORA
    while (evento := carga.proximo_evento(agora)) is not None:
        eventos.append(evento)
        agora += timedelta(seconds=1)
    saidas = [e for e in eventos if e.event_type == TipoEvento.SAIU_PARA_ENTREGA]
    falhas = [e for e in eventos if e.event_type == TipoEvento.ENTREGA_FALHOU]
    assert [e.payload.tentativa for e in saidas] == [1, 2, 3]  # type: ignore[union-attr]
    assert [e.payload.tentativa for e in falhas] == [1, 2, 3]  # type: ignore[union-attr]
    assert eventos[-1].event_type == TipoEvento.ENTREGA_FALHOU
    assert carga.concluida
    assert carga.proximo_evento(agora) is None


def test_falha_seguida_de_nova_saida_para_entrega() -> None:
    for seed in range(200):
        tipos = _jornada(seed, prob_falha=0.5)
        for i, tipo in enumerate(tipos[:-1]):
            if tipo == TipoEvento.ENTREGA_FALHOU:
                assert tipos[i + 1] == TipoEvento.SAIU_PARA_ENTREGA


def test_occurred_at_estritamente_crescente_mesmo_com_relogio_parado() -> None:
    carga = CargaSimulada.nova(Gerador(random.Random(3)), prob_falha=0.3)
    ocorrencias = []
    while (evento := carga.proximo_evento(AGORA)) is not None:
        ocorrencias.append(evento.occurred_at)
    assert all(a < b for a, b in itertools.pairwise(ocorrencias))


def test_correlation_id_e_carga_id_constantes() -> None:
    carga = CargaSimulada.nova(Gerador(random.Random(4)), prob_falha=0.3)
    eventos = []
    while (evento := carga.proximo_evento(AGORA)) is not None:
        eventos.append(evento)
    assert len({e.correlation_id for e in eventos}) == 1
    assert len({e.carga_id for e in eventos}) == 1
    assert len({e.event_id for e in eventos}) == len(eventos)


def test_status_atual_acompanha_ultimo_evento() -> None:
    carga = CargaSimulada.nova(Gerador(random.Random(5)), prob_falha=0.0)
    assert carga.status is None
    evento = carga.proximo_evento(AGORA)
    assert evento is not None
    assert carga.status is StatusCarga.RECEBIDA
    assert STATUS_POR_TIPO[evento.event_type] is carga.status


def test_deterministico_com_mesma_seed() -> None:
    def gerar() -> list[str]:
        carga = CargaSimulada.nova(Gerador(random.Random(42)), prob_falha=0.2)
        saida = []
        while (evento := carga.proximo_evento(AGORA)) is not None:
            saida.append(evento.model_dump_json())
        return saida

    assert gerar() == gerar()
