"""Configuração do notificador (variáveis de ambiente)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigNotificador(BaseSettings):
    """Parâmetros do notificador. Sem token e chat do Telegram, roda em modo demonstração."""

    model_config = SettingsConfigDict(extra="ignore")

    kafka_bootstrap: str = "kafka:29092"
    topico_eventos: str = "loja.pedido.eventos.v1"
    notificador_grupo: str = "notificador"
    # Só vale na primeira vez que o grupo conecta; depois o Kafka retoma do offset commitado.
    notificador_offset_inicial: Literal["latest", "earliest"] = "latest"
    notificador_intervalo_s: Annotated[float, Field(ge=0)] = 1.0
    notificador_metrics_port: Annotated[int, Field(ge=0, le=65535)] = 9100
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    telegram_api_url: str = "https://api.telegram.org"
    log_level: str = "INFO"

    @property
    def telegram_configurado(self) -> bool:
        """Verdadeiro quando há token e chat para envio real."""
        return bool(self.telegram_bot_token.get_secret_value() and self.telegram_chat_id)
