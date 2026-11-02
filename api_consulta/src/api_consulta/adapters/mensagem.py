"""Representação mínima de uma mensagem Kafka consumida (independente do cliente)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Mensagem:
    """Campos de um registro Kafka usados pelo processamento."""

    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes | None
    headers: Sequence[tuple[str, bytes]]

    def header(self, nome: str) -> str | None:
        """Valor do header como texto, se existir."""
        for chave, valor in self.headers:
            if chave == nome and valor is not None:
                return valor.decode("utf-8", errors="replace")
        return None
