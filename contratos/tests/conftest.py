from __future__ import annotations

import copy
from typing import Any

import pytest

BASE: dict[str, Any] = {
    "event_id": "3f0c8a52-6b1e-4c5e-9d7a-2f1b8e4c9a10",
    "event_version": 1,
    "occurred_at": "2026-11-02T13:05:12.481Z",
    "source": "simulador-loja",
    "correlation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "pedido_id": "PED-1A2B3C4D",
}

PAYLOADS: dict[str, dict[str, Any]] = {
    "pedido.criado": {
        "origem": {"cidade": "Campinas", "uf": "SP"},
        "destino": {"cidade": "Belo Horizonte", "uf": "MG"},
        "peso_kg": 412.5,
        "descricao": "Eletrônicos - 12 volumes",
        "centro_distribuicao": "CD-CAMPINAS",
    },
    "pedido.enviado": {
        "veiculo_id": "VEI-0042",
        "previsao_entrega": "2026-11-03T18:00:00Z",
    },
    "pedido.em_transito": {
        "veiculo_id": "VEI-0042",
        "localizacao": {
            "latitude": -22.5,
            "longitude": -45.1,
            "cidade": "Pouso Alegre",
            "uf": "MG",
        },
    },
    "pedido.saiu_para_entrega": {"veiculo_id": "VEI-0042", "tentativa": 1},
    "pedido.entregue": {"tentativa": 1, "recebedor": "Ana Souza"},
    "pedido.entrega_falhou": {"tentativa": 2, "motivo": "DESTINATARIO_AUSENTE"},
}


def montar(tipo: str, **overrides: Any) -> dict[str, Any]:
    evento = copy.deepcopy(BASE)
    evento["event_type"] = tipo
    evento["payload"] = copy.deepcopy(PAYLOADS[tipo])
    evento.update(overrides)
    return evento


@pytest.fixture(params=sorted(PAYLOADS))
def evento_valido(request: pytest.FixtureRequest) -> dict[str, Any]:
    return montar(request.param)


def _com_payload(tipo: str, **campos: Any) -> dict[str, Any]:
    evento = montar(tipo)
    evento["payload"].update(campos)
    return evento


INVALIDOS: dict[str, dict[str, Any]] = {
    "campo_extra_envelope": montar("pedido.criado", extra="x"),
    "pedido_id_minusculo": montar("pedido.criado", pedido_id="PED-1a2b3c4d"),
    "pedido_id_curto": montar("pedido.criado", pedido_id="PED-123"),
    "occurred_at_sem_z": montar("pedido.criado", occurred_at="2026-11-02T13:05:12+03:00"),
    "occurred_at_sem_fuso": montar("pedido.criado", occurred_at="2026-11-02T13:05:12"),
    "event_version_2": montar("pedido.criado", event_version=2),
    "event_type_desconhecido": montar("pedido.criado", event_type="pedido.perdida"),
    "payload_de_outro_tipo": {**montar("pedido.entregue"), "payload": PAYLOADS["pedido.criado"]},
    "peso_zero": _com_payload("pedido.criado", peso_kg=0),
    "peso_acima": _com_payload("pedido.criado", peso_kg=30000.01),
    "descricao_longa": _com_payload("pedido.criado", descricao="x" * 201),
    "uf_invalida": _com_payload("pedido.criado", origem={"cidade": "Campinas", "uf": "sp"}),
    "tentativa_zero": _com_payload("pedido.saiu_para_entrega", tentativa=0),
    "tentativa_quatro": _com_payload("pedido.entrega_falhou", tentativa=4),
    "motivo_invalido": _com_payload("pedido.entrega_falhou", motivo="CHUVA"),
    "veiculo_invalido": _com_payload("pedido.em_transito", veiculo_id="V-1"),
    "latitude_fora": _com_payload(
        "pedido.em_transito",
        localizacao={"latitude": 91, "longitude": 0, "cidade": "X", "uf": "SP"},
    ),
    "recebedor_longo": _com_payload("pedido.entregue", recebedor="x" * 101),
    "sem_pedido_id": {k: v for k, v in montar("pedido.criado").items() if k != "pedido_id"},
}


@pytest.fixture(params=sorted(INVALIDOS))
def evento_invalido(request: pytest.FixtureRequest) -> dict[str, Any]:
    return INVALIDOS[request.param]
