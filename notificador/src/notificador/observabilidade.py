"""Logs estruturados e métricas Prometheus do notificador."""

from __future__ import annotations

import logging
import sys

import structlog
from prometheus_client import Counter, start_http_server

SERVICE = "notificador"

MENSAGENS_ENVIADAS = Counter(
    "notificador_mensagens_enviadas_total", "Mensagens entregues ao canal", ["event_type", "canal"]
)
EVENTOS_IGNORADOS = Counter(
    "notificador_eventos_ignorados_total", "Eventos consumidos sem envio", ["motivo"]
)
FALHAS_ENVIO = Counter(
    "notificador_falhas_envio_total", "Tentativas de envio sem sucesso", ["tipo"]
)


def configurar_logs(nivel: str = "INFO") -> None:
    """Configura `structlog` para emitir JSON em stdout com `timestamp`, `level` e `service`."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=nivel.upper())
    # O httpx registra a URL de cada requisição, e a URL da API do Telegram contém o token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(nivel.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=SERVICE)


def iniciar_servidor_metricas(porta: int) -> None:
    """Expõe `/metrics` na porta indicada (0 desliga)."""
    if porta > 0:
        start_http_server(porta)
