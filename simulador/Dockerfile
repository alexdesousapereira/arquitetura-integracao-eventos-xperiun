# syntax=docker/dockerfile:1
# Contexto de build: raiz do repositório (inclui o pacote compartilhado `contratos`).
FROM python:3.12.16-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY contratos/pyproject.toml contratos/pyproject.toml
COPY simulador/pyproject.toml simulador/pyproject.toml
COPY controle_ingestao/pyproject.toml controle_ingestao/pyproject.toml
COPY api_consulta/pyproject.toml api_consulta/pyproject.toml
COPY notificador/pyproject.toml notificador/pyproject.toml
COPY contratos/src contratos/src
COPY simulador/src simulador/src
RUN uv sync --frozen --no-dev --no-editable --package simulador

FROM python:3.12.16-slim-trixie
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SIMULADOR_SAIDA=/app/dados/eventos
USER app
ENTRYPOINT ["python", "-m", "simulador"]
