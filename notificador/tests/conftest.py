from __future__ import annotations

import os
import uuid
from collections.abc import Callable

import pytest

from contratos import serializar_evento
from contratos.exemplo import evento_exemplo


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola os testes das variáveis exportadas pelo Makefile a partir do `.env`."""
    for nome in list(os.environ):
        if nome.startswith(("TELEGRAM_", "NOTIFICADOR_")):
            monkeypatch.delenv(nome)


def evento_bytes(pedido_id: str = "PED-0000E5E1", event_id: uuid.UUID | None = None) -> bytes:
    """Evento `pedido.criado` válido serializado, como chega do tópico."""
    evento = evento_exemplo(pedido_id)
    if event_id is not None:
        evento = evento.model_copy(update={"event_id": event_id})
    return serializar_evento(evento)


class CanalFalso:
    """Canal que guarda as mensagens e pode falhar nas primeiras tentativas."""

    nome = "falso"

    def __init__(self, falhas: list[Exception] | None = None) -> None:
        self.enviadas: list[str] = []
        self.tentativas = 0
        self.falhas = list(falhas or [])

    async def enviar(self, html: str) -> None:
        self.tentativas += 1
        if self.falhas:
            raise self.falhas.pop(0)
        self.enviadas.append(html)

    async def fechar(self) -> None: ...


@pytest.fixture
def gerar_evento() -> Callable[..., bytes]:
    return evento_bytes


@pytest.fixture
def canal_falso() -> type[CanalFalso]:
    return CanalFalso
