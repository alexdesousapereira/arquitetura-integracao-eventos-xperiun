"""Configuração da API de consulta (variáveis de ambiente)."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigConsulta(BaseSettings):
    """Parâmetros da API de consulta."""

    model_config = SettingsConfigDict(extra="ignore")

    kafka_bootstrap: str = "kafka:29092"
    topico_eventos: str = "loja.pedido.eventos.v1"
    topico_dlq: str = "loja.pedido.eventos-dlq.v1"
    catch_up_timeout_s: Annotated[float, Field(gt=0)] = 120
    retencao_projecao_s: Annotated[float, Field(gt=0)] = 900
    intervalo_expiracao_s: Annotated[float, Field(gt=0)] = 30
    log_level: str = "INFO"
