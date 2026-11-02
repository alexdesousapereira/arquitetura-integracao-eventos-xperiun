"""US3: configuração do tópico e ordenação por carga (fica neste pacote para reaproveitar as
fixtures de Kafka da integração)."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.admin.config_resource import ConfigResource, ConfigResourceType

from contratos import EventoCargaAdapter, parse_evento

pytestmark = pytest.mark.integration


async def test_topico_criado_com_configuracao(kafka: str, topicos: tuple[str, str]) -> None:
    eventos, _ = topicos
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka)
    await admin.start()
    try:
        descricao = await admin.describe_topics([eventos])
        assert len(descricao[0]["partitions"]) == 3
        resposta = await admin.describe_configs([ConfigResource(ConfigResourceType.TOPIC, eventos)])
        configs = {c[0]: c[1] for c in resposta[0].resources[0][4]}
    finally:
        await admin.close()
    assert configs["retention.ms"] == "900000"
    assert configs["segment.ms"] == "60000"
    assert configs["cleanup.policy"] == "delete"


async def test_ordem_preservada_por_carga(
    kafka: str, topicos: tuple[str, str], gerar_jornada: Any
) -> None:
    eventos_topico, _ = topicos
    jornadas = [gerar_jornada(seed, inicio=datetime.now(UTC)) for seed in range(10)]
    producer = AIOKafkaProducer(bootstrap_servers=kafka, acks="all")
    await producer.start()
    try:
        # intercala as cargas, mantendo a ordem dentro de cada uma
        for i in range(max(len(j) for j in jornadas)):
            for j in jornadas:
                if i < len(j):
                    await producer.send(
                        eventos_topico,
                        key=j[i].carga_id.encode(),
                        value=EventoCargaAdapter.dump_json(j[i]),
                    )
        await producer.flush()
    finally:
        await producer.stop()

    total = sum(len(j) for j in jornadas)
    consumer = AIOKafkaConsumer(
        eventos_topico, bootstrap_servers=kafka, auto_offset_reset="earliest", group_id=None
    )
    await consumer.start()
    recebidos: dict[str, list[str]] = {}
    try:
        lidos = 0
        while lidos < total:
            lotes = await consumer.getmany(timeout_ms=2000)
            for registros in lotes.values():
                for r in registros:
                    evento = parse_evento(r.value)
                    assert r.key.decode() == evento.carga_id
                    recebidos.setdefault(evento.carga_id, []).append(str(evento.event_id))
                    lidos += 1
    finally:
        await consumer.stop()
    for j in jornadas:
        assert recebidos[j[0].carga_id] == [str(e.event_id) for e in j]


RETENCAO_CURTA_MS = 10_000


async def _offsets(kafka: str, topico: str) -> tuple[int, int]:
    """Soma dos *log start offsets* e dos *end offsets* de todas as partições."""
    consumer = AIOKafkaConsumer(bootstrap_servers=kafka, group_id=None)
    await consumer.start()
    try:
        particoes = [TopicPartition(topico, p) for p in consumer.partitions_for_topic(topico) or []]
        inicio = await consumer.beginning_offsets(particoes)
        fim = await consumer.end_offsets(particoes)
    finally:
        await consumer.stop()
    return sum(inicio.values()), sum(fim.values())


async def test_retencao_curta_expira_mensagens_do_topico(kafka: str, gerar_jornada: Any) -> None:
    """US3/AC3: com retenção curta (só no teste), as mensagens deixam de estar no tópico."""
    topico = f"retencao-{uuid.uuid4().hex[:8]}"
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka)
    await admin.start()
    try:
        configs = {
            "cleanup.policy": "delete",
            "retention.ms": str(RETENCAO_CURTA_MS),
            "segment.ms": "2000",
        }
        await admin.create_topics(
            [NewTopic(topico, num_partitions=1, replication_factor=1, topic_configs=configs)]
        )
    finally:
        await admin.close()

    agora = datetime.now(UTC)
    eventos = [e for seed in range(5) for e in gerar_jornada(seed, inicio=agora)][:10]
    producer = AIOKafkaProducer(bootstrap_servers=kafka, acks="all")
    await producer.start()
    try:
        for evento in eventos:
            await producer.send(
                topico, key=evento.carga_id.encode(), value=EventoCargaAdapter.dump_json(evento)
            )
        await producer.flush()
    finally:
        await producer.stop()
    assert await _offsets(kafka, topico) == (0, len(eventos))

    limite = time.monotonic() + 120
    while (inicio := (await _offsets(kafka, topico))[0]) < len(eventos):
        assert time.monotonic() < limite, f"log start offset parado em {inicio}"
        await asyncio.sleep(2)

    consumer = AIOKafkaConsumer(
        topico, bootstrap_servers=kafka, auto_offset_reset="earliest", group_id=None
    )
    await consumer.start()
    try:
        lotes = await consumer.getmany(timeout_ms=3000)
    finally:
        await consumer.stop()
    assert not any(lotes.values())
