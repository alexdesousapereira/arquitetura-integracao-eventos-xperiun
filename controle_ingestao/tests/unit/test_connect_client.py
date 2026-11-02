from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from controle_ingestao.adapters.connect_client import (
    ConectorInexistenteError,
    ConnectClient,
    ConnectErroError,
    ConnectIndisponivelError,
)

BASE = "http://connect:8083"
NOME = "arquivos"


@pytest.fixture
async def cliente() -> AsyncIterator[ConnectClient]:
    async with httpx.AsyncClient(base_url=BASE, timeout=1) as http:
        yield ConnectClient(http)


@respx.mock
async def test_obter_status_200(cliente: ConnectClient) -> None:
    respx.get(f"{BASE}/connectors/{NOME}/status").respond(200, json={"connector": {}})
    assert await cliente.obter_status(NOME) == {"connector": {}}


@respx.mock
async def test_obter_status_404_retorna_none(cliente: ConnectClient) -> None:
    respx.get(f"{BASE}/connectors/{NOME}/status").respond(404, json={"message": "not found"})
    assert await cliente.obter_status(NOME) is None


@respx.mock
@pytest.mark.parametrize(("codigo", "criado"), [(201, True), (200, False)])
async def test_aplicar_config_distingue_criado(
    cliente: ConnectClient, codigo: int, criado: bool
) -> None:
    rota = respx.put(f"{BASE}/connectors/{NOME}/config").respond(codigo, json={"name": NOME})
    assert await cliente.aplicar_config(NOME, {"a": "b"}) is criado
    assert rota.calls.last.request.read() == b'{"a":"b"}'


@respx.mock
async def test_obter_config(cliente: ConnectClient) -> None:
    respx.get(f"{BASE}/connectors/{NOME}/config").respond(200, json={"a": "b"})
    assert await cliente.obter_config(NOME) == {"a": "b"}
    respx.get(f"{BASE}/connectors/{NOME}/config").respond(404, json={"message": "x"})
    assert await cliente.obter_config(NOME) is None


@respx.mock
async def test_pausar_e_retomar(cliente: ConnectClient) -> None:
    pausa = respx.put(f"{BASE}/connectors/{NOME}/pause").respond(202)
    retomada = respx.put(f"{BASE}/connectors/{NOME}/resume").respond(202)
    await cliente.pausar(NOME)
    await cliente.retomar(NOME)
    assert pausa.called
    assert retomada.called


@respx.mock
async def test_reiniciar_inclui_tarefas(cliente: ConnectClient) -> None:
    rota = respx.post(f"{BASE}/connectors/{NOME}/restart").respond(202, json={})
    await cliente.reiniciar(NOME)
    params = rota.calls.last.request.url.params
    assert params["includeTasks"] == "true"
    assert params["onlyFailed"] == "false"


@respx.mock
async def test_reiniciar_conector_sem_tarefas(cliente: ConnectClient) -> None:
    rota = respx.post(f"{BASE}/connectors/{NOME}/restart").respond(204)
    await cliente.reiniciar_conector(NOME)
    assert "includeTasks" not in rota.calls.last.request.url.params


@respx.mock
async def test_pausar_inexistente(cliente: ConnectClient) -> None:
    respx.put(f"{BASE}/connectors/{NOME}/pause").respond(404, json={"message": "x"})
    with pytest.raises(ConectorInexistenteError):
        await cliente.pausar(NOME)


@respx.mock
async def test_remover_404_e_sucesso(cliente: ConnectClient) -> None:
    respx.delete(f"{BASE}/connectors/{NOME}").respond(404, json={"message": "x"})
    await cliente.remover(NOME)


@respx.mock
async def test_conexao_recusada_vira_indisponivel(cliente: ConnectClient) -> None:
    respx.get(f"{BASE}/connectors/{NOME}/status").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(ConnectIndisponivelError):
        await cliente.obter_status(NOME)


@respx.mock
async def test_timeout_vira_indisponivel(cliente: ConnectClient) -> None:
    respx.put(f"{BASE}/connectors/{NOME}/pause").mock(side_effect=httpx.ReadTimeout("x"))
    with pytest.raises(ConnectIndisponivelError):
        await cliente.pausar(NOME)


@respx.mock
async def test_erro_do_connect_preserva_detalhe(cliente: ConnectClient) -> None:
    respx.put(f"{BASE}/connectors/{NOME}/config").respond(400, json={"message": "config ruim"})
    with pytest.raises(ConnectErroError) as exc:
        await cliente.aplicar_config(NOME, {})
    assert exc.value.status == 400
    assert "config ruim" in str(exc.value)


@respx.mock
async def test_ping(cliente: ConnectClient) -> None:
    respx.get(f"{BASE}/").respond(200, json={"version": "7.9"})
    assert await cliente.ping() is True
    respx.get(f"{BASE}/").mock(side_effect=httpx.ConnectError("x"))
    assert await cliente.ping() is False


@respx.mock
async def test_propaga_correlation_id(cliente: ConnectClient) -> None:
    from controle_ingestao.observabilidade import correlation_id_var

    rota = respx.get(f"{BASE}/connectors/{NOME}/status").respond(200, json={})
    token = correlation_id_var.set("abc-123")
    try:
        await cliente.obter_status(NOME)
    finally:
        correlation_id_var.reset(token)
    assert rota.calls.last.request.headers["X-Correlation-ID"] == "abc-123"
