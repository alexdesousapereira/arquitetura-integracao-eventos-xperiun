"""Rotas `/api/v1/ingestao`."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from controle_ingestao.api.dependencias import exigir_api_key, obter_servico
from controle_ingestao.api.problemas import doc_problema
from controle_ingestao.services.ingestao import ServicoIngestao, StatusIngestao

Respostas = dict[int | str, dict[str, Any]]

router = APIRouter(prefix="/api/v1/ingestao", tags=["ingestao"])
Servico = Annotated[ServicoIngestao, Depends(obter_servico)]
AUTENTICADO = [Depends(exigir_api_key)]

R401: Respostas = {401: doc_problema("Header X-API-Key ausente ou inválido")}
R404: Respostas = {404: doc_problema("Conector não existe; use PUT /api/v1/ingestao")}
R502: Respostas = {502: doc_problema("Kafka Connect rejeitou a operação")}
R503: Respostas = {503: doc_problema("Kafka Connect inacessível")}
ACAO = {
    "status_code": status.HTTP_202_ACCEPTED,
    "response_model": StatusIngestao,
    "dependencies": AUTENTICADO,
    "responses": {**R401, **R404, **R503},
}


@router.get("", response_model=StatusIngestao, operation_id="obterStatusIngestao", responses=R503)
async def obter_status(servico: Servico) -> StatusIngestao:
    """Status da ingestão (inclui `INEXISTENTE` se o conector não foi criado)."""
    return await servico.status()


@router.put(
    "",
    response_model=StatusIngestao,
    operation_id="ativarIngestao",
    dependencies=AUTENTICADO,
    responses={
        201: {"model": StatusIngestao, "description": "Conector criado"},
        **R401,
        **R502,
        **R503,
    },
)
async def ativar(servico: Servico, resposta: Response) -> StatusIngestao:
    """Cria ou atualiza (ativa) a ingestão com a configuração versionada."""
    st, criado = await servico.ativar()
    resposta.status_code = status.HTTP_201_CREATED if criado else status.HTTP_200_OK
    return st


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="removerIngestao",
    dependencies=AUTENTICADO,
    responses={**R401, **R503},
)
async def remover(servico: Servico) -> Response:
    """Remove a ingestão (idempotente)."""
    await servico.remover()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/pausar", operation_id="pausarIngestao", **ACAO)  # type: ignore[arg-type]
async def pausar(servico: Servico) -> StatusIngestao:
    """Pausa a ingestão (idempotente)."""
    return await servico.pausar()


@router.post("/retomar", operation_id="retomarIngestao", **ACAO)  # type: ignore[arg-type]
async def retomar(servico: Servico) -> StatusIngestao:
    """Retoma a ingestão pausada (idempotente)."""
    return await servico.retomar()


@router.post("/reiniciar", operation_id="reiniciarIngestao", **ACAO)  # type: ignore[arg-type]
async def reiniciar(servico: Servico) -> StatusIngestao:
    """Reinicia o conector e suas tarefas."""
    return await servico.reiniciar()
