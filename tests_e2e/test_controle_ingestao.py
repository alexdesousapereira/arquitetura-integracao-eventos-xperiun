"""US2 ponta a ponta: ingestão de arquivos e operação pela API de controle."""

from __future__ import annotations

import time

import httpx
import pytest

from simulador.adapters.escritor_arquivo import EscritorArquivo
from tests_e2e.conftest import DADOS, GravadorEventos, aguardar, arquivos, end_offsets

pytestmark = pytest.mark.e2e


def _arquivos_status(controle: httpx.Client) -> dict[str, int]:
    resposta: dict[str, int] = controle.get("/api/v1/ingestao").json()["arquivos"]
    return resposta


def test_arquivos_validos_vao_para_backup(
    ingestao_ativa: httpx.Client, gravador: GravadorEventos
) -> None:
    eventos = gravador.gerar(10)
    nomes = {
        f"{e.occurred_at.strftime('%Y%m%dT%H%M%S%f')}Z_{e.carga_id}_{e.event_id}.json"
        for e in eventos
    }
    aguardar(lambda: nomes <= arquivos("backup"), timeout=30)
    assert not nomes & arquivos("eventos")


def test_pausa_retem_arquivos_e_retomada_ingere(
    ingestao_ativa: httpx.Client, gravador: GravadorEventos
) -> None:
    controle = ingestao_ativa
    assert controle.post("/api/v1/ingestao/pausar").status_code == httpx.codes.ACCEPTED
    aguardar(lambda: controle.get("/api/v1/ingestao").json()["estado"] == "PAUSADA", 30)
    gravador.gerar(10)
    time.sleep(20)
    assert _arquivos_status(controle)["pendentes"] >= 10
    assert controle.post("/api/v1/ingestao/retomar").status_code == httpx.codes.ACCEPTED
    aguardar(lambda: _arquivos_status(controle)["pendentes"] == 0, timeout=30)


def test_arquivo_invalido_vai_para_erros(ingestao_ativa: httpx.Client) -> None:
    antes = _arquivos_status(ingestao_ativa)["com_erro"]
    nome = f"invalido-{time.time_ns()}.json"
    (DADOS / "eventos" / nome).write_text("{ quebrado")
    aguardar(lambda: nome in arquivos("erros"), timeout=30)
    status = ingestao_ativa.get("/api/v1/ingestao").json()
    assert status["arquivos"]["com_erro"] == antes + 1
    assert status["estado"] == "ATIVA"
    (DADOS / "erros" / nome).unlink()


def test_reiniciar_nao_republica(ingestao_ativa: httpx.Client, gravador: GravadorEventos) -> None:
    gravador.gerar(5)
    aguardar(lambda: _arquivos_status(ingestao_ativa)["pendentes"] == 0, timeout=30)
    time.sleep(3)
    offsets = end_offsets()
    assert ingestao_ativa.post("/api/v1/ingestao/reiniciar").status_code == httpx.codes.ACCEPTED
    aguardar(lambda: ingestao_ativa.get("/api/v1/ingestao").json()["estado"] == "ATIVA", 60)
    time.sleep(10)
    assert end_offsets() == offsets


def test_mutacao_sem_chave_401(controle: httpx.Client) -> None:
    resposta = httpx.post(f"{controle.base_url}/api/v1/ingestao/pausar")
    assert resposta.status_code == httpx.codes.UNAUTHORIZED
    assert resposta.headers["content-type"].startswith("application/problem+json")


def test_backlog_acumulado_e_processado_apos_retomada(
    ingestao_ativa: httpx.Client, gravador: GravadorEventos
) -> None:
    """Edge case da spec: arquivos acumulados durante a pausa (volume de simulação)."""
    controle = ingestao_ativa
    controle.post("/api/v1/ingestao/pausar").raise_for_status()
    aguardar(lambda: controle.get("/api/v1/ingestao").json()["estado"] == "PAUSADA", 30)
    eventos = gravador.gerar(10)
    assert _arquivos_status(controle)["pendentes"] >= 10
    controle.post("/api/v1/ingestao/retomar").raise_for_status()
    aguardar(lambda: _arquivos_status(controle)["pendentes"] == 0, timeout=30, intervalo=2)
    nomes = {f"{EscritorArquivo.nome_arquivo(e)}" for e in eventos}
    assert nomes <= arquivos("backup")
    assert controle.get("/api/v1/ingestao").json()["estado"] == "ATIVA"
