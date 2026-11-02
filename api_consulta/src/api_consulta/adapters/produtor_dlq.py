"""Publicação de mensagens inválidas no tópico DLQ (contracts/topicos.md)."""

from __future__ import annotations

from typing import Any, Protocol

from api_consulta.adapters.mensagem import Mensagem

LIMITE_MOTIVO = 1000


class _Producer(Protocol):
    async def send_and_wait(self, topic: str, **kwargs: Any) -> Any:
        """Envia e aguarda a confirmação do broker."""
        ...


class ProdutorDLQ:
    """Reenvia a mensagem original (chave e valor intactos) ao DLQ com headers de diagnóstico."""

    def __init__(self, producer: _Producer, topico: str) -> None:
        self.producer = producer
        self.topico = topico

    async def enviar(self, mensagem: Mensagem, erro_tipo: str, erro_motivo: str) -> None:
        """Publica no DLQ e aguarda a confirmação."""
        headers = [
            ("erro_tipo", erro_tipo.encode()),
            ("erro_motivo", erro_motivo[:LIMITE_MOTIVO].encode()),
            ("topico_origem", mensagem.topic.encode()),
            ("particao_origem", str(mensagem.partition).encode()),
            ("offset_origem", str(mensagem.offset).encode()),
        ]
        if correlacao := mensagem.header("correlation_id"):
            headers.append(("correlation_id", correlacao.encode()))
        await self.producer.send_and_wait(
            self.topico, key=mensagem.key, value=mensagem.value, headers=headers
        )
