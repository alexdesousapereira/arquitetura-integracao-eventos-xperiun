from __future__ import annotations

import json

import httpx
import pytest
import respx

from notificador.canais import CanalLog, CanalTelegram, ErroEnvio

URL = "https://api.telegram.org/botTOKEN-SECRETO/sendMessage"


@pytest.fixture
def canal() -> CanalTelegram:
    return CanalTelegram("TOKEN-SECRETO", "-100123")


@respx.mock
async def test_envia_html_para_o_chat(canal: CanalTelegram) -> None:
    rota = respx.post(URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    await canal.enviar("<b>Novo pedido</b>")
    corpo = json.loads(rota.calls.last.request.content)
    assert corpo["chat_id"] == "-100123"
    assert corpo["text"] == "<b>Novo pedido</b>"
    assert corpo["parse_mode"] == "HTML"
    await canal.fechar()


@respx.mock
async def test_limite_de_envio_informa_espera(canal: CanalTelegram) -> None:
    respx.post(URL).mock(
        return_value=httpx.Response(
            429,
            json={
                "ok": False,
                "description": "Too Many Requests",
                "parameters": {"retry_after": 3},
            },
        )
    )
    with pytest.raises(ErroEnvio) as erro:
        await canal.enviar("x")
    assert erro.value.temporario
    assert erro.value.aguardar_s == 3


@respx.mock
async def test_html_invalido_e_rejeicao_definitiva(canal: CanalTelegram) -> None:
    respx.post(URL).mock(
        return_value=httpx.Response(
            400, json={"ok": False, "description": "Bad Request: can't parse entities"}
        )
    )
    with pytest.raises(ErroEnvio) as erro:
        await canal.enviar("<b>")
    assert not erro.value.temporario
    assert "can't parse entities" in erro.value.motivo


@pytest.mark.parametrize(
    ("status", "descricao"),
    [(400, "Bad Request: chat not found"), (401, "Unauthorized"), (502, "Bad Gateway")],
)
@respx.mock
async def test_erros_de_configuracao_ou_servico_sao_temporarios(
    canal: CanalTelegram, status: int, descricao: str
) -> None:
    respx.post(URL).mock(return_value=httpx.Response(status, json={"description": descricao}))
    with pytest.raises(ErroEnvio) as erro:
        await canal.enviar("x")
    assert erro.value.temporario


@respx.mock
async def test_resposta_sem_json(canal: CanalTelegram) -> None:
    respx.post(URL).mock(return_value=httpx.Response(503, text="indisponível"))
    with pytest.raises(ErroEnvio) as erro:
        await canal.enviar("x")
    assert erro.value.motivo == "HTTP 503: "


@respx.mock
async def test_falha_de_rede_nao_expoe_o_token(canal: CanalTelegram) -> None:
    respx.post(URL).mock(side_effect=httpx.ConnectError(f"falhou ao conectar em {URL}"))
    with pytest.raises(ErroEnvio) as erro:
        await canal.enviar("x")
    assert erro.value.temporario
    assert "TOKEN-SECRETO" not in str(erro.value)
    assert erro.value.__cause__ is None
    assert erro.value.__suppress_context__


async def test_canal_log_nao_envia_nada() -> None:
    canal = CanalLog()
    await canal.enviar("<b>teste</b>")
    await canal.fechar()
    assert canal.nome == "log"
