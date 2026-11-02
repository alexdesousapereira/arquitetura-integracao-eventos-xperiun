"""O OpenAPI gerado pela aplicação deve corresponder ao contrato versionado em specs/."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from api_consulta.api.dependencias import obter_consumidor, obter_projecao
from api_consulta.config import ConfigConsulta
from api_consulta.main import criar_app
from api_consulta.services.projecao import Projecao
from contratos import carregar_schema

RAIZ = Path(__file__).resolve().parents[3]
CONTRATO = (
    RAIZ
    / "specs"
    / "001-pipeline-eventos-transportadora"
    / "contracts"
    / "api-consulta.openapi.yaml"
)
METODOS = {"get", "put", "post", "delete"}


def _operacoes(doc: dict[str, Any]) -> dict[tuple[str, str], set[str]]:
    return {
        (caminho, metodo): set(op["responses"])
        for caminho, item in doc["paths"].items()
        for metodo, op in item.items()
        if metodo in METODOS
    }


def _gerado() -> dict[str, Any]:
    return criar_app(ConfigConsulta()).openapi()


def test_paths_metodos_e_codigos_conferem() -> None:
    contrato = _operacoes(yaml.safe_load(CONTRATO.open()))
    gerado = _operacoes(_gerado())
    assert set(gerado) == set(contrato)
    for chave, codigos in contrato.items():
        assert codigos <= gerado[chave], chave
        assert gerado[chave] - codigos <= {"422"}, chave


def test_parametros_conferem() -> None:
    contrato = yaml.safe_load(CONTRATO.open())
    gerado = _gerado()
    params = {p["name"] for p in gerado["paths"]["/api/v1/cargas"]["get"]["parameters"]}
    esperado = {p["name"] for p in contrato["paths"]["/api/v1/cargas"]["get"]["parameters"]}
    assert params == esperado


def test_schemas_obrigatorios_conferem() -> None:
    contrato = yaml.safe_load(CONTRATO.open())["components"]["schemas"]
    gerado = _gerado()["components"]["schemas"]
    for nome in ("Carga", "PaginaCargas", "Resumo", "StatusConsumo", "Problema"):
        assert set(gerado[nome].get("required", [])) == set(contrato[nome]["required"]), nome
    assert set(gerado["StatusCarga"]["enum"]) == set(contrato["StatusCarga"]["enum"])


async def test_eventos_do_historico_validam_no_json_schema(relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    projecao = Projecao(timedelta(minutes=15), agora=relogio)
    eventos = gerar_jornada(1, inicio=relogio() - timedelta(minutes=1), prob_falha=0.5)
    for evento in eventos:
        projecao.aplicar(evento)
    app = criar_app(ConfigConsulta())
    app.dependency_overrides[obter_projecao] = lambda: projecao
    app.dependency_overrides[obter_consumidor] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/v1/cargas/{eventos[0].carga_id}/eventos")
    validador = Draft202012Validator(carregar_schema(), format_checker=FormatChecker())
    for item in r.json()["eventos"]:
        validador.validate(item)
