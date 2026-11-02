"""Rotas de consulta de cargas: `/api/v1/cargas` e `/api/v1/resumo`."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from api_consulta.api.dependencias import obter_projecao
from api_consulta.api.problemas import doc_problema
from api_consulta.services.projecao import Carga, PaginaCargas, Projecao, Resumo
from contratos import EventoCarga, StatusCarga

Respostas = dict[int | str, dict[str, Any]]

router = APIRouter(prefix="/api/v1", tags=["cargas"])
ProjecaoDep = Annotated[Projecao, Depends(obter_projecao)]
CargaId = Annotated[str, Path(pattern=r"^CRG-[0-9A-F]{8}$")]

R404: Respostas = {
    404: doc_problema(
        "Carga não encontrada (inexistente ou com todos os eventos fora da janela de retenção)"
    )
}
R422: Respostas = {422: doc_problema("Parâmetro inválido")}


class HistoricoCarga(BaseModel):
    """Eventos de uma carga em ordem cronológica."""

    carga_id: str
    eventos: list[EventoCarga]


@router.get("/cargas", response_model=PaginaCargas, operation_id="listarCargas", responses=R422)
async def listar_cargas(
    projecao: ProjecaoDep,
    status: StatusCarga | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PaginaCargas:
    """Lista cargas com filtro opcional por status (mais recentes primeiro)."""
    return projecao.listar(status, page, size)


@router.get(
    "/cargas/{carga_id}",
    response_model=Carga,
    operation_id="obterCarga",
    responses={**R404, **R422},
)
async def obter_carga(projecao: ProjecaoDep, carga_id: CargaId) -> Carga:
    """Detalhe e status atual de uma carga."""
    return projecao.obter_carga(carga_id)


@router.get(
    "/cargas/{carga_id}/eventos",
    response_model=HistoricoCarga,
    operation_id="listarEventosCarga",
    responses={**R404, **R422},
)
async def listar_eventos(projecao: ProjecaoDep, carga_id: CargaId) -> HistoricoCarga:
    """Histórico de eventos da carga em ordem cronológica."""
    return HistoricoCarga(carga_id=carga_id, eventos=projecao.historico(carga_id))


@router.get("/resumo", response_model=Resumo, operation_id="obterResumo")
async def obter_resumo(projecao: ProjecaoDep) -> Resumo:
    """Indicadores agregados."""
    return projecao.resumo()
