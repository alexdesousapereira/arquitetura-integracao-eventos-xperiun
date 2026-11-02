"""Processamento de cada mensagem consumida: validação, DLQ e aplicação na projeção."""

from __future__ import annotations

import json
from typing import Any, Protocol

import structlog
from pydantic import ValidationError

from api_consulta.adapters.mensagem import Mensagem
from api_consulta.observabilidade import (
    ERROS,
    EVENTOS_CONSUMIDOS,
    EVENTOS_DLQ,
    EVENTOS_DUPLICADOS,
    EVENTOS_EXPIRADOS,
)
from api_consulta.services.projecao import Projecao, Resultado
from contratos import EventoCargaAdapter

JSON_INVALIDO = "JSON_INVALIDO"
LIMITE_MOTIVO = 1000
CONTRATO_INVALIDO = "CONTRATO_INVALIDO"

log = structlog.get_logger()


class EnviadorDLQ(Protocol):
    """Destino das mensagens inválidas."""

    async def enviar(self, mensagem: Mensagem, erro_tipo: str, erro_motivo: str) -> None:
        """Publica a mensagem original no DLQ."""
        ...


def extrair_correlation_id(mensagem: Mensagem, dados: Any) -> str | None:
    """`correlation_id` do header Kafka ou, na falta dele, do corpo da mensagem."""
    if correlacao := mensagem.header("correlation_id"):
        return correlacao
    if isinstance(dados, dict) and isinstance(dados.get("correlation_id"), str):
        return str(dados["correlation_id"])
    return None


class Processador:
    """Aplica mensagens válidas na projeção e desvia as inválidas para o DLQ."""

    def __init__(self, projecao: Projecao, dlq: EnviadorDLQ) -> None:
        self.projecao = projecao
        self.dlq = dlq

    async def processar(self, mensagem: Mensagem) -> None:
        """Processa uma mensagem; nunca propaga erro de conteúdo para o loop de consumo."""
        try:
            dados = json.loads(mensagem.value or b"")
            if not isinstance(dados, dict):
                raise ValueError("o valor não é um objeto JSON")
        except ValueError as exc:
            await self._desviar(mensagem, JSON_INVALIDO, str(exc), None)
            return
        correlacao = extrair_correlation_id(mensagem, dados)
        try:
            evento = EventoCargaAdapter.validate_python(dados)
        except ValidationError as exc:
            await self._desviar(mensagem, CONTRATO_INVALIDO, str(exc), correlacao)
            return

        resultado = self.projecao.aplicar(evento)
        if resultado is Resultado.APLICADO:
            EVENTOS_CONSUMIDOS.labels(evento.event_type.value).inc()
        elif resultado is Resultado.DUPLICADO:
            EVENTOS_DUPLICADOS.inc()
        else:
            EVENTOS_EXPIRADOS.inc()
        log.debug(
            "evento_consumido",
            resultado=resultado.name,
            event_id=str(evento.event_id),
            carga_id=evento.carga_id,
            correlation_id=correlacao,
            particao=mensagem.partition,
            offset=mensagem.offset,
        )

    async def _desviar(
        self, mensagem: Mensagem, tipo: str, motivo: str, correlacao: str | None
    ) -> None:
        contexto = {
            "erro_tipo": tipo,
            "particao": mensagem.partition,
            "offset": mensagem.offset,
            "correlation_id": correlacao,
        }
        try:
            await self.dlq.enviar(mensagem, tipo, motivo[:LIMITE_MOTIVO])
        except Exception:
            ERROS.labels("envio_dlq").inc()
            log.exception("falha_envio_dlq", **contexto)
            return
        self.projecao.registrar_dlq()
        EVENTOS_DLQ.labels(tipo).inc()
        log.warning("mensagem_enviada_dlq", **contexto)
