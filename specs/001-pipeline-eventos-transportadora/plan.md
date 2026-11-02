# Implementation Plan: Pipeline de Eventos da Transportadora

**Branch**: `001-pipeline-eventos-transportadora` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-pipeline-eventos-transportadora/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Pipeline orientado a eventos, executado localmente em Docker, que simula o ciclo de vida de cargas
de uma transportadora. Um **simulador Python** grava cada evento como arquivo JSON (escrita
atômica) em `dados/eventos`; o **Kafka Connect** com o conector **FilePulse** ingere os arquivos,
move-os para `dados/backup`/`dados/erros` e publica no tópico
`transportadora.carga.eventos.v1` (Kafka KRaft, 1 broker, retenção de 15 min) usando `carga_id`
como chave. Uma **API FastAPI de controle** opera o conector (status, ativar, pausar, retomar,
reiniciar, remover) via REST do Connect — e se autorrecupera da falha conhecida do FilePulse ao
parar a instância do conector (research R1) —, e uma **API FastAPI de consulta** consome o tópico com
`aiokafka`, mantém uma projeção em memória limitada à janela de retenção de 15 min (com deduplicação, expiração periódica e DLQ para eventos fora do contrato)
e expõe status, histórico e resumo das cargas. Um contrato de evento único (JSON Schema +
modelos Pydantic) é compartilhado via uv workspace. Detalhes em [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Uvicorn, Pydantic v2, pydantic-settings, httpx, aiokafka,
structlog, prometheus-client; Apache Kafka 3.9 (Confluent Platform 7.9.10, KRaft); Kafka Connect
7.9.10 + `streamthoughts/kafka-connect-file-pulse` 2.18.0 (zip oficial validado por SHA-256); imagens base `python:3.12.16-slim-trixie`
e `ghcr.io/astral-sh/uv:0.13.6`; scanner `aquasec/trivy:0.76.1`

**Storage**: Arquivos JSON em `dados/` (bind mount) como origem; tópicos Kafka (retenção 15 min);
projeção em memória na API de consulta. Sem banco de dados.

**Testing**: pytest, pytest-asyncio, pytest-cov, respx (mock httpx), jsonschema (contrato),
testcontainers[kafka] (integração), suíte e2e contra o `docker compose`

**Target Platform**: Containers Linux (amd64/arm64) via Docker Compose v2 em máquina de
desenvolvimento (macOS/Linux)

**Project Type**: Monorepo com 3 serviços (CLI simulador + 2 web services) + 1 biblioteca de
contratos + infraestrutura Docker

**Performance Goals**: volume de simulação (~10 cargas, até 500 eventos) entregue 100% sem perda
(SC-003); evento visível na API em ≤ 60 s p95 (SC-002); ingestão de arquivo novo ≤ 30 s; consultas
< 1 s com algumas centenas de cargas (SC-008). Testes de carga/estresse fora do escopo.

**Constraints**: Cluster com 1 broker (RF=1); retenção de 15 min observável; nenhum container
como root; tags de imagem fixas; ambiente sobe com um comando; ~4 GB de RAM

**Scale/Scope**: Simulação local com volumes pequenos (dezenas de cargas, centenas de eventos);
6 tipos de evento; ~12 endpoints no total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Princípio | Como o plano atende | Pré | Pós |
|---|-----------|---------------------|-----|-----|
| I | Eventos e contratos | JSON Schema versionado ([evento-carga.schema.json](./contracts/evento-carga.schema.json)); envelope com `event_id`, `event_type`, `event_version`, `occurred_at` UTC, `source`, `correlation_id`; chave `carga_id`; tópicos `transportadora.carga.eventos.v1` / `...eventos-dlq.v1` com partições/retenção/RF declarados; dedup por `event_id`; arquivos inválidos → `dados/erros`, eventos fora do contrato → DLQ; config do conector versionada ([conector-filepulse.json](./contracts/conector-filepulse.json)) e aplicada via REST | ✅ | ✅ |
| II | APIs FastAPI | Pydantic v2 em todos os modelos; `APIRouter` por domínio em `/api/v1`; OpenAPI versionado em `contracts/` com teste de snapshot; RFC 9457; `httpx`/`aiokafka` assíncronos; `/health/live` e `/health/ready` checando dependências; `pydantic-settings`; camadas `api` → `services` → `adapters` | ✅ | ✅ |
| III | Qualidade Python | Python 3.12, uv workspace + `uv.lock`, `ruff` (lint+format, regras `D` para docstrings e `T20` contra `print`), `mypy --strict`, logging estruturado, sem segredos no código (`.env`) | ✅ | ✅ |
| IV | Testes em camadas | Unit, contract (JSON Schema + snapshot OpenAPI), integração (testcontainers Kafka), e2e (compose); cobertura ≥ 80% em domínio/serviços | ✅ | ✅ |
| V | Observabilidade | `structlog` JSON com `event_id`/`correlation_id`; `correlation_id` no evento → header Kafka (SMT `HeaderFrom`) → logs/erros da API; `/metrics` Prometheus em todos os serviços; status de cada etapa e lag consultáveis | ✅ | ✅ |
| VI | Docker como código | Compose único; Kafka KRaft; imagens com tag fixa, multi-stage, `python:3.12.16-slim-trixie`, usuário não-root (UID 1000 compartilhado com o Connect); healthchecks nos serviços de longa duração + `depends_on: service_healthy`; `kafka-init` via `service_completed_successfully` e simulador sob demanda (constituição 1.0.1); `.env.example`; `make up` | ✅ | ✅ |
| VII | Simplicidade e segurança | Conector oficial de mercado em vez de producer próprio; sem Schema Registry nem banco; validação na fronteira (Pydantic/JSON Schema); `X-API-Key` nas rotas mutáveis; `pip-audit` no `make lint` e `make scan` (Trivy): bloqueia HIGH/CRITICAL corrigíveis nas imagens próprias; a imagem do Connect (base Confluent) é apenas reportada, pois a correção depende do fornecedor | ✅ | ✅ |

**Resultado**: nenhuma violação. Uma complexidade adicional (autorrecuperação do FilePulse) está
justificada em Complexity Tracking (princípio VII).

Observação: a constituição pede DLQ para mensagens inválidas; o Kafka Connect não oferece DLQ para
conectores *source*. O plano cobre isso com `dados/erros` (fronteira de arquivo) + DLQ na API de
consulta (fronteira de contrato) — ver [research.md R3](./research.md#r3-tratamento-de-erros-e-dlq-fonte-não-suporta-dlq-nativa).

## Project Structure

### Documentation (this feature)

```text
specs/001-pipeline-eventos-transportadora/
├── plan.md              # Este arquivo
├── research.md          # Fase 0
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/           # Fase 1
│   ├── evento-carga.schema.json
│   ├── topicos.md
│   ├── conector-filepulse.json
│   ├── api-controle-ingestao.openapi.yaml
│   ├── api-consulta.openapi.yaml
│   └── simulador-cli.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
pyproject.toml                 # uv workspace (membros abaixo) + config ruff/mypy/pytest
uv.lock
docker-compose.yml
Makefile
.env.example
README.md                      # US5

contratos/                     # biblioteca compartilhada do contrato de evento
├── pyproject.toml
├── src/contratos/
│   ├── __init__.py
│   ├── evento.py              # EventoCarga, TipoEvento, payloads (Pydantic, discriminated union)
│   ├── status.py              # StatusCarga + mapeamento TipoEvento → StatusCarga
│   └── schemas/evento-carga.v1.schema.json
└── tests/
    ├── unit/
    └── contract/              # modelo Pydantic ≡ JSON Schema versionado

simulador/                     # US1 (pasta exigida em requisitos/decisoes.md)
├── pyproject.toml
├── Dockerfile
├── src/simulador/
│   ├── __main__.py            # CLI (argparse + env)
│   ├── config.py              # pydantic-settings
│   ├── dominio/
│   │   ├── carga.py           # máquina de estados da carga
│   │   └── gerador.py         # sorteio de etapas, dados fictícios
│   ├── adapters/
│   │   └── escritor_arquivo.py  # escrita atômica (tmp + fsync + os.replace)
│   ├── servico.py             # loop de simulação, shutdown gracioso
│   └── observabilidade.py     # logging/metrics
└── tests/
    ├── unit/
    └── contract/              # eventos gerados validam contra o JSON Schema

controle_ingestao/             # US2 — API de controle do Kafka Connect
├── pyproject.toml
├── Dockerfile
├── src/controle_ingestao/
│   ├── main.py                # app FastAPI, lifespan, handlers RFC 9457
│   ├── config.py
│   ├── api/
│   │   ├── ingestao.py        # /api/v1/ingestao...
│   │   ├── saude.py           # /health/*
│   │   └── dependencias.py    # auth X-API-Key, clientes
│   ├── services/
│   │   └── ingestao.py        # regras de transição, mapeamento de estados
│   ├── adapters/
│   │   ├── connect_client.py  # httpx → REST do Kafka Connect
│   │   └── pastas.py          # contagem de arquivos pendentes/backup/erros
│   └── observabilidade.py
├── conectores/
│   └── arquivos-eventos-transportadora.json   # config versionada aplicada via PUT
└── tests/
    ├── unit/                  # respx
    └── contract/              # snapshot OpenAPI

api_consulta/                  # US4 — API de consulta
├── pyproject.toml
├── Dockerfile
├── src/api_consulta/
│   ├── main.py                # app, lifespan inicia consumer
│   ├── config.py
│   ├── api/
│   │   ├── cargas.py          # /api/v1/cargas, /resumo
│   │   ├── consumo.py         # /api/v1/consumo/status
│   │   └── saude.py
│   ├── services/
│   │   └── projecao.py        # aplica eventos, dedup, ordenação, status, resumo
│   ├── adapters/
│   │   ├── consumidor_kafka.py  # aiokafka assign + seek_to_beginning, catch-up, lag
│   │   └── produtor_dlq.py
│   └── observabilidade.py
└── tests/
    ├── unit/
    ├── contract/
    └── integration/           # testcontainers Kafka

infra/
├── connect/
│   └── Dockerfile             # cp-kafka-connect 7.9.10 + FilePulse 2.18.0
└── kafka/
    └── criar-topicos.sh       # usado pelo serviço kafka-init

tests_e2e/                     # fluxo completo contra `make up`
├── conftest.py
├── test_fluxo_completo.py
├── test_controle_ingestao.py
└── test_simulacao.py

dados/                         # fora do git (exceto .gitkeep)
├── eventos/
├── backup/
└── erros/
```

**Structure Decision**: monorepo com uv workspace. Cada unidade implantável (`simulador`,
`controle_ingestao`, `api_consulta`) tem `pyproject.toml`, `Dockerfile` e `tests/` próprios,
conforme a seção "Padrões de Stack" da constituição; `contratos` é a única biblioteca
compartilhada e concentra o contrato de evento (fonte única para produtor e consumidor). Os
Dockerfiles usam a raiz como contexto de build para incluir `contratos`. A configuração do conector
vive em `controle_ingestao/conectores/` (cópia operacional de
[contracts/conector-filepulse.json](./contracts/conector-filepulse.json)); a API envia o bloco
`config` via `PUT /connectors/{nome}/config`, que é idempotente.

### Serviços do Compose

| Serviço              | Imagem/Build                  | Porta host | Healthcheck                         | Depende de            |
|----------------------|-------------------------------|------------|-------------------------------------|-----------------------|
| `kafka`              | `confluentinc/cp-kafka:7.9.10` | 9092       | `kafka-broker-api-versions`         | —                     |
| `kafka-init`         | mesma do `kafka`              | —          | (efêmero, exit 0)                   | `kafka` healthy       |
| `connect`            | `infra/connect/Dockerfile`    | 8083       | `GET /connector-plugins` contém FilePulseSourceConnector | `kafka-init` completed |
| `controle-ingestao`  | `controle_ingestao/Dockerfile`| 8001       | `GET /health/live`                  | `connect` healthy     |
| `api-consulta`       | `api_consulta/Dockerfile`     | 8002       | `GET /health/live`                  | `kafka-init` completed |
| `simulador` (perfil `simulacao`) | `simulador/Dockerfile` | 9100 (metrics) | —                         | —                     |

Volumes: `./dados/eventos`, `./dados/backup`, `./dados/erros` montados em `/data/*` no
`connect` (rw), `controle-ingestao` (ro) e `/app/dados/eventos` no `simulador` (rw).

## Complexity Tracking

| Complexidade adicional | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Autorrecuperação do conector na API de controle (`services/ingestao.py`): toda consulta de status e uma vigia de 15 s após ativar/pausar/retomar/reiniciar detectam a falha `FAILED … has already been shut down` do FilePulse 2.18 e reiniciam só a instância do conector (`POST /connectors/{nome}/restart`), com log `conector_recuperado` | A condição de corrida do FilePulse ao parar a instância (research R1) deixa a ingestão parada após pausar/retomar; foi reproduzida nos testes e2e e violaria FR-010/SC-005 | Reiniciar manualmente (`make ingestao-reiniciar`) deixa o pipeline parado até alguém perceber; trocar de conector não é viável (SpoolDir rejeitado na T043); corrigir o plugin exigiria manter um fork Java |
