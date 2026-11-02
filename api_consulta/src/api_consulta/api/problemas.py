"""Respostas de erro no formato RFC 9457 (Problem Details)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from api_consulta.observabilidade import correlation_id_var
from api_consulta.services.projecao import CargaNaoEncontradaError

TIPO_BASE = "https://transportadora.local/problemas/"
MEDIA_TYPE = "application/problem+json"


class Problema(BaseModel):
    """RFC 9457 Problem Details."""

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    correlation_id: str | None = None


def resposta_problema(
    request: Request, status: int, tipo: str, titulo: str, detalhe: str | None = None
) -> JSONResponse:
    """Monta a resposta `application/problem+json`."""
    corpo = Problema(
        type=f"{TIPO_BASE}{tipo}",
        title=titulo,
        status=status,
        detail=detalhe,
        instance=request.url.path,
        correlation_id=correlation_id_var.get(),
    )
    return JSONResponse(
        corpo.model_dump(exclude_none=True), status_code=status, media_type=MEDIA_TYPE
    )


def doc_problema(descricao: str) -> dict[str, Any]:
    """Entrada de `responses` para o OpenAPI de uma resposta de erro."""
    return {
        "description": descricao,
        "model": Problema,
        "content": {MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problema"}}},
    }


def registrar_handlers(app: FastAPI) -> None:
    """Traduz exceções de domínio e do framework para Problem Details."""

    @app.exception_handler(CargaNaoEncontradaError)
    async def _nao_encontrada(request: Request, exc: CargaNaoEncontradaError) -> JSONResponse:
        return resposta_problema(
            request,
            404,
            "carga-nao-encontrada",
            "Carga não encontrada",
            f"A carga {exc} não existe ou todos os seus eventos saíram da janela de retenção.",
        )

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
        detalhe = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return resposta_problema(request, 422, "parametro-invalido", "Parâmetro inválido", detalhe)

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        return resposta_problema(request, exc.status_code, "http", str(exc.detail))
