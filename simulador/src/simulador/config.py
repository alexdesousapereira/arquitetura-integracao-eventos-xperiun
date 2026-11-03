"""Configuração do simulador (variáveis de ambiente `SIMULADOR_*`)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigSimulador(BaseSettings):
    """Parâmetros da simulação; a CLI sobrepõe os valores vindos do ambiente."""

    model_config = SettingsConfigDict(env_prefix="SIMULADOR_", extra="ignore")

    pedidos: Annotated[int, Field(ge=1)] = 3
    intervalo_ms: Annotated[int, Field(ge=10)] = 500
    duracao_s: Annotated[int, Field(ge=0)] = 0
    max_eventos: Annotated[int, Field(ge=1)] = 10
    continuo: bool = False
    saida: Path = Path("dados/eventos")
    seed: int | None = None
    prob_falha: Annotated[float, Field(ge=0, le=1)] = 0.15
    metrics_port: Annotated[int, Field(ge=0, le=65535)] = 0
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
