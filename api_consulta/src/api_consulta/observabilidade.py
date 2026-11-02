"""Logs estruturados, `correlation_id` e métricas Prometheus da API de consulta."""

from __future__ import annotations

import logging
import sys
import time
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

SERVICE = "api-consulta"
HEADER_CORRELACAO = "X-Correlation-ID"

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

EVENTOS_CONSUMIDOS = Counter(
    "consulta_eventos_consumidos_total", "Eventos aplicados na projeção", ["event_type"]
)
EVENTOS_DUPLICADOS = Counter("consulta_eventos_duplicados_total", "Eventos duplicados descartados")
EVENTOS_DLQ = Counter("consulta_eventos_dlq_total", "Mensagens enviadas ao DLQ", ["erro_tipo"])
EVENTOS_EXPIRADOS = Counter(
    "consulta_eventos_expirados_total", "Eventos removidos ou ignorados por retenção"
)
ERROS = Counter("consulta_erros_total", "Falhas no consumo do tópico ou no envio ao DLQ", ["tipo"])
LAG = Gauge("consulta_lag_mensagens", "Mensagens ainda não consumidas", ["particao"])
DURACAO = Histogram(
    "consulta_requisicao_duracao_segundos", "Latência das requisições HTTP", ["rota", "metodo"]
)


LOGGERS_UVICORN = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _adicionar_contexto(
    _logger: object, _metodo: str, evento: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    evento["service"] = SERVICE
    if (correlacao := correlation_id_var.get()) is not None:
        evento.setdefault("correlation_id", correlacao)
    return evento


def configurar_logs(nivel: str = "INFO") -> None:
    """Emite todos os logs (structlog e `logging` da stdlib: uvicorn, httpx, aiokafka) em JSON.

    Cada linha tem `timestamp` (UTC), `level`, `logger`, `service` e, quando houver,
    `correlation_id` (constituição, princípio V).
    """
    comuns: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        _adicionar_contexto,
    ]
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *comuns,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatador = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=comuns,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(formatador)
    raiz = logging.getLogger()
    raiz.handlers = [saida]
    raiz.setLevel(nivel.upper())
    # O uvicorn instala handlers próprios (texto) antes de criar a app: redireciona para a raiz.
    for nome in LOGGERS_UVICORN:
        logger = logging.getLogger(nome)
        logger.handlers = []
        logger.propagate = True


class MiddlewareObservabilidade(BaseHTTPMiddleware):
    """Lê ou gera o `X-Correlation-ID`, devolve-o na resposta e mede a latência."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Envolve a requisição com o identificador de correlação."""
        correlacao = request.headers.get(HEADER_CORRELACAO) or str(uuid.uuid4())
        token = correlation_id_var.set(correlacao)
        inicio = time.perf_counter()
        try:
            resposta = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        rota = getattr(request.scope.get("route"), "path", "desconhecida")
        DURACAO.labels(rota, request.method).observe(time.perf_counter() - inicio)
        resposta.headers[HEADER_CORRELACAO] = correlacao
        return resposta
