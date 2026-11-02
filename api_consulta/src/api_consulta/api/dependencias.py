"""Dependências injetadas nas rotas."""

from __future__ import annotations

from typing import Protocol

from fastapi import Request

from api_consulta.adapters.consumidor_kafka import StatusConsumo
from api_consulta.services.projecao import Projecao


class Consumidor(Protocol):
    """Visão do consumidor usada pelas rotas."""

    conectado: bool
    catch_up_concluido: bool

    async def status_consumo(self) -> StatusConsumo:
        """Lag por partição."""
        ...


def obter_projecao(request: Request) -> Projecao:
    """Projeção criada no `lifespan`."""
    projecao: Projecao = request.app.state.projecao
    return projecao


def obter_consumidor(request: Request) -> Consumidor:
    """Consumidor criado no `lifespan`."""
    consumidor: Consumidor = request.app.state.consumidor
    return consumidor
