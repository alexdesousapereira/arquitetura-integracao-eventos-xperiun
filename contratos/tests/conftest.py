from __future__ import annotations

import copy
from typing import Any

import pytest

BASE: dict[str, Any] = {
    "event_id": "3f0c8a52-6b1e-4c5e-9d7a-2f1b8e4c9a10",
    "event_version": 1,
    "occurred_at": "2026-11-02T13:05:12.481Z",
    "source": "simulador-transportadora",
    "correlation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "carga_id": "CRG-1A2B3C4D",
}

PAYLOADS: dict[str, dict[str, Any]] = {
    "carga.recebida": {
        "origem": {"cidade": "Campinas", "uf": "SP"},
        "destino": {"cidade": "Belo Horizonte", "uf": "MG"},
        "peso_kg": 412.5,
        "descricao": "Eletrônicos - 12 volumes",
        "centro_distribuicao": "CD-CAMPINAS",
    },
    "carga.saiu_para_transporte": {
        "veiculo_id": "VEI-0042",
        "previsao_entrega": "2026-11-03T18:00:00Z",
    },
    "carga.em_transito": {
        "veiculo_id": "VEI-0042",
        "localizacao": {
            "latitude": -22.5,
            "longitude": -45.1,
            "cidade": "Pouso Alegre",
            "uf": "MG",
        },
    },
    "carga.saiu_para_entrega": {"veiculo_id": "VEI-0042", "tentativa": 1},
    "carga.entregue": {"tentativa": 1, "recebedor": "Ana Souza"},
    "carga.entrega_falhou": {"tentativa": 2, "motivo": "DESTINATARIO_AUSENTE"},
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
    "campo_extra_envelope": montar("carga.recebida", extra="x"),
    "carga_id_minusculo": montar("carga.recebida", carga_id="CRG-1a2b3c4d"),
    "carga_id_curto": montar("carga.recebida", carga_id="CRG-123"),
    "occurred_at_sem_z": montar("carga.recebida", occurred_at="2026-11-02T13:05:12+03:00"),
    "occurred_at_sem_fuso": montar("carga.recebida", occurred_at="2026-11-02T13:05:12"),
    "event_version_2": montar("carga.recebida", event_version=2),
    "event_type_desconhecido": montar("carga.recebida", event_type="carga.perdida"),
    "payload_de_outro_tipo": {**montar("carga.entregue"), "payload": PAYLOADS["carga.recebida"]},
    "peso_zero": _com_payload("carga.recebida", peso_kg=0),
    "peso_acima": _com_payload("carga.recebida", peso_kg=30000.01),
    "descricao_longa": _com_payload("carga.recebida", descricao="x" * 201),
    "uf_invalida": _com_payload("carga.recebida", origem={"cidade": "Campinas", "uf": "sp"}),
    "tentativa_zero": _com_payload("carga.saiu_para_entrega", tentativa=0),
    "tentativa_quatro": _com_payload("carga.entrega_falhou", tentativa=4),
    "motivo_invalido": _com_payload("carga.entrega_falhou", motivo="CHUVA"),
    "veiculo_invalido": _com_payload("carga.em_transito", veiculo_id="V-1"),
    "latitude_fora": _com_payload(
        "carga.em_transito",
        localizacao={"latitude": 91, "longitude": 0, "cidade": "X", "uf": "SP"},
    ),
    "recebedor_longo": _com_payload("carga.entregue", recebedor="x" * 101),
    "sem_carga_id": {k: v for k, v in montar("carga.recebida").items() if k != "carga_id"},
}


@pytest.fixture(params=sorted(INVALIDOS))
def evento_invalido(request: pytest.FixtureRequest) -> dict[str, Any]:
    return INVALIDOS[request.param]
