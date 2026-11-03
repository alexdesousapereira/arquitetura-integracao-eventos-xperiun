# syntax=docker/dockerfile:1
# Contexto de build: raiz do repositório.
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
COPY controle_ingestao/src controle_ingestao/src
RUN uv sync --frozen --no-dev --no-editable --package controle-ingestao

FROM python:3.12.16-slim-trixie
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY controle_ingestao/conectores /app/conectores
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=2)"]
CMD ["uvicorn", "--factory", "controle_ingestao.main:criar_app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
