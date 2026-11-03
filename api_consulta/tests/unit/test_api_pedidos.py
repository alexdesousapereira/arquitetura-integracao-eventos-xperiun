from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from api_consulta.adapters.consumidor_kafka import LagParticao, StatusConsumo
from api_consulta.api.dependencias import obter_consumidor, obter_projecao
from api_consulta.config import ConfigConsulta
from api_consulta.main import criar_app
from api_consulta.services.projecao import Projecao


class ConsumidorFalso:
    def __init__(self) -> None:
        self.conectado = True
        self.catch_up_concluido = True

    async def status_consumo(self) -> StatusConsumo:
        return StatusConsumo(
            topico="t",
            catch_up_concluido=self.catch_up_concluido,
            lag_total=3,
            particoes=[LagParticao(particao=0, posicao=7, offset_final=10, lag=3)],
        )


@pytest.fixture
def projecao(relogio: Any, gerar_jornada: Any) -> Projecao:
    proj = Projecao(timedelta(minutes=15), agora=relogio)
    for seed in range(5):
        for evento in gerar_jornada(seed, inicio=relogio() - timedelta(minutes=1)):
            proj.aplicar(evento)
    return proj


@pytest.fixture
def consumidor() -> ConsumidorFalso:
    return ConsumidorFalso()


@pytest.fixture
def app(projecao: Projecao, consumidor: ConsumidorFalso) -> FastAPI:
    aplicacao = criar_app(ConfigConsulta())
    aplicacao.dependency_overrides[obter_projecao] = lambda: projecao
    aplicacao.dependency_overrides[obter_consumidor] = lambda: consumidor
    return aplicacao


@pytest.fixture
async def cliente(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://teste"
    ) as c:
        yield c


async def test_listar_pedidos(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/v1/pedidos", params={"size": 2})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 5
    assert len(corpo["itens"]) == 2
    assert corpo["page"] == 1


async def test_listar_filtra_status(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/v1/pedidos", params={"status": "ENVIADO"})
    assert r.status_code == 200
    assert {c["status"] for c in r.json()["itens"]} == {"ENVIADO"}


@pytest.mark.parametrize("params", [{"size": 0}, {"size": 501}, {"page": 0}, {"status": "PERDIDA"}])
async def test_listar_parametros_invalidos(
    cliente: httpx.AsyncClient, params: dict[str, Any]
) -> None:
    r = await cliente.get("/api/v1/pedidos", params=params)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_detalhe_e_historico(cliente: httpx.AsyncClient, projecao: Projecao) -> None:
    pedido_id = projecao.listar(None, 1, 1).itens[0].pedido_id
    r = await cliente.get(f"/api/v1/pedidos/{pedido_id}")
    assert r.status_code == 200
    assert r.json()["pedido_id"] == pedido_id
    r = await cliente.get(f"/api/v1/pedidos/{pedido_id}/eventos")
    assert r.status_code == 200
    eventos = r.json()["eventos"]
    instantes = [e["occurred_at"] for e in eventos]
    assert instantes == sorted(instantes)
    assert all(e["occurred_at"].endswith("Z") for e in eventos)


async def test_pedido_inexistente_404(cliente: httpx.AsyncClient) -> None:
    for rota in ("/api/v1/pedidos/PED-00000000", "/api/v1/pedidos/PED-00000000/eventos"):
        r = await cliente.get(rota, headers={"X-Correlation-ID": "c-404"})
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["correlation_id"] == "c-404"


async def test_pedido_id_invalido_422(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/v1/pedidos/abc")
    assert r.status_code == 422


async def test_resumo(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/v1/resumo")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total_pedidos"] == 5
    assert sum(corpo["pedidos_por_status"].values()) == 5


async def test_status_consumo(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/v1/consumo/status")
    assert r.status_code == 200
    assert r.json()["lag_total"] == 3


async def test_ready_depende_de_catch_up(
    cliente: httpx.AsyncClient, consumidor: ConsumidorFalso
) -> None:
    assert (await cliente.get("/health/ready")).status_code == 200
    consumidor.catch_up_concluido = False
    r = await cliente.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["dependencias"]["catch_up"] == "em_andamento"
    consumidor.catch_up_concluido = True
    consumidor.conectado = False
    assert (await cliente.get("/health/ready")).status_code == 503


async def test_live_e_metrics(cliente: httpx.AsyncClient) -> None:
    assert (await cliente.get("/health/live")).json() == {"status": "ok", "dependencias": {}}
    r = await cliente.get("/metrics")
    assert r.status_code == 200
    assert "consulta_eventos_consumidos_total" in r.text
