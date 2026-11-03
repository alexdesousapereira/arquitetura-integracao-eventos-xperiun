"""Decide o que fazer com cada mensagem consumida: validar, deduplicar, formatar e enviar."""

from __future__ import annotations

from collections import OrderedDict
from enum import StrEnum
from uuid import UUID

import structlog
from pydantic import ValidationError

from contratos import formatar_mensagem, parse_evento
from notificador.canais import Canal, ErroEnvio
from notificador.observabilidade import EVENTOS_IGNORADOS, FALHAS_ENVIO, MENSAGENS_ENVIADAS

MEMORIA_PADRAO = 10_000
log = structlog.get_logger()


class Resultado(StrEnum):
    """Desfecho do processamento de uma mensagem."""

    ENVIADO = "ENVIADO"
    DUPLICADO = "DUPLICADO"
    FORA_DO_CONTRATO = "FORA_DO_CONTRATO"
    REJEITADO = "REJEITADO"


class Notificador:
    """Transforma eventos em mensagens e entrega ao canal.

    Lembra os últimos `memoria` `event_id` enviados: um evento repetido no tópico (ou relido
    depois de uma reconexão) não gera uma segunda mensagem enquanto o processo estiver no ar.
    """

    def __init__(self, canal: Canal, *, memoria: int = MEMORIA_PADRAO) -> None:
        self.canal = canal
        self._memoria = memoria
        self._enviados: OrderedDict[UUID, None] = OrderedDict()

    async def processar(self, valor: bytes | None) -> Resultado:
        """Processa o valor de uma mensagem Kafka.

        Raises:
            ErroEnvio: falha temporária; a mensagem deve ser tentada de novo.
        """
        try:
            evento = parse_evento(valor or b"")
        except ValidationError:
            # A API de consulta já desvia mensagens inválidas para o DLQ; aqui só não notifica.
            EVENTOS_IGNORADOS.labels("fora_do_contrato").inc()
            log.warning("evento_fora_do_contrato")
            return Resultado.FORA_DO_CONTRATO

        contexto = {
            "event_id": str(evento.event_id),
            "event_type": evento.event_type.value,
            "pedido_id": evento.pedido_id,
            "correlation_id": str(evento.correlation_id),
        }
        if evento.event_id in self._enviados:
            EVENTOS_IGNORADOS.labels("duplicado").inc()
            log.info("evento_duplicado", **contexto)
            return Resultado.DUPLICADO

        try:
            await self.canal.enviar(formatar_mensagem(evento))
        except ErroEnvio as exc:
            if exc.temporario:
                raise
            FALHAS_ENVIO.labels("rejeitada").inc()
            log.error("mensagem_rejeitada", motivo=exc.motivo, **contexto)
            return Resultado.REJEITADO

        self._lembrar(evento.event_id)
        MENSAGENS_ENVIADAS.labels(evento.event_type.value, self.canal.nome).inc()
        log.info("mensagem_enviada", canal=self.canal.nome, **contexto)
        return Resultado.ENVIADO

    def _lembrar(self, event_id: UUID) -> None:
        self._enviados[event_id] = None
        while len(self._enviados) > self._memoria:
            self._enviados.popitem(last=False)
