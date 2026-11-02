from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from controle_ingestao.adapters.connect_client import ConnectErroError, ConnectIndisponivelError
from controle_ingestao.api.dependencias import obter_servico, obter_verificador
from controle_ingestao.config import ConfigControle
from controle_ingestao.main import criar_app
from controle_ingestao.services.ingestao import (
    ContagemArquivos,
    EstadoIngestao,
    IngestaoInexistenteError,
    StatusIngestao,
)

CHAVE = "segredo-teste"
AUTH = {"X-API-Key": CHAVE}


def _st(estado: EstadoIngestao = EstadoIngestao.ATIVA) -> StatusIngestao:
    return StatusIngestao(
        nome="arquivos",
        estado=estado,
        tarefas=[],
        arquivos=ContagemArquivos(pendentes=0, em_backup=0, com_erro=0),
        connect_disponivel=True,
        consultado_em=datetime.now(UTC),
    )


class ServicoFalso:
    def __init__(self) -> None:
        self.erro: Exception | None = None
        self.criado = True

    def _talvez_falhar(self) -> None:
        if self.erro:
            raise self.erro

    async def status(self) -> StatusIngestao:
        self._talvez_falhar()
        return _st()

    async def ativar(self) -> tuple[StatusIngestao, bool]:
        self._talvez_falhar()
        return _st(), self.criado

    async def pausar(self) -> StatusIngestao:
        self._talvez_falhar()
        return _st(EstadoIngestao.PAUSADA)

    async def retomar(self) -> StatusIngestao:
        self._talvez_falhar()
        return _st()

    async def reiniciar(self) -> StatusIngestao:
        self._talvez_falhar()
        return _st(EstadoIngestao.INICIANDO)

    async def remover(self) -> None:
        self._talvez_falhar()


class VerificadorFalso:
    def __init__(self) -> None:
        self.dependencias = {"kafka_connect": True, "kafka": True}

    async def verificar(self) -> dict[str, bool]:
        return self.dependencias


@pytest.fixture
def servico() -> ServicoFalso:
    return ServicoFalso()


@pytest.fixture
def verificador() -> VerificadorFalso:
    return VerificadorFalso()


@pytest.fixture
def app(servico: ServicoFalso, verificador: VerificadorFalso) -> FastAPI:
    aplicacao = criar_app(ConfigControle(controle_api_key=CHAVE))  # type: ignore[arg-type]
    aplicacao.dependency_overrides[obter_servico] = lambda: servico
    aplicacao.dependency_overrides[obter_verificador] = lambda: verificador
    return aplicacao


@pytest.fixture
async def cliente(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        yield c


async def test_get_status(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/v1/ingestao")
    assert r.status_code == 200
    assert r.json()["estado"] == "ATIVA"
    assert r.json()["arquivos"] == {"pendentes": 0, "em_backup": 0, "com_erro": 0}


@pytest.mark.parametrize(("criado", "codigo"), [(True, 201), (False, 200)])
async def test_put_ativar(
    cliente: httpx.AsyncClient, servico: ServicoFalso, criado: bool, codigo: int
) -> None:
    servico.criado = criado
    r = await cliente.put("/api/v1/ingestao", headers=AUTH)
    assert r.status_code == codigo


@pytest.mark.parametrize("acao", ["pausar", "retomar", "reiniciar"])
async def test_acoes_retornam_202(cliente: httpx.AsyncClient, acao: str) -> None:
    r = await cliente.post(f"/api/v1/ingestao/{acao}", headers=AUTH)
    assert r.status_code == 202
    assert "estado" in r.json()


async def test_delete_204(cliente: httpx.AsyncClient) -> None:
    r = await cliente.delete("/api/v1/ingestao", headers=AUTH)
    assert r.status_code == 204


@pytest.mark.parametrize(
    ("metodo", "rota"),
    [
        ("PUT", "/api/v1/ingestao"),
        ("DELETE", "/api/v1/ingestao"),
        ("POST", "/api/v1/ingestao/pausar"),
        ("POST", "/api/v1/ingestao/retomar"),
        ("POST", "/api/v1/ingestao/reiniciar"),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "errada"}])
async def test_mutacoes_exigem_chave(
    cliente: httpx.AsyncClient, metodo: str, rota: str, headers: dict[str, str]
) -> None:
    r = await cliente.request(metodo, rota, headers=headers)
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    corpo = r.json()
    assert corpo["status"] == 401
    assert corpo["correlation_id"]


@pytest.mark.parametrize(
    ("erro", "codigo"),
    [
        (IngestaoInexistenteError("x"), 404),
        (ConnectIndisponivelError("x"), 503),
        (ConnectErroError(400, "config ruim"), 502),
    ],
)
async def test_erros_viram_problem_details(
    cliente: httpx.AsyncClient, servico: ServicoFalso, erro: Exception, codigo: int
) -> None:
    servico.erro = erro
    r = await cliente.post("/api/v1/ingestao/pausar", headers=AUTH)
    assert r.status_code == codigo
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"]


async def test_correlation_id_propagado(cliente: httpx.AsyncClient, servico: ServicoFalso) -> None:
    servico.erro = ConnectIndisponivelError("x")
    r = await cliente.get("/api/v1/ingestao", headers={"X-Correlation-ID": "corr-1"})
    assert r.headers["X-Correlation-ID"] == "corr-1"
    assert r.json()["correlation_id"] == "corr-1"


async def test_health_live(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize(
    ("deps", "codigo", "indisponivel"),
    [
        ({"kafka_connect": True, "kafka": True}, 200, None),
        ({"kafka_connect": False, "kafka": True}, 503, "kafka_connect"),
        ({"kafka_connect": True, "kafka": False}, 503, "kafka"),
    ],
)
async def test_health_ready(
    cliente: httpx.AsyncClient,
    verificador: VerificadorFalso,
    deps: dict[str, bool],
    codigo: int,
    indisponivel: str | None,
) -> None:
    verificador.dependencias = deps
    r = await cliente.get("/health/ready")
    assert r.status_code == codigo
    corpo: dict[str, Any] = r.json()
    if indisponivel:
        assert corpo["dependencias"][indisponivel] == "indisponivel"


async def test_metrics(cliente: httpx.AsyncClient) -> None:
    await cliente.get("/api/v1/ingestao")
    r = await cliente.get("/metrics")
    assert r.status_code == 200
    assert "controle_requisicoes_total" in r.text
    assert "controle_arquivos" in r.text
