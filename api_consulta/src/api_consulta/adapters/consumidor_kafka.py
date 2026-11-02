"""Consumo contínuo do tópico de eventos com `aiokafka` (research.md, R10).

Sem consumer group: todas as partições são atribuídas manualmente e lidas desde o início a cada
inicialização, reconstruindo a projeção em memória. Em caso de falha, reconecta com backoff
exponencial e retoma das posições já processadas.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from pydantic import BaseModel, Field

from api_consulta.adapters.mensagem import Mensagem
from api_consulta.config import ConfigConsulta
from api_consulta.observabilidade import ERROS, LAG
from api_consulta.services.processador import Processador

BACKOFF_MAXIMO_S = 30.0
log = structlog.get_logger()


class LagParticao(BaseModel):
    """Posição e atraso de uma partição."""

    particao: int
    posicao: int
    offset_final: int
    lag: int = Field(ge=0)


class StatusConsumo(BaseModel):
    """Status do consumo do tópico."""

    topico: str
    catch_up_concluido: bool
    lag_total: int = Field(ge=0)
    particoes: list[LagParticao]


class ConsumidorEventos:
    """Lê o tópico de eventos e entrega cada mensagem ao `Processador`."""

    def __init__(
        self, config: ConfigConsulta, processador: Processador, producer: AIOKafkaProducer
    ) -> None:
        self.config = config
        self.topico = config.topico_eventos
        self.processador = processador
        self.producer = producer
        self.conectado = False
        self.catch_up_concluido = False
        self._consumer: AIOKafkaConsumer | None = None
        self._producer_iniciado = False
        self._tps: list[TopicPartition] = []
        self._fins_iniciais: dict[TopicPartition, int] | None = None
        self._posicoes: dict[TopicPartition, int] = {}
        self._inicio = time.monotonic()
        self._aviso_catch_up = False

    async def _conectar(self) -> AIOKafkaConsumer:
        if not self._producer_iniciado:
            await self.producer.start()
            self._producer_iniciado = True
        consumer = AIOKafkaConsumer(
            bootstrap_servers=self.config.kafka_bootstrap,
            group_id=None,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            client_id="api-consulta",
        )
        await consumer.start()
        try:
            particoes: set[int] | None = None
            while not particoes:
                # `partitions_for_topic` do consumer só conhece tópicos já atribuídos; os
                # metadados completos do cluster trazem as partições antes do `assign`.
                metadados = await consumer._client.fetch_all_metadata()
                particoes = metadados.partitions_for_topic(self.topico)
                if not particoes:
                    log.warning("topico_sem_metadados", topico=self.topico)
                    await asyncio.sleep(1)
            self._tps = [TopicPartition(self.topico, p) for p in sorted(particoes)]
            consumer.assign(self._tps)
            for tp in self._tps:
                if tp in self._posicoes:
                    consumer.seek(tp, self._posicoes[tp])
                else:
                    await consumer.seek_to_beginning(tp)
            if self._fins_iniciais is None:
                self._fins_iniciais = await consumer.end_offsets(self._tps)
        except BaseException:
            await consumer.stop()
            raise
        self._consumer = consumer
        self.conectado = True
        log.info("consumidor_conectado", topico=self.topico, particoes=len(self._tps))
        return consumer

    async def _fechar(self) -> None:
        self.conectado = False
        if self._consumer is not None:
            consumer, self._consumer = self._consumer, None
            try:
                await consumer.stop()
            except Exception:  # pragma: no cover - melhor esforço
                log.exception("erro_ao_fechar_consumidor")

    async def _verificar_catch_up(self, consumer: AIOKafkaConsumer) -> None:
        if self.catch_up_concluido or self._fins_iniciais is None:
            return
        for tp, fim in self._fins_iniciais.items():
            if await consumer.position(tp) < fim:
                if (
                    not self._aviso_catch_up
                    and time.monotonic() - self._inicio > self.config.catch_up_timeout_s
                ):
                    self._aviso_catch_up = True
                    log.warning("catch_up_demorado", timeout_s=self.config.catch_up_timeout_s)
                return
        self.catch_up_concluido = True
        log.info("catch_up_concluido", resumo=self.processador.projecao.resumo().model_dump())

    async def _consumir(self, consumer: AIOKafkaConsumer) -> None:
        while True:
            lotes: dict[TopicPartition, list[Any]] = await consumer.getmany(
                timeout_ms=1000, max_records=500
            )
            for tp, registros in lotes.items():
                for r in registros:
                    await self.processador.processar(
                        Mensagem(
                            topic=r.topic,
                            partition=r.partition,
                            offset=r.offset,
                            key=r.key,
                            value=r.value,
                            headers=list(r.headers or ()),
                        )
                    )
                    self._posicoes[tp] = r.offset + 1
            await self._verificar_catch_up(consumer)

    async def executar(self) -> None:
        """Loop principal: conecta, consome e reconecta com backoff em caso de falha."""
        backoff = 1.0
        while True:
            try:
                consumer = await self._conectar()
                backoff = 1.0
                await self._consumir(consumer)
            except asyncio.CancelledError:
                await self._fechar()
                raise
            except Exception:
                ERROS.labels("consumo").inc()
                log.exception("falha_no_consumo", nova_tentativa_em_s=backoff)
                await self._fechar()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAXIMO_S)

    async def parar(self) -> None:
        """Fecha consumidor e producer."""
        await self._fechar()
        if self._producer_iniciado:
            await self.producer.stop()

    async def status_consumo(self) -> StatusConsumo:
        """Posição, offset final e lag por partição (atualiza a métrica de lag)."""
        consumer = self._consumer
        particoes: list[LagParticao] = []
        if consumer is not None and self._tps:
            fins = await consumer.end_offsets(self._tps)
            for tp in self._tps:
                posicao = await consumer.position(tp)
                lag = max(fins[tp] - posicao, 0)
                LAG.labels(str(tp.partition)).set(lag)
                particoes.append(
                    LagParticao(
                        particao=tp.partition, posicao=posicao, offset_final=fins[tp], lag=lag
                    )
                )
        return StatusConsumo(
            topico=self.topico,
            catch_up_concluido=self.catch_up_concluido,
            lag_total=sum(p.lag for p in particoes),
            particoes=particoes,
        )
