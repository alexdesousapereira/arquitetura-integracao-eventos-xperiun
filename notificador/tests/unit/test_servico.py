from __future__ import annotations

import uuid

import pytest

from notificador.canais import ErroEnvio
from notificador.servico import Notificador, Resultado


async def test_evento_valido_vira_mensagem(gerar_evento, canal_falso) -> None:
    canal = canal_falso()
    assert await Notificador(canal).processar(gerar_evento()) is Resultado.ENVIADO
    assert len(canal.enviadas) == 1
    assert "Novo pedido PED-0000E5E1" in canal.enviadas[0]


async def test_evento_repetido_nao_gera_segunda_mensagem(gerar_evento, canal_falso) -> None:
    canal = canal_falso()
    notificador = Notificador(canal)
    valor = gerar_evento()
    assert await notificador.processar(valor) is Resultado.ENVIADO
    assert await notificador.processar(valor) is Resultado.DUPLICADO
    assert len(canal.enviadas) == 1


@pytest.mark.parametrize("valor", [None, b"", b"nao e json", b"{}", b'{"event_type": "x"}'])
async def test_fora_do_contrato_e_ignorado(valor: bytes | None, canal_falso) -> None:
    canal = canal_falso()
    assert await Notificador(canal).processar(valor) is Resultado.FORA_DO_CONTRATO
    assert canal.tentativas == 0


async def test_rejeicao_definitiva_nao_e_lembrada(gerar_evento, canal_falso) -> None:
    canal = canal_falso([ErroEnvio("HTTP 400", temporario=False)])
    notificador = Notificador(canal)
    valor = gerar_evento()
    assert await notificador.processar(valor) is Resultado.REJEITADO
    assert await notificador.processar(valor) is Resultado.ENVIADO


async def test_falha_temporaria_sobe_para_o_consumidor(gerar_evento, canal_falso) -> None:
    canal = canal_falso([ErroEnvio("rede", temporario=True)])
    with pytest.raises(ErroEnvio):
        await Notificador(canal).processar(gerar_evento())


async def test_memoria_de_enviados_e_limitada(gerar_evento, canal_falso) -> None:
    canal = canal_falso()
    notificador = Notificador(canal, memoria=2)
    ids = [uuid.uuid4() for _ in range(3)]
    for event_id in ids:
        await notificador.processar(gerar_evento(event_id=event_id))
    assert await notificador.processar(gerar_evento(event_id=ids[0])) is Resultado.ENVIADO
    assert await notificador.processar(gerar_evento(event_id=ids[2])) is Resultado.DUPLICADO
