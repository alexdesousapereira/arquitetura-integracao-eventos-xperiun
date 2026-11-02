from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from testcontainers.community.kafka import KafkaContainer

IMAGEM_KAFKA = "confluentinc/cp-kafka:7.9.10"
CONFIGS_TOPICO = {"cleanup.policy": "delete", "retention.ms": "900000", "segment.ms": "60000"}


@pytest.fixture(scope="session")
def kafka() -> Iterator[str]:
    # verificação de retenção a cada 2 s: permite comprovar a expiração com retenção curta
    container = KafkaContainer(IMAGEM_KAFKA).with_kraft()
    container.with_env("KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS", "2000")
    with container:
        yield container.get_bootstrap_server()


@pytest.fixture
async def topicos(kafka: str) -> AsyncIterator[tuple[str, str]]:
    """Cria um tópico de eventos (3 partições) e um DLQ exclusivos para o teste."""
    sufixo = uuid.uuid4().hex[:8]
    eventos, dlq = f"eventos-{sufixo}", f"dlq-{sufixo}"
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka)
    await admin.start()
    try:
        await admin.create_topics(
            [
                NewTopic(
                    eventos, num_partitions=3, replication_factor=1, topic_configs=CONFIGS_TOPICO
                ),
                NewTopic(dlq, num_partitions=1, replication_factor=1),
            ]
        )
        yield eventos, dlq
    finally:
        await admin.close()
