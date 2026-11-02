from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from contratos import EventoCargaAdapter, carregar_schema

RAIZ = Path(__file__).resolve().parents[3]
SCHEMA_SPEC = (
    RAIZ
    / "specs"
    / "001-pipeline-eventos-transportadora"
    / "contracts"
    / "evento-carga.schema.json"
)
FIXTURES_V1 = Path(__file__).parent / "fixtures" / "v1"

VALIDADOR = Draft202012Validator(carregar_schema(), format_checker=FormatChecker())


def test_schema_do_pacote_identico_ao_da_spec() -> None:
    assert carregar_schema() == json.loads(SCHEMA_SPEC.read_text(encoding="utf-8"))


def test_schema_e_valido() -> None:
    Draft202012Validator.check_schema(carregar_schema())


def test_modelo_gera_json_valido_no_schema(evento_valido: dict[str, Any]) -> None:
    evento = EventoCargaAdapter.validate_python(evento_valido)
    VALIDADOR.validate(EventoCargaAdapter.dump_python(evento, mode="json"))


def test_schema_rejeita_invalidos(evento_invalido: dict[str, Any]) -> None:
    assert list(VALIDADOR.iter_errors(evento_invalido)), "JSON Schema deveria rejeitar"


@pytest.mark.parametrize("arquivo", sorted(FIXTURES_V1.glob("*.json")), ids=lambda p: p.stem)
def test_fixtures_v1_continuam_validas(arquivo: Path) -> None:
    """Compatibilidade retroativa: eventos v1 publicados devem continuar válidos."""
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    VALIDADOR.validate(dados)
    EventoCargaAdapter.validate_python(dados)


def test_existe_fixture_para_cada_tipo() -> None:
    tipos = {json.loads(p.read_text())["event_type"] for p in FIXTURES_V1.glob("*.json")}
    assert tipos == set(carregar_schema()["properties"]["event_type"]["enum"])
