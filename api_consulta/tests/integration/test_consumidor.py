from __future__ import annotations

import asyncio
import contextlib
import json
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from api_consulta.adapters.consumidor_kafka import ConsumidorEventos
from api_consulta.adapters.produtor_dlq import ProdutorDLQ
from api_consulta.config import ConfigConsulta
from api_consulta.services.processador import Processador
from api_consulta.services.projecao import Projecao
from contratos import EventoCarga, EventoCargaAdapter
from simulador.dominio.carga import CargaSimulada
from simulador.dominio.gerador import Gerador

pytestmark = pytest.mark.integration


async def _aguardar(condicao: Callable[[], bool | Awaitable[bool]], limite_s: float = 30) -> None:
    limite = asyncio.get_running_loop().time() + limite_s
    while True:
        resultado = condicao()
        if isinstance(resultado, Awaitable):
            resultado = await resultado
        if resultado:
            return
        if asyncio.get_running_loop().time() > limite:
            raise AssertionError("condição não atingida a tempo")
        await asyncio.sleep(0.2)


async def _publicar(kafka: str, topico: str, mensagens: list[tuple[bytes, bytes]]) -> None:
    producer = AIOKafkaProducer(bootstrap_servers=kafka, acks="all")
    await producer.start()
    try:
        for chave, valor in mensagens:
            await producer.send(topico, key=chave, value=valor)
        await producer.flush()
    finally:
        await producer.stop()


class Execucao:
    def __init__(self, kafka: str, topicos: tuple[str, str], retencao_s: float = 900) -> None:
        cfg = ConfigConsulta(
            kafka_bootstrap=kafka,
            topico_eventos=topicos[0],
            topico_dlq=topicos[1],
            retencao_projecao_s=retencao_s,
        )
        self.projecao = Projecao(timedelta(seconds=retencao_s))
        producer = AIOKafkaProducer(bootstrap_servers=kafka, acks="all", enable_idempotence=True)
        processador = Processador(self.projecao, ProdutorDLQ(producer, cfg.topico_dlq))
        self.consumidor = ConsumidorEventos(cfg, processador, producer)
        self.tarefa: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Execucao:
        self.tarefa = asyncio.create_task(self.consumidor.executar())
        await _aguardar(lambda: self.consumidor.catch_up_concluido)
        return self

    async def __aexit__(self, *_: object) -> None:
        assert self.tarefa is not None
        self.tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.tarefa
        await self.consumidor.parar()


def _jornada(seed: int, inicio: datetime) -> list[EventoCarga]:
    carga = CargaSimulada.nova(Gerador(random.Random(seed)), prob_falha=0.0)
    eventos = []
    while (evento := carga.proximo_evento(inicio)) is not None:
        eventos.append(evento)
        inicio += timedelta(seconds=1)
    return eventos


def _eventos(quantidade_cargas: int, inicio: datetime) -> list[EventoCarga]:
    return [e for seed in range(quantidade_cargas) for e in _jornada(seed, inicio)]


async def test_consumo_dedup_dlq_e_reconstrucao(kafka: str, topicos: tuple[str, str]) -> None:
    eventos = _eventos(8, datetime.now(UTC))[:45]
    assert len(eventos) == 45
    validas = [(e.carga_id.encode(), EventoCargaAdapter.dump_json(e)) for e in eventos]
    duplicadas = validas[:5]
    invalidas = [
        (b"CRG-1", b"{ quebrado"),
        (b"CRG-2", json.dumps({"event_type": "carga.recebida"}).encode()),
    ]
    await _publicar(kafka, topicos[0], validas + duplicadas + invalidas)

    async with Execucao(kafka, topicos) as execucao:
        resumo = execucao.projecao.resumo()
        assert resumo.total_eventos == 45
        assert resumo.eventos_duplicados_descartados == 5
        assert resumo.eventos_enviados_dlq == 2
        status = await execucao.consumidor.status_consumo()
        assert status.catch_up_concluido
        assert status.lag_total == 0
        cargas_antes = execucao.projecao.listar(None, 1, 500).model_dump()["itens"]

    consumer = AIOKafkaConsumer(
        topicos[1], bootstrap_servers=kafka, auto_offset_reset="earliest", group_id=None
    )
    await consumer.start()
    try:
        lotes = await consumer.getmany(timeout_ms=5000)
        registros = [r for rs in lotes.values() for r in rs]
    finally:
        await consumer.stop()
    tipos = sorted(dict(r.headers)["erro_tipo"].decode() for r in registros)
    assert tipos == ["CONTRATO_INVALIDO", "JSON_INVALIDO"]
    assert {r.value for r in registros} == {v for _, v in invalidas}
    for r in registros:
        headers = dict(r.headers)
        assert headers["topico_origem"].decode() == topicos[0]
        assert {"particao_origem", "offset_origem", "erro_motivo"} <= set(headers)

    # reinício: nova instância reconstrói exatamente a mesma projeção
    async with Execucao(kafka, topicos) as segunda:
        assert segunda.projecao.listar(None, 1, 500).model_dump()["itens"] == cargas_antes


async def test_retencao_da_projecao(kafka: str, topicos: tuple[str, str]) -> None:
    antigos = _eventos(2, datetime.now(UTC) - timedelta(minutes=20))
    recentes = _eventos(3, datetime.now(UTC))
    await _publicar(
        kafka,
        topicos[0],
        [(e.carga_id.encode(), EventoCargaAdapter.dump_json(e)) for e in antigos + recentes],
    )
    async with Execucao(kafka, topicos, retencao_s=5) as execucao:
        cargas = {c.carga_id for c in execucao.projecao.listar(None, 1, 500).itens}
        assert cargas == {e.carga_id for e in recentes}
        mais_recente = max(e.occurred_at for e in recentes)
        await asyncio.sleep(max(0, (mais_recente - datetime.now(UTC)).total_seconds()) + 5.5)
        assert execucao.projecao.expirar() == len(recentes)
        assert execucao.projecao.resumo().total_cargas == 0
