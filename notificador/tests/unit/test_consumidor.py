from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from aiokafka import TopicPartition

from notificador.canais import ErroEnvio
from notificador.config import ConfigNotificador
from notificador.consumidor import ConsumidorNotificacoes, _AoRebalancear
from notificador.servico import Notificador

TP = TopicPartition("loja.pedido.eventos.v1", 0)


class ConsumerFalso:
    """Devolve os lotes configurados e encerra o loop com `CancelledError` quando acabam."""

    def __init__(self, lotes: list[Any], **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.lotes = list(lotes)
        self.commits: list[dict[TopicPartition, int]] = []
        self.iniciado = False
        self.parado = False

    def subscribe(self, topicos: list[str], listener: Any) -> None:
        self.topicos = topicos
        self.listener = listener

    async def start(self) -> None:
        self.iniciado = True

    async def stop(self) -> None:
        self.parado = True

    async def getmany(self, **_: Any) -> dict[TopicPartition, list[Any]]:
        if not self.lotes:
            raise asyncio.CancelledError
        lote = self.lotes.pop(0)
        if isinstance(lote, Exception):
            raise lote
        return lote

    async def commit(self, offsets: dict[TopicPartition, int]) -> None:
        self.commits.append(offsets)

    async def committed(self, tp: TopicPartition) -> int | None:
        return {TP: 4}.get(tp)

    async def position(self, tp: TopicPartition) -> int:
        return 9


def registro(offset: int, valor: bytes) -> SimpleNamespace:
    return SimpleNamespace(offset=offset, value=valor)


class Ambiente:
    def __init__(self, lotes_por_conexao: list[list[Any]], canal: Any) -> None:
        self.consumers: list[ConsumerFalso] = []
        self.esperas: list[float] = []
        self.canal = canal
        self._lotes = list(lotes_por_conexao)
        self.consumidor = ConsumidorNotificacoes(
            ConfigNotificador(notificador_intervalo_s=0.5),
            Notificador(canal),
            fabrica_consumer=self._fabrica,
            dormir=self._dormir,
        )

    def _fabrica(self, **kwargs: Any) -> ConsumerFalso:
        consumer = ConsumerFalso(self._lotes.pop(0) if self._lotes else [], **kwargs)
        self.consumers.append(consumer)
        return consumer

    async def _dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)

    async def executar(self) -> None:
        with pytest.raises(asyncio.CancelledError):
            await self.consumidor.executar()


async def test_usa_grupo_proprio_com_commit_manual(canal_falso) -> None:
    amb = Ambiente([[]], canal_falso())
    await amb.executar()
    consumer = amb.consumers[0]
    assert consumer.kwargs["group_id"] == "notificador"
    assert consumer.kwargs["enable_auto_commit"] is False
    assert consumer.kwargs["auto_offset_reset"] == "latest"
    assert consumer.topicos == ["loja.pedido.eventos.v1"]
    assert consumer.iniciado and consumer.parado


async def test_commita_cada_offset_depois_do_envio(gerar_evento, canal_falso) -> None:
    lote = {TP: [registro(7, gerar_evento(event_id=uuid.uuid4()))]}
    lote[TP].append(registro(8, gerar_evento(event_id=uuid.uuid4())))
    amb = Ambiente([[lote]], canal_falso())
    await amb.executar()
    assert amb.consumers[0].commits == [{TP: 8}, {TP: 9}]
    assert len(amb.canal.enviadas) == 2
    assert amb.esperas == [0.5, 0.5]


async def test_duplicado_e_invalido_sao_commitados_sem_pausa(gerar_evento, canal_falso) -> None:
    valor = gerar_evento()
    lote = {TP: [registro(0, valor), registro(1, valor), registro(2, b"lixo")]}
    amb = Ambiente([[lote]], canal_falso())
    await amb.executar()
    assert amb.consumers[0].commits == [{TP: 1}, {TP: 2}, {TP: 3}]
    assert len(amb.canal.enviadas) == 1
    assert amb.esperas == [0.5]


async def test_falha_temporaria_tenta_de_novo_sem_pular_o_evento(gerar_evento, canal_falso) -> None:
    canal = canal_falso(
        [
            ErroEnvio("rede", temporario=True),
            ErroEnvio("HTTP 429", temporario=True, aguardar_s=5),
            ErroEnvio("rede", temporario=True),
        ]
    )
    amb = Ambiente([[{TP: [registro(0, gerar_evento())]}]], canal)
    await amb.executar()
    assert canal.tentativas == 4
    assert amb.esperas == [1.0, 5, 4.0, 0.5]
    assert amb.consumers[0].commits == [{TP: 1}]


async def test_reconecta_depois_de_falha_no_broker(gerar_evento, canal_falso) -> None:
    amb = Ambiente(
        [[ConnectionError("broker caiu")], [{TP: [registro(0, gerar_evento())]}]], canal_falso()
    )
    await amb.executar()
    assert len(amb.consumers) == 2
    assert amb.consumers[0].parado
    assert amb.esperas[0] == 1.0
    assert len(amb.canal.enviadas) == 1


async def test_particao_sem_offset_ganha_ponto_de_partida_ao_ser_atribuida() -> None:
    """Sem isso, um bot parado antes da 1ª mensagem da partição pularia eventos ao voltar."""
    consumer = ConsumerFalso([])
    sem_offset = TopicPartition("loja.pedido.eventos.v1", 1)
    listener = _AoRebalancear(consumer)
    await listener.on_partitions_assigned({TP, sem_offset})
    assert consumer.commits == [{sem_offset: 9}]
    await listener.on_partitions_revoked({TP})
    await listener.on_partitions_revoked(set())
