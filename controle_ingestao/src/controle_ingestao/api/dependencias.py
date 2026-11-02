"""Dependências injetadas nas rotas (autenticação, serviços)."""

from __future__ import annotations

import asyncio
import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from controle_ingestao.adapters.connect_client import ConnectClient
from controle_ingestao.api.problemas import NaoAutorizadoError
from controle_ingestao.config import ConfigControle
from controle_ingestao.services.ingestao import ServicoIngestao

esquema_api_key = APIKeyHeader(name="X-API-Key", scheme_name="ApiKey", auto_error=False)


def obter_config(request: Request) -> ConfigControle:
    """Configuração carregada no startup."""
    config: ConfigControle = request.app.state.config
    return config


async def exigir_api_key(
    chave: Annotated[str | None, Depends(esquema_api_key)],
    config: Annotated[ConfigControle, Depends(obter_config)],
) -> None:
    """Rejeita a requisição se o header `X-API-Key` não conferir com `CONTROLE_API_KEY`."""
    esperada = config.controle_api_key.get_secret_value()
    if not chave or not secrets.compare_digest(chave.encode(), esperada.encode()):
        raise NaoAutorizadoError("Header X-API-Key ausente ou inválido")


def obter_servico(request: Request) -> ServicoIngestao:
    """Serviço de ingestão criado no `lifespan`."""
    servico: ServicoIngestao = request.app.state.servico
    return servico


class VerificadorDependencias:
    """Checa se o Kafka Connect e o broker Kafka estão acessíveis (readiness)."""

    def __init__(self, cliente: ConnectClient, kafka_bootstrap: str) -> None:
        self.cliente = cliente
        self.kafka_bootstrap = kafka_bootstrap

    async def _kafka_acessivel(self) -> bool:
        host, _, porta = self.kafka_bootstrap.split(",")[0].rpartition(":")
        try:
            _, escritor = await asyncio.wait_for(asyncio.open_connection(host, int(porta)), 2)
        except (OSError, TimeoutError, ValueError):
            return False
        escritor.close()
        await escritor.wait_closed()
        return True

    async def verificar(self) -> dict[str, bool]:
        """Retorna a disponibilidade de cada dependência."""
        connect, kafka = await asyncio.gather(self.cliente.ping(), self._kafka_acessivel())
        return {"kafka_connect": connect, "kafka": kafka}


def obter_verificador(request: Request) -> VerificadorDependencias:
    """Verificador de dependências criado no `lifespan`."""
    verificador: VerificadorDependencias = request.app.state.verificador
    return verificador
