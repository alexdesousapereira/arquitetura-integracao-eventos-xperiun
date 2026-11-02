"""Aplicação FastAPI da API de controle da ingestão.

Execução: `uvicorn --factory controle_ingestao.main:criar_app`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI

from controle_ingestao.adapters.connect_client import ConnectClient
from controle_ingestao.adapters.pastas import Pastas
from controle_ingestao.api import ingestao, saude
from controle_ingestao.api.dependencias import VerificadorDependencias
from controle_ingestao.api.problemas import registrar_handlers
from controle_ingestao.config import ConfigControle
from controle_ingestao.observabilidade import MiddlewareObservabilidade, configurar_logs
from controle_ingestao.services.ingestao import ServicoIngestao


def criar_app(config: ConfigControle | None = None) -> FastAPI:
    """Cria a aplicação; sem argumento, lê a configuração do ambiente."""
    cfg = config or ConfigControle()
    configurar_logs(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            base_url=cfg.connect_url, timeout=cfg.timeout_connect_s
        ) as http:
            cliente = ConnectClient(http)
            app.state.servico = ServicoIngestao(
                cliente,
                cfg.conector_nome,
                cfg.conector_config_path,
                Pastas(cfg.pasta_eventos, cfg.pasta_backup, cfg.pasta_erros),
            )
            app.state.verificador = VerificadorDependencias(cliente, cfg.kafka_bootstrap)
            structlog.get_logger().info("api_iniciada", connect_url=cfg.connect_url)
            yield
            await app.state.servico.cancelar_vigias()

    app = FastAPI(
        title="API de Controle da Ingestão",
        version="1.0.0",
        description=(
            "Monitora e controla o conector Kafka Connect que ingere os arquivos de eventos da "
            "pasta `dados/eventos`. Rotas que alteram estado exigem o header `X-API-Key`."
        ),
        lifespan=lifespan,
    )
    app.state.config = cfg
    app.add_middleware(MiddlewareObservabilidade)
    registrar_handlers(app)
    app.include_router(ingestao.router)
    app.include_router(saude.router)
    return app
