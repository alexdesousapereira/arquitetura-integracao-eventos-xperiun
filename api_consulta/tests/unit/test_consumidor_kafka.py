from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from aiokafka import TopicPartition

from api_consulta.adapters import consumidor_kafka
from api_consulta.adapters.consumidor_kafka import ConsumidorEventos
from api_consulta.adapters.mensagem import Mensagem
from api_consulta.config import ConfigConsulta
from api_consulta.services.processador import Processador
from api_consulta.services.projecao import Projecao

TOPICO = "eventos"


class ProcessadorFalso:
    def __init__(self) -> None:
        self.mensagens: list[Mensagem] = []
        self.projecao = Projecao(timedelta(minutes=15))

    async def processar(self, mensagem: Mensagem) -> None:
        self.mensagens.append(mensagem)


class ProducerFalso:
    def __init__(self) -> None:
        self.iniciado = 0
        self.parado = 0

    async def start(self) -> None:
        self.iniciado += 1

    async def stop(self) -> None:
        self.parado += 1


class ConsumerFalso:
    """Simula um tópico de 2 partições com registros em memória."""

    instancias: ClassVar[list[ConsumerFalso]] = []
    registros: ClassVar[dict[int, list[bytes]]] = {}
    falhar_getmany_uma_vez = False
    metadados_vazios = 0

    def __init__(self, **_: Any) -> None:
        self.posicoes: dict[TopicPartition, int] = {}
        self.parado = False
        self.seeks: dict[TopicPartition, int] = {}
        ConsumerFalso.instancias.append(self)

        async def fetch_all_metadata() -> Any:
            if ConsumerFalso.metadados_vazios > 0:
                ConsumerFalso.metadados_vazios -= 1
                return SimpleNamespace(partitions_for_topic=lambda _t: None)
            return SimpleNamespace(partitions_for_topic=lambda _t: set(self.registros))

        self._client = SimpleNamespace(fetch_all_metadata=fetch_all_metadata)

    async def start(self) -> None: ...

    async def stop(self) -> None:
        self.parado = True

    def assign(self, tps: list[TopicPartition]) -> None:
        self.tps = tps

    def seek(self, tp: TopicPartition, offset: int) -> None:
        self.posicoes[tp] = offset
        self.seeks[tp] = offset

    async def seek_to_beginning(self, tp: TopicPartition) -> None:
        self.posicoes[tp] = 0

    async def end_offsets(self, tps: list[TopicPartition]) -> dict[TopicPartition, int]:
        return {tp: len(self.registros[tp.partition]) for tp in tps}

    async def position(self, tp: TopicPartition) -> int:
        return self.posicoes[tp]

    async def getmany(self, **_: Any) -> dict[TopicPartition, list[Any]]:
        if ConsumerFalso.falhar_getmany_uma_vez:
            ConsumerFalso.falhar_getmany_uma_vez = False
            raise ConnectionError("broker caiu")
        lotes: dict[TopicPartition, list[Any]] = {}
        for tp in self.tps:
            inicio = self.posicoes[tp]
            valores = self.registros[tp.partition][inicio : inicio + 2]
            if valores:
                lotes[tp] = [
                    SimpleNamespace(
                        topic=TOPICO,
                        partition=tp.partition,
                        offset=inicio + i,
                        key=b"k",
                        value=v,
                        headers=[("h", b"1")],
                    )
                    for i, v in enumerate(valores)
                ]
                self.posicoes[tp] = inicio + len(valores)
        await asyncio.sleep(0)
        return lotes


@pytest.fixture(autouse=True)
def consumer_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    ConsumerFalso.instancias = []
    ConsumerFalso.registros = {0: [b"a", b"b", b"c"], 1: [b"d"]}
    ConsumerFalso.falhar_getmany_uma_vez = False
    ConsumerFalso.metadados_vazios = 0
    monkeypatch.setattr(consumidor_kafka, "AIOKafkaConsumer", ConsumerFalso)

    dormir_original = asyncio.sleep

    async def sem_espera(_: float) -> None:
        await dormir_original(0)

    monkeypatch.setattr(consumidor_kafka.asyncio, "sleep", sem_espera)


def _consumidor() -> tuple[ConsumidorEventos, ProcessadorFalso, ProducerFalso]:
    processador = ProcessadorFalso()
    producer = ProducerFalso()
    consumidor = ConsumidorEventos(
        ConfigConsulta(topico_eventos=TOPICO, catch_up_timeout_s=0.001),
        processador,  # type: ignore[arg-type]
        producer,  # type: ignore[arg-type]
    )
    return consumidor, processador, producer


async def _rodar_ate(consumidor: ConsumidorEventos, condicao: Any) -> None:
    tarefa = asyncio.create_task(consumidor.executar())
    try:
        for _ in range(500):
            if condicao():
                return
            await asyncio.sleep(0)
        raise AssertionError("condição não atingida")
    finally:
        tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa


async def test_consome_todas_as_particoes_e_conclui_catch_up() -> None:
    consumidor, processador, producer = _consumidor()
    await _rodar_ate(consumidor, lambda: consumidor.catch_up_concluido)
    assert sorted(m.value for m in processador.mensagens) == [b"a", b"b", b"c", b"d"]
    assert processador.mensagens[0].headers == [("h", b"1")]
    assert producer.iniciado == 1
    assert ConsumerFalso.instancias[-1].parado  # fechado no cancelamento


async def test_status_consumo_calcula_lag() -> None:
    consumidor, _, _ = _consumidor()
    vazio = await consumidor.status_consumo()
    assert vazio.particoes == []
    await _rodar_ate(consumidor, lambda: consumidor.catch_up_concluido)
    ConsumerFalso.registros[0].append(b"novo")
    consumidor._consumer = ConsumerFalso.instancias[-1]  # mantém referência após o cancelamento
    consumidor._consumer.tps = consumidor._tps
    status = await consumidor.status_consumo()
    assert status.lag_total == 1
    assert {p.particao: p.lag for p in status.particoes} == {0: 1, 1: 0}


async def test_reconecta_e_retoma_das_posicoes() -> None:
    from prometheus_client import REGISTRY

    antes = REGISTRY.get_sample_value("consulta_erros_total", {"tipo": "consumo"}) or 0
    ConsumerFalso.falhar_getmany_uma_vez = True
    consumidor, processador, producer = _consumidor()
    await _rodar_ate(consumidor, lambda: consumidor.catch_up_concluido)
    assert len(ConsumerFalso.instancias) == 2
    assert ConsumerFalso.instancias[0].parado
    assert producer.iniciado == 1  # producer não é reiniciado
    assert len(processador.mensagens) == 4
    assert REGISTRY.get_sample_value("consulta_erros_total", {"tipo": "consumo"}) == antes + 1


async def test_reconexao_faz_seek_nas_posicoes_salvas() -> None:
    consumidor, _, _ = _consumidor()
    await _rodar_ate(consumidor, lambda: consumidor.catch_up_concluido)
    ConsumerFalso.falhar_getmany_uma_vez = True
    await _rodar_ate(consumidor, lambda: len(ConsumerFalso.instancias) >= 3)
    seeks = ConsumerFalso.instancias[-1].seeks
    assert {tp.partition: o for tp, o in seeks.items()} == {0: 3, 1: 1}


async def test_aguarda_metadados_do_topico() -> None:
    ConsumerFalso.metadados_vazios = 2
    consumidor, _, _ = _consumidor()
    await _rodar_ate(consumidor, lambda: consumidor.catch_up_concluido)
    assert consumidor.conectado is False  # fechado ao final


async def test_parar_fecha_producer() -> None:
    consumidor, _, producer = _consumidor()
    await _rodar_ate(consumidor, lambda: consumidor.catch_up_concluido)
    await consumidor.parar()
    assert producer.parado == 1


def test_tipo_do_processador_real_e_aceito() -> None:
    processador = Processador(Projecao(timedelta(minutes=1)), dlq=None)  # type: ignore[arg-type]
    ConsumidorEventos(ConfigConsulta(), processador, ProducerFalso())  # type: ignore[arg-type]
