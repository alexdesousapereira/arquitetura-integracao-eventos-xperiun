"""O OpenAPI gerado pela aplicação deve corresponder ao contrato versionado em specs/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from controle_ingestao.config import ConfigControle
from controle_ingestao.main import criar_app

RAIZ = Path(__file__).resolve().parents[3]
CONTRATOS = RAIZ / "specs" / "001-pipeline-eventos-loja" / "contracts"
METODOS = {"get", "put", "post", "delete"}


def _operacoes(doc: dict[str, Any]) -> dict[tuple[str, str], set[str]]:
    return {
        (caminho, metodo): set(op["responses"])
        for caminho, item in doc["paths"].items()
        for metodo, op in item.items()
        if metodo in METODOS
    }


def _gerado() -> dict[str, Any]:
    return criar_app(ConfigControle(controle_api_key="x")).openapi()  # type: ignore[arg-type]


def test_paths_metodos_e_codigos_conferem() -> None:
    contrato = _operacoes(yaml.safe_load((CONTRATOS / "api-controle-ingestao.openapi.yaml").open()))
    gerado = _operacoes(_gerado())
    assert set(gerado) == set(contrato)
    for chave, codigos in contrato.items():
        assert codigos <= gerado[chave], chave
        assert gerado[chave] - codigos <= {"422"}, chave


def test_schemas_obrigatorios_conferem() -> None:
    contrato = yaml.safe_load((CONTRATOS / "api-controle-ingestao.openapi.yaml").open())
    gerado = _gerado()["components"]["schemas"]
    for nome in ("StatusIngestao", "Problema"):
        esperado = set(contrato["components"]["schemas"][nome]["required"])
        assert set(gerado[nome].get("required", [])) == esperado, nome


def test_rotas_mutaveis_declaram_api_key() -> None:
    doc = _gerado()
    assert doc["components"]["securitySchemes"]["ApiKey"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    for (caminho, metodo), _ in _operacoes(doc).items():
        op = doc["paths"][caminho][metodo]
        mutavel = caminho.startswith("/api/") and metodo != "get"
        assert bool(op.get("security")) is mutavel, (caminho, metodo, json.dumps(op)[:80])


def test_config_versionada_do_conector_igual_ao_contrato() -> None:
    contrato = json.loads((CONTRATOS / "conector-filepulse.json").read_text())
    operacional = json.loads(
        (RAIZ / "controle_ingestao" / "conectores" / "arquivos-eventos-loja.json").read_text()
    )
    assert operacional == contrato["config"]
