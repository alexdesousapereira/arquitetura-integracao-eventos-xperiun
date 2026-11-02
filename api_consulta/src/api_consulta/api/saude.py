"""Rotas de consumo, saúde e métricas."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from api_consulta.adapters.consumidor_kafka import StatusConsumo
from api_consulta.api.dependencias import Consumidor, obter_consumidor

router = APIRouter()
ConsumidorDep = Annotated[Consumidor, Depends(obter_consumidor)]


class Saude(BaseModel):
    """Estado de saúde do serviço e de suas dependências."""

    status: Literal["ok", "degradado", "indisponivel"]
    dependencias: dict[str, str] = {}


@router.get(
    "/api/v1/consumo/status",
    response_model=StatusConsumo,
    operation_id="obterStatusConsumo",
    tags=["consumo"],
)
async def status_consumo(consumidor: ConsumidorDep) -> StatusConsumo:
    """Status do consumo do tópico (lag por partição)."""
    return await consumidor.status_consumo()


@router.get("/health/live", response_model=Saude, operation_id="live", tags=["saude"])
async def live() -> Saude:
    """Processo vivo."""
    return Saude(status="ok")


@router.get(
    "/health/ready",
    response_model=Saude,
    operation_id="ready",
    tags=["saude"],
    responses={503: {"model": Saude, "description": "Não pronto"}},
)
async def ready(consumidor: ConsumidorDep) -> JSONResponse:
    """Pronto com o broker acessível e o catch-up inicial do tópico concluído."""
    deps = {
        "kafka": "ok" if consumidor.conectado else "indisponivel",
        "catch_up": "ok" if consumidor.catch_up_concluido else "em_andamento",
    }
    pronto = consumidor.conectado and consumidor.catch_up_concluido
    corpo = Saude(status="ok" if pronto else "indisponivel", dependencias=deps)
    return JSONResponse(corpo.model_dump(), status_code=200 if pronto else 503)


@router.get("/metrics", response_class=PlainTextResponse, operation_id="metrics", tags=["saude"])
async def metrics() -> Response:
    """Métricas no formato Prometheus."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
