"""Rotas de saúde e métricas."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from controle_ingestao.api.dependencias import VerificadorDependencias, obter_verificador

router = APIRouter(tags=["saude"])


class Saude(BaseModel):
    """Estado de saúde do serviço e de suas dependências."""

    status: Literal["ok", "degradado", "indisponivel"]
    dependencias: dict[str, Literal["ok", "indisponivel"]] = {}


@router.get("/health/live", response_model=Saude, operation_id="live")
async def live() -> Saude:
    """Processo vivo."""
    return Saude(status="ok")


@router.get(
    "/health/ready",
    response_model=Saude,
    operation_id="ready",
    responses={503: {"model": Saude, "description": "Dependência indisponível"}},
)
async def ready(
    verificador: Annotated[VerificadorDependencias, Depends(obter_verificador)],
) -> JSONResponse:
    """Pronto quando o Kafka Connect e o broker Kafka estão acessíveis (FR-011)."""
    deps = await verificador.verificar()
    pronto = all(deps.values())
    corpo = Saude(
        status="ok" if pronto else "indisponivel",
        dependencias={k: "ok" if v else "indisponivel" for k, v in deps.items()},
    )
    return JSONResponse(corpo.model_dump(), status_code=200 if pronto else 503)


@router.get("/metrics", response_class=PlainTextResponse, operation_id="metrics")
async def metrics() -> Response:
    """Métricas no formato Prometheus."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
