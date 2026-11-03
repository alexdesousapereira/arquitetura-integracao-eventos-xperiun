"""Imprime um evento válido como `<pedido_id>|<json>` (usado por `make publicar-evento-teste`)."""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime

from contratos.evento import (
    EventoCriado,
    Localidade,
    PayloadCriado,
    serializar_evento,
)


def evento_exemplo(pedido_id: str = "PED-0000E5E1") -> EventoCriado:
    """Evento `pedido.criado` com identificadores novos e horário atual."""
    return EventoCriado(
        event_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        source="make-publicar-evento-teste",
        correlation_id=uuid.uuid4(),
        pedido_id=pedido_id,
        payload=PayloadCriado(
            origem=Localidade(cidade="Campinas", uf="SP"),
            destino=Localidade(cidade="Curitiba", uf="PR"),
            peso_kg=120.0,
            descricao="Evento de teste",
            centro_distribuicao="CD-CAMPINAS",
        ),
    )


def main() -> int:
    """Escreve a linha chave|valor em stdout."""
    evento = evento_exemplo()
    sys.stdout.write(f"{evento.pedido_id}|{serializar_evento(evento).decode()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
