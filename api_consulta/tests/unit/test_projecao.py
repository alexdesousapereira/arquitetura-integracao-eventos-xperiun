from __future__ import annotations

import random
import time
from collections.abc import Callable
from datetime import timedelta

import pytest

from api_consulta.services.projecao import CargaNaoEncontradaError, Projecao, Resultado
from contratos import EventoCarga, StatusCarga, TipoEvento

JANELA = timedelta(minutes=15)


def _projecao(relogio: Callable[[], object]) -> Projecao:
    return Projecao(JANELA, agora=relogio)  # type: ignore[arg-type]


def test_status_reflete_evento_mais_recente(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    eventos = gerar_jornada(1)
    for evento in eventos:
        assert proj.aplicar(evento) is Resultado.APLICADO
    carga = proj.obter_carga(eventos[0].carga_id)
    assert carga.status is StatusCarga.ENTREGUE
    assert carga.total_eventos == len(eventos)
    assert carga.ultima_atualizacao == eventos[-1].occurred_at
    assert carga.origem is not None
    assert carga.peso_kg is not None
    assert carga.tentativas_entrega == 1
    assert carga.correlation_id == str(eventos[0].correlation_id)


def test_historico_ordenado_mesmo_fora_de_ordem(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    eventos = gerar_jornada(2)
    embaralhados = eventos[:]
    random.Random(0).shuffle(embaralhados)
    for evento in embaralhados:
        proj.aplicar(evento)
    assert proj.historico(eventos[0].carga_id) == eventos
    assert proj.obter_carga(eventos[0].carga_id).status is StatusCarga.ENTREGUE


def test_duplicado_descartado(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    evento = gerar_jornada(3)[0]
    assert proj.aplicar(evento) is Resultado.APLICADO
    assert proj.aplicar(evento) is Resultado.DUPLICADO
    assert proj.resumo().eventos_duplicados_descartados == 1
    assert proj.resumo().total_eventos == 1


def test_fora_de_ordem_sem_recebida(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    eventos = gerar_jornada(4)
    entregue = eventos[-1]
    assert entregue.event_type == TipoEvento.ENTREGUE
    proj.aplicar(entregue)
    carga = proj.obter_carga(entregue.carga_id)
    assert carga.status is StatusCarga.ENTREGUE
    assert carga.origem is None
    assert carga.destino is None
    assert carga.peso_kg is None
    assert carga.descricao is None


def test_tentativas_maior_valor(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    eventos = gerar_jornada(5, prob_falha=1.0)
    for evento in eventos:
        proj.aplicar(evento)
    carga = proj.obter_carga(eventos[0].carga_id)
    assert carga.tentativas_entrega == 3
    assert carga.status is StatusCarga.FALHA_ENTREGA


def test_sem_tentativas_e_zero(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    evento = gerar_jornada(6)[0]
    proj.aplicar(evento)
    assert proj.obter_carga(evento.carga_id).tentativas_entrega == 0


def test_carga_inexistente(relogio) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    with pytest.raises(CargaNaoEncontradaError):
        proj.obter_carga("CRG-00000000")
    with pytest.raises(CargaNaoEncontradaError):
        proj.historico("CRG-00000000")


def _carregar(
    proj: Projecao, gerar_jornada, quantidade: int, inicio=None
) -> list[list[EventoCarga]]:  # type: ignore[no-untyped-def]
    jornadas = []
    for seed in range(quantidade):
        kwargs = {"inicio": inicio + timedelta(seconds=seed)} if inicio else {}
        eventos = gerar_jornada(seed + 100, **kwargs)
        corte = 1 + seed % len(eventos)
        for evento in eventos[:corte]:
            proj.aplicar(evento)
        jornadas.append(eventos[:corte])
    return jornadas


def test_listagem_filtra_ordena_e_pagina(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    _carregar(proj, gerar_jornada, 30, inicio=relogio())
    pagina = proj.listar(None, page=1, size=10)
    assert pagina.total == 30
    assert len(pagina.itens) == 10
    datas = [c.ultima_atualizacao for c in pagina.itens]
    assert datas == sorted(datas, reverse=True)
    ultima = proj.listar(None, page=3, size=10)
    assert len(ultima.itens) == 10
    assert proj.listar(None, page=4, size=10).itens == []
    recebidas = proj.listar(StatusCarga.RECEBIDA, page=1, size=500)
    assert recebidas.total >= 1
    assert all(c.status is StatusCarga.RECEBIDA for c in recebidas.itens)


def test_resumo_coerente(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    jornadas = _carregar(proj, gerar_jornada, 20)
    resumo = proj.resumo()
    assert resumo.total_cargas == 20
    assert resumo.total_eventos == sum(len(j) for j in jornadas)
    assert set(resumo.cargas_por_status) == {s.value for s in StatusCarga}
    assert sum(resumo.cargas_por_status.values()) == 20


def test_resumo_vazio_tem_todas_as_chaves(relogio) -> None:  # type: ignore[no-untyped-def]
    resumo = _projecao(relogio).resumo()
    assert resumo.cargas_por_status == {s.value: 0 for s in StatusCarga}
    assert resumo.total_cargas == 0


# ---------------------------------------------------------------- expiração (FR-022a)


def test_evento_ja_expirado_e_ignorado(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    antigo = gerar_jornada(7, inicio=relogio() - timedelta(minutes=16))[0]
    assert proj.aplicar(antigo) is Resultado.EXPIRADO
    assert proj.resumo().total_cargas == 0
    assert proj.resumo().eventos_duplicados_descartados == 0


def test_expirar_remove_eventos_e_recalcula(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    eventos = gerar_jornada(8, inicio=relogio())
    for evento in eventos:
        proj.aplicar(evento)
    carga_id = eventos[0].carga_id
    # avança até que só o último evento continue dentro da janela
    relogio.atual = eventos[-1].occurred_at + JANELA - timedelta(milliseconds=1)
    removidos = proj.expirar()
    assert removidos == len(eventos) - 1
    carga = proj.obter_carga(carga_id)
    assert carga.total_eventos == 1
    assert carga.origem is None  # carga.recebida expirou
    assert carga.status is StatusCarga.ENTREGUE
    assert proj.historico(carga_id) == [eventos[-1]]


def test_carga_sem_eventos_e_removida(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    eventos = gerar_jornada(9, inicio=relogio())
    for evento in eventos:
        proj.aplicar(evento)
    relogio.atual = eventos[-1].occurred_at + JANELA + timedelta(seconds=1)
    assert proj.expirar() == len(eventos)
    with pytest.raises(CargaNaoEncontradaError):
        proj.obter_carga(eventos[0].carga_id)
    resumo = proj.resumo()
    assert resumo.total_cargas == 0
    assert resumo.total_eventos == 0
    assert proj.listar(None, 1, 50).total == 0


def test_expirar_sem_nada_vencido(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    for evento in gerar_jornada(10, inicio=relogio()):
        proj.aplicar(evento)
    assert proj.expirar() == 0


def test_duplicado_de_evento_expirado_nao_conta(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    evento = gerar_jornada(11, inicio=relogio())[0]
    proj.aplicar(evento)
    relogio.avancar(minutes=16)
    proj.expirar()
    assert proj.aplicar(evento) is Resultado.EXPIRADO
    assert proj.resumo().eventos_duplicados_descartados == 0


def test_desempenho_volume_de_simulacao(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    proj = _projecao(relogio)
    base = gerar_jornada(12, inicio=relogio())
    for i in range(500):
        for evento in base[:3]:
            proj.aplicar(
                evento.model_copy(
                    update={
                        "carga_id": f"CRG-{i:08X}",
                        "event_id": f"00000000-0000-4000-8000-{i:06d}{base.index(evento):06d}",
                    }
                )
            )
    inicio = time.perf_counter()
    proj.listar(StatusCarga.EM_TRANSITO, 1, 500)
    proj.listar(None, 2, 100)
    proj.obter_carga("CRG-000000AB")
    proj.resumo()
    assert time.perf_counter() - inicio < 1.0
