"""Consumo do tópico de eventos com consumer group próprio e commit manual.

Diferente da API de consulta (que lê todas as partições sem grupo e reconstrói a projeção a cada
inicialização), o notificador participa do grupo `notificador`:

- o Kafka guarda o offset do grupo, então o bot retoma de onde parou depois de reiniciar;
- o offset só é commitado depois do envio, garantindo entrega *at-least-once*;
- várias instâncias no mesmo grupo dividem as partições entre si (rebalanceamento).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer, ConsumerRebalanceListener, TopicPartition

from notificador.canais import ErroEnvio
from notificador.config import ConfigNotificador
from notificador.observabilidade import FALHAS_ENVIO
from notificador.servico import Notificador, Resultado

BACKOFF_MAXIMO_S = 60.0
log = structlog.get_logger()

Dormir = Callable[[float], Awaitable[None]]


class _AoRebalancear(ConsumerRebalanceListener):  # type: ignore[misc]
    """Registra as partições recebidas e perdidas a cada rebalanceamento do grupo."""

    def __init__(self, consumer: Any) -> None:
        self._consumer = consumer

    async def on_partitions_revoked(self, revoked: set[TopicPartition]) -> None:
        if revoked:
            log.info("particoes_revogadas", particoes=sorted(tp.partition for tp in revoked))

    async def on_partitions_assigned(self, assigned: set[TopicPartition]) -> None:
        log.info("particoes_atribuidas", particoes=sorted(tp.partition for tp in assigned))
        # Partição ainda sem offset no grupo: fixa o ponto de partida já. Sem isso, se o bot parar
        # antes de receber a primeira mensagem dela, ao voltar o `latest` pularia o que chegou
        # nesse intervalo.
        for tp in assigned:
            if await self._consumer.committed(tp) is None:
                await self._consumer.commit({tp: await self._consumer.position(tp)})


class ConsumidorNotificacoes:
    """Lê o tópico no grupo do notificador e entrega cada evento ao `Notificador`."""

    def __init__(
        self,
        config: ConfigNotificador,
        notificador: Notificador,
        *,
        fabrica_consumer: Callable[..., Any] = AIOKafkaConsumer,
        dormir: Dormir = asyncio.sleep,
    ) -> None:
        self.config = config
        self.notificador = notificador
        self._fabrica = fabrica_consumer
        self._dormir = dormir
        self._consumer: Any = None

    async def _conectar(self) -> Any:
        consumer = self._fabrica(
            bootstrap_servers=self.config.kafka_bootstrap,
            group_id=self.config.notificador_grupo,
            client_id="notificador",
            enable_auto_commit=False,
            auto_offset_reset=self.config.notificador_offset_inicial,
        )
        consumer.subscribe([self.config.topico_eventos], listener=_AoRebalancear(consumer))
        await consumer.start()
        self._consumer = consumer
        log.info(
            "consumidor_conectado",
            topico=self.config.topico_eventos,
            grupo=self.config.notificador_grupo,
            canal=self.notificador.canal.nome,
        )
        return consumer

    async def _fechar(self) -> None:
        if self._consumer is not None:
            consumer, self._consumer = self._consumer, None
            try:
                await consumer.stop()
            except Exception:  # pragma: no cover - melhor esforço
                log.exception("erro_ao_fechar_consumidor")

    async def _entregar(self, valor: bytes | None) -> Resultado:
        """Tenta até conseguir: falhas temporárias não fazem o evento ser pulado."""
        backoff = 1.0
        while True:
            try:
                return await self.notificador.processar(valor)
            except ErroEnvio as exc:
                espera = max(exc.aguardar_s, backoff)
                FALHAS_ENVIO.labels("temporaria").inc()
                log.warning("envio_falhou", motivo=exc.motivo, nova_tentativa_em_s=espera)
                await self._dormir(espera)
                backoff = min(backoff * 2, BACKOFF_MAXIMO_S)

    async def _consumir(self, consumer: Any) -> None:
        while True:
            lotes: dict[TopicPartition, list[Any]] = await consumer.getmany(
                timeout_ms=1000, max_records=50
            )
            for tp, registros in lotes.items():
                for registro in registros:
                    resultado = await self._entregar(registro.value)
                    await consumer.commit({tp: registro.offset + 1})
                    if resultado is Resultado.ENVIADO and self.config.notificador_intervalo_s:
                        # Respeita o limite de mensagens por segundo do Telegram.
                        await self._dormir(self.config.notificador_intervalo_s)

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
                log.exception("falha_no_consumo", nova_tentativa_em_s=backoff)
                await self._fechar()
                await self._dormir(backoff)
                backoff = min(backoff * 2, BACKOFF_MAXIMO_S)
