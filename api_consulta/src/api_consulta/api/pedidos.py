"""Rotas de consulta de pedidos: `/api/v1/pedidos` e `/api/v1/resumo`."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from api_consulta.api.dependencias import obter_projecao
from api_consulta.api.problemas import doc_problema
from api_consulta.services.projecao import PaginaPedidos, Pedido, Projecao, Resumo
from contratos import EventoPedido, StatusPedido, formatar_mensagem

Respostas = dict[int | str, dict[str, Any]]

router = APIRouter(prefix="/api/v1", tags=["pedidos"])
ProjecaoDep = Annotated[Projecao, Depends(obter_projecao)]
PedidoId = Annotated[str, Path(pattern=r"^PED-[0-9A-F]{8}$")]

R404: Respostas = {
    404: doc_problema(
        "Pedido não encontrada (inexistente ou com todos os eventos fora da janela de retenção)"
    )
}
R422: Respostas = {422: doc_problema("Parâmetro inválido")}


class HistoricoPedido(BaseModel):
    """Eventos de um pedido em ordem cronológica."""

    pedido_id: str
    eventos: list[EventoPedido]


@router.get("/pedidos", response_model=PaginaPedidos, operation_id="listarPedidos", responses=R422)
async def listar_pedidos(
    projecao: ProjecaoDep,
    status: StatusPedido | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PaginaPedidos:
    """Lista pedidos com filtro opcional por status (mais recentes primeiro)."""
    return projecao.listar(status, page, size)


@router.get(
    "/pedidos/{pedido_id}",
    response_model=Pedido,
    operation_id="obterPedido",
    responses={**R404, **R422},
)
async def obter_pedido(projecao: ProjecaoDep, pedido_id: PedidoId) -> Pedido:
    """Detalhe e status atual de um pedido."""
    return projecao.obter_pedido(pedido_id)


@router.get(
    "/pedidos/{pedido_id}/eventos",
    response_model=HistoricoPedido,
    operation_id="listarEventosPedido",
    responses={**R404, **R422},
)
async def listar_eventos(projecao: ProjecaoDep, pedido_id: PedidoId) -> HistoricoPedido:
    """Histórico de eventos do pedido em ordem cronológica."""
    return HistoricoPedido(pedido_id=pedido_id, eventos=projecao.historico(pedido_id))


@router.get("/resumo", response_model=Resumo, operation_id="obterResumo")
async def obter_resumo(projecao: ProjecaoDep) -> Resumo:
    """Indicadores agregados."""
    return projecao.resumo()


class MensagemCanal(BaseModel):
    """Um aviso por event_id, pronto para envio com parse_mode=HTML."""

    event_id: str
    pedido_id: str
    html: str


@router.get("/pedidos/{pedido_id}/mensagens", response_model=list[MensagemCanal])
async def listar_mensagens(projecao: ProjecaoDep, pedido_id: PedidoId) -> list[MensagemCanal]:
    """Mensagens do pedido, sem duplicatas e em ordem cronológica."""
    return [
        MensagemCanal(event_id=str(e.event_id), pedido_id=e.pedido_id, html=formatar_mensagem(e))
        for e in projecao.historico(pedido_id)
    ]
