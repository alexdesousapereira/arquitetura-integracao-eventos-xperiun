from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from contratos import (
    STATUS_POR_TIPO,
    EventoCriado,
    EventoEntregue,
    EventoPedidoAdapter,
    StatusPedido,
    TipoEvento,
    parse_evento,
)


def test_aceita_evento_valido(evento_valido: dict[str, Any]) -> None:
    evento = EventoPedidoAdapter.validate_python(evento_valido)
    assert evento.event_type == evento_valido["event_type"]
    assert evento.pedido_id == "PED-1A2B3C4D"
    assert isinstance(evento.event_id, UUID)


def test_rejeita_evento_invalido(evento_invalido: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EventoPedidoAdapter.validate_python(evento_invalido)


def test_occurred_at_normalizado_para_utc_com_z(evento_valido: dict[str, Any]) -> None:
    evento = EventoPedidoAdapter.validate_python(evento_valido)
    assert evento.occurred_at.tzinfo is not None
    assert evento.occurred_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    dump = EventoPedidoAdapter.dump_python(evento, mode="json")
    assert dump["occurred_at"].endswith("Z")


def test_roundtrip_json(evento_valido: dict[str, Any]) -> None:
    evento = parse_evento(json.dumps(evento_valido))
    recarregado = parse_evento(EventoPedidoAdapter.dump_json(evento))
    assert recarregado == evento


def test_parse_evento_aceita_bytes(evento_valido: dict[str, Any]) -> None:
    assert parse_evento(json.dumps(evento_valido).encode()).pedido_id == "PED-1A2B3C4D"


def test_parse_evento_rejeita_json_malformado() -> None:
    with pytest.raises(ValidationError):
        parse_evento(b"{ quebrado")


def test_eventos_sao_imutaveis(evento_valido: dict[str, Any]) -> None:
    evento = EventoPedidoAdapter.validate_python(evento_valido)
    with pytest.raises(ValidationError):
        evento.pedido_id = "PED-FFFFFFFF"  # type: ignore[misc]


def test_construcao_direta_tipada() -> None:
    evento = EventoEntregue(
        event_id=UUID("3f0c8a52-6b1e-4c5e-9d7a-2f1b8e4c9a10"),
        occurred_at=datetime(2026, 11, 2, 13, 0, tzinfo=UTC),
        source="teste",
        correlation_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"),
        pedido_id="PED-00000001",
        payload={"tentativa": 1, "recebedor": "Ana"},  # type: ignore[arg-type]
    )
    assert evento.event_type == TipoEvento.ENTREGUE
    assert evento.event_version == 1


def test_mapeamento_status_cobre_todos_os_tipos() -> None:
    assert set(STATUS_POR_TIPO) == set(TipoEvento)
    assert STATUS_POR_TIPO[TipoEvento.CRIADO] is StatusPedido.CRIADO
    assert STATUS_POR_TIPO[TipoEvento.ENTREGA_FALHOU] is StatusPedido.FALHA_ENTREGA


def test_tipo_do_modelo_criado() -> None:
    assert EventoCriado.model_fields["event_type"].default == TipoEvento.CRIADO
