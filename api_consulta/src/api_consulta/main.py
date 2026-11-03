"""Aplicação FastAPI da API de consulta de pedidos.

Execução: `uvicorn --factory api_consulta.main:criar_app`.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import structlog
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI

from api_consulta.adapters.consumidor_kafka import ConsumidorEventos
from api_consulta.adapters.produtor_dlq import ProdutorDLQ
from api_consulta.api import pedidos, saude
from api_consulta.api.problemas import registrar_handlers
from api_consulta.config import ConfigConsulta
from api_consulta.observabilidade import (
    EVENTOS_EXPIRADOS,
    MiddlewareObservabilidade,
    configurar_logs,
)
from api_consulta.services.processador import Processador
from api_consulta.services.projecao import Projecao

log = structlog.get_logger()


async def _expirar_periodicamente(projecao: Projecao, intervalo_s: float) -> None:
    while True:
        await asyncio.sleep(intervalo_s)
        if removidos := projecao.expirar():
            EVENTOS_EXPIRADOS.inc(removidos)
            log.info("eventos_expirados", removidos=removidos)


def criar_app(config: ConfigConsulta | None = None) -> FastAPI:
    """Cria a aplicação; sem argumento, lê a configuração do ambiente."""
    cfg = config or ConfigConsulta()
    configurar_logs(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        projecao = Projecao(timedelta(seconds=cfg.retencao_projecao_s))
        producer = AIOKafkaProducer(
            bootstrap_servers=cfg.kafka_bootstrap, acks="all", enable_idempotence=True
        )
        processador = Processador(projecao, ProdutorDLQ(producer, cfg.topico_dlq))
        consumidor = ConsumidorEventos(cfg, processador, producer)
        app.state.projecao = projecao
        app.state.consumidor = consumidor
        tarefas = [
            asyncio.create_task(consumidor.executar(), name="consumo"),
            asyncio.create_task(
                _expirar_periodicamente(projecao, cfg.intervalo_expiracao_s), name="expiracao"
            ),
        ]
        log.info("api_iniciada", topico=cfg.topico_eventos, retencao_s=cfg.retencao_projecao_s)
        try:
            yield
        finally:
            for tarefa in tarefas:
                tarefa.cancel()
            for tarefa in tarefas:
                with contextlib.suppress(asyncio.CancelledError):
                    await tarefa
            await consumidor.parar()

    app = FastAPI(
        title="API de Consulta de Pedidos",
        version="1.0.0",
        description=(
            "Consome o tópico `loja.pedido.eventos.v1` e expõe o status atual, o "
            "histórico de eventos e indicadores agregados dos pedidos. Dados mantidos em memória, "
            "limitados à mesma janela de retenção do tópico (15 min, pelo `occurred_at`)."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(MiddlewareObservabilidade)
    registrar_handlers(app)
    app.include_router(pedidos.router)
    app.include_router(saude.router)
    return app
