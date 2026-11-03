"""Respostas de erro no formato RFC 9457 (Problem Details)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from controle_ingestao.adapters.connect_client import (
    ConectorInexistenteError,
    ConnectErroError,
    ConnectIndisponivelError,
)
from controle_ingestao.observabilidade import correlation_id_var
from controle_ingestao.services.ingestao import IngestaoInexistenteError

TIPO_BASE = "https://loja.local/problemas/"
MEDIA_TYPE = "application/problem+json"


class Problema(BaseModel):
    """RFC 9457 Problem Details."""

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    correlation_id: str | None = None


class NaoAutorizadoError(Exception):
    """Header `X-API-Key` ausente ou inválido."""


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

    @app.exception_handler(NaoAutorizadoError)
    async def _nao_autorizado(request: Request, exc: NaoAutorizadoError) -> JSONResponse:
        return resposta_problema(request, 401, "nao-autorizado", "Não autorizado", str(exc))

    @app.exception_handler(IngestaoInexistenteError)
    @app.exception_handler(ConectorInexistenteError)
    async def _inexistente(request: Request, exc: Exception) -> JSONResponse:
        return resposta_problema(
            request,
            404,
            "ingestao-inexistente",
            "Ingestão inexistente",
            "O conector não existe; ative-o com PUT /api/v1/ingestao.",
        )

    @app.exception_handler(ConnectIndisponivelError)
    async def _indisponivel(request: Request, exc: ConnectIndisponivelError) -> JSONResponse:
        return resposta_problema(
            request, 503, "connect-indisponivel", "Kafka Connect indisponível", str(exc)
        )

    @app.exception_handler(ConnectErroError)
    async def _erro_connect(request: Request, exc: ConnectErroError) -> JSONResponse:
        return resposta_problema(
            request, 502, "connect-erro", "Kafka Connect rejeitou a operação", exc.detalhe
        )

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
        return resposta_problema(
            request, 422, "parametro-invalido", "Parâmetro inválido", str(exc.errors())
        )

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        return resposta_problema(request, exc.status_code, "http", str(exc.detail))
