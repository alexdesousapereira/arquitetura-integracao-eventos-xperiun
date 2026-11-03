"""Configuração da API de controle (variáveis de ambiente)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigControle(BaseSettings):
    """Parâmetros da API de controle; `CONTROLE_API_KEY` é obrigatório."""

    model_config = SettingsConfigDict(extra="ignore")

    connect_url: str = "http://connect:8083"
    conector_nome: str = "arquivos-eventos-loja"
    conector_config_path: Path = Path("conectores/arquivos-eventos-loja.json")
    controle_api_key: SecretStr
    kafka_bootstrap: str = "kafka:29092"
    pasta_eventos: Path = Path("/data/eventos")
    pasta_backup: Path = Path("/data/backup")
    pasta_erros: Path = Path("/data/erros")
    timeout_connect_s: Annotated[float, Field(gt=0)] = 5.0
    log_level: str = "INFO"
