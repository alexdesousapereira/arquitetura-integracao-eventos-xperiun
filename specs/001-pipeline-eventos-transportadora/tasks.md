---

description: "Task list for Pipeline de Eventos da Transportadora"
---

# Tasks: Pipeline de Eventos da Transportadora

**Input**: Design documents from `/specs/001-pipeline-eventos-transportadora/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: INCLUÍDOS — exigidos pela constituição (princípio IV: unit, contrato, integração,
cobertura ≥ 80%). Em cada história, escreva os testes primeiro e confirme que falham.

**Organization**: Tasks agrupadas por user story; cada história é um incremento testável.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história a que pertence (US1…US5)
- Caminhos relativos à raiz do repositório, conforme a estrutura do [plan.md](./plan.md)

## Nota sobre dependências entre histórias

O broker Kafka e a criação dos tópicos são pré-requisito de US2 e US4, então ficam na **Fase 2
(Foundational)**. A **US3** concentra o que torna o tópico verificável conforme a spec: retenção
de 15 min efetiva, ordenação por carga, ferramentas de inspeção e seus testes.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: inicialização do monorepo, ferramentas e esqueleto dos pacotes

- [X] T001 Inicializar o repositório git (`git init`, branch `001-pipeline-eventos-transportadora`) e criar estrutura de diretórios do plan.md: `contratos/src/contratos/`, `contratos/tests/{unit,contract}/`, `simulador/src/simulador/{dominio,adapters}/`, `simulador/tests/{unit,contract}/`, `controle_ingestao/src/controle_ingestao/{api,services,adapters}/`, `controle_ingestao/conectores/`, `controle_ingestao/tests/{unit,contract}/`, `api_consulta/src/api_consulta/{api,services,adapters}/`, `api_consulta/tests/{unit,contract,integration}/`, `infra/connect/`, `infra/kafka/`, `tests_e2e/`, `dados/{eventos,backup,erros}/` (com `.gitkeep` em cada pasta de `dados/`)
- [X] T002 Criar `pyproject.toml` raiz como uv workspace (`[tool.uv.workspace] members = ["contratos", "simulador", "controle_ingestao", "api_consulta"]`), `requires-python = ">=3.12"`, grupo `dev` com `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `jsonschema`, `testcontainers[kafka]`, `pip-audit`, `pre-commit`, `httpx`; configurar `[tool.ruff]` (line-length 100, target py312, regras `E,F,I,UP,B,SIM,ASYNC,S,RUF,D,T20` — `D` garante docstrings em funções públicas e `T20` proíbe `print` (constituição, princípio III); `[tool.ruff.lint.pydocstyle] convention = "google"`; ignorar `D100`, `D104`, `D107`; em `tests/**` ignorar `D` e `S101`), `[tool.mypy]` (`strict = true`, plugin `pydantic.mypy`), `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`, markers `integration` e `e2e`, `addopts = "-m 'not integration and not e2e'"`)
- [X] T003 [P] Criar `contratos/pyproject.toml` (pacote `contratos`, src layout, dependência `pydantic>=2.7`) e `contratos/src/contratos/__init__.py`
- [X] T004 [P] Criar `simulador/pyproject.toml` (pacote `simulador`, dependências `contratos` (workspace), `pydantic-settings`, `structlog`, `prometheus-client`) e `simulador/src/simulador/__init__.py`
- [X] T005 [P] Criar `controle_ingestao/pyproject.toml` (pacote `controle_ingestao`, dependências `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`, `structlog`, `prometheus-client`) e `controle_ingestao/src/controle_ingestao/__init__.py`
- [X] T006 [P] Criar `api_consulta/pyproject.toml` (pacote `api_consulta`, dependências `contratos` (workspace), `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `aiokafka`, `structlog`, `prometheus-client`) e `api_consulta/src/api_consulta/__init__.py`
- [X] T007 Rodar `uv lock` e versionar `uv.lock` na raiz
- [X] T008 [P] Atualizar `.gitignore` com `.venv/`, `.env`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`, `dados/**/*` e exceções `!dados/**/` e `!dados/**/.gitkeep`
- [X] T009 [P] Criar `.pre-commit-config.yaml` com hooks `ruff` (check --fix), `ruff-format` e `mypy`
- [X] T010 [P] Preencher `.env.example` (sem segredos reais) com: `APP_UID=1000`, `APP_GID=1000`, `KAFKA_PORTA=9092`, `CONNECT_PORTA=8083`, `CONTROLE_PORTA=8001`, `CONSULTA_PORTA=8002`, `TOPICO_EVENTOS=transportadora.carga.eventos.v1`, `TOPICO_DLQ=transportadora.carga.eventos-dlq.v1`, `TOPICO_PARTICOES=3`, `TOPICO_RETENCAO_MS=900000`, `TOPICO_SEGMENT_MS=60000`, `DLQ_RETENCAO_MS=86400000`, `RETENCAO_PROJECAO_S=900`, `CONTROLE_API_KEY=troque-me`, `CONECTOR_NOME=arquivos-eventos-transportadora`, `LOG_LEVEL=INFO`, e variáveis `SIMULADOR_*` de [contracts/simulador-cli.md](./contracts/simulador-cli.md)
- [X] T011 Criar `Makefile` com alvos base: `lint` (`uv run ruff check . && uv run ruff format --check . && uv run mypy contratos/src simulador/src controle_ingestao/src api_consulta/src && uv run pip-audit`), `format`, `test` (unit+contract com `--cov` e `--cov-fail-under=80`), `test-integracao` (`-m integration`), `test-e2e` (`-m e2e`), `up`, `down`, `clean`, `logs`, `status` (`docker compose ps`), `build` (`docker compose --profile simulacao build`), `scan` (para cada imagem própria — `simulador`, `controle-ingestao`, `api-consulta`, `connect` — roda `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.76.1 image --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed <imagem>`), `ci` (`lint` → `test` → `build` → `scan` → `test-integracao`, os gates de merge da constituição); `up` deve criar `dados/{eventos,backup,erros}` com dono `$(APP_UID):$(APP_GID)` antes de `docker compose up -d --wait`, e imprimir a dica `make ingestao-ativar` ao final

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: contrato de evento compartilhado e broker Kafka com tópicos — pré-requisitos de US1, US2 e US4

**⚠️ CRITICAL**: nenhuma user story começa antes desta fase terminar

### Contrato de evento (biblioteca `contratos`)

- [X] T012 Copiar [contracts/evento-carga.schema.json](./contracts/evento-carga.schema.json) para `contratos/src/contratos/schemas/evento-carga.v1.schema.json` e incluí-lo como package data em `contratos/pyproject.toml`; esta cópia é a **fonte única** do contrato no código
- [X] T013 [P] Escrever testes unitários em `contratos/tests/unit/test_evento.py` cobrindo: aceitação do exemplo do JSON Schema; rejeição de campo extra no envelope (`additionalProperties: false`); `carga_id` fora de `^CRG-[0-9A-F]{8}$`; `occurred_at` sem sufixo `Z`/não-UTC; `event_version` diferente de `1`; payload incompatível com `event_type`; `peso_kg` ≤ 0 ou > 30000; `tentativa` fora de 1..3; `uf` fora de `^[A-Z]{2}$`; `motivo` fora de `DESTINATARIO_AUSENTE`, `ENDERECO_NAO_ENCONTRADO`, `RECUSADA`
- [X] T014 [P] Escrever teste de contrato em `contratos/tests/contract/test_schema_sincronizado.py` que valida 1 evento de cada `event_type` construído pelos modelos (via `model_dump(mode="json")`) contra `evento-carga.v1.schema.json` com `jsonschema.Draft202012Validator` (com `FormatChecker`), e garante que JSONs inválidos do T013 também são rejeitados pelo JSON Schema; asserta que `contratos/src/contratos/schemas/evento-carga.v1.schema.json` é idêntico a `specs/001-pipeline-eventos-transportadora/contracts/evento-carga.schema.json` (evita divergência); mantém 1 evento de cada tipo em `contratos/tests/contract/fixtures/v1/*.json` que MUST continuar válido em versões futuras do contrato (compatibilidade retroativa, princípio I)
- [X] T015 Implementar `contratos/src/contratos/evento.py` com Pydantic v2 (`model_config = ConfigDict(extra="forbid", frozen=True)`): `TipoEvento` (StrEnum com os 6 valores `carga.recebida`, `carga.saiu_para_transporte`, `carga.em_transito`, `carga.saiu_para_entrega`, `carga.entregue`, `carga.entrega_falhou`), `Localidade` (`cidade` 1–100 chars, `uf` `^[A-Z]{2}$`), `Localizacao` (`latitude` −90..90, `longitude` −180..180, `cidade`, `uf`), os 6 payloads conforme [data-model.md §3](./data-model.md) (`peso_kg` "number > 0, ≤ 30000", `descricao` "≤ 200", `veiculo_id` `^VEI-[0-9]{4}$`, `tentativa` "integer 1..3", `recebedor` "≤ 100", `motivo` enum), e `EventoCarga` como união discriminada por `event_type` (uma classe por tipo com `event_type: Literal[...]`) contendo `event_id: UUID`, `event_version: Literal[1]`, `occurred_at: AwareDatetime` (validador: converte/exige UTC e serializa com `Z`), `source` (1–100), `correlation_id: UUID`, `carga_id` (`^CRG-[0-9A-F]{8}$`), `payload`; expor `EventoCargaAdapter = TypeAdapter(EventoCarga)` e `parse_evento(raw: bytes | str) -> EventoCarga`
- [X] T016 Implementar `contratos/src/contratos/status.py` com `StatusCarga` (StrEnum `RECEBIDA`, `EM_TRANSPORTE`, `EM_TRANSITO`, `SAIU_PARA_ENTREGA`, `ENTREGUE`, `FALHA_ENTREGA`) e `STATUS_POR_TIPO: Mapping[TipoEvento, StatusCarga]` conforme [data-model.md §2](./data-model.md); exportar API pública em `contratos/src/contratos/__init__.py`

### Broker Kafka e tópicos

- [X] T017 Criar `infra/kafka/criar-topicos.sh` (bash, `set -euo pipefail`) que usa `kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists` para `${TOPICO_EVENTOS}` (partições `${TOPICO_PARTICOES}`, RF 1, `--config cleanup.policy=delete --config retention.ms=${TOPICO_RETENCAO_MS} --config segment.ms=${TOPICO_SEGMENT_MS}`) e `${TOPICO_DLQ}` (1 partição, RF 1, `retention.ms=${DLQ_RETENCAO_MS}`); em seguida aplica `kafka-configs --alter` com os mesmos valores (para tópicos já existentes) e imprime `kafka-topics --describe` de ambos
- [X] T018 Criar `docker-compose.yml` com: rede `pipeline`; serviço `kafka` (`confluentinc/cp-kafka:7.9.10`, KRaft com `KAFKA_PROCESS_ROLES=broker,controller`, `KAFKA_NODE_ID=1`, `CLUSTER_ID` fixo, listeners `PLAINTEXT://kafka:29092`, `CONTROLLER://kafka:29093`, `PLAINTEXT_HOST://localhost:${KAFKA_PORTA}`, `KAFKA_AUTO_CREATE_TOPICS_ENABLE=false`, `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1`, `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1`, `KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1`, `KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS=60000`, volume nomeado `kafka-data`, healthcheck `kafka-broker-api-versions --bootstrap-server kafka:29092`); serviço `kafka-init` (mesma imagem, monta `./infra/kafka/criar-topicos.sh`, `env_file: .env`, `depends_on: kafka: condition: service_healthy`, `restart: "no"`)
- [X] T019 Adicionar alvos `topicos` (executa `kafka-topics --describe` dos dois tópicos via `docker compose exec kafka`) ao `Makefile`
- [X] T020 Validar a fundação: `make lint`, `make test` (contratos verdes) e `make up` com `kafka` healthy e `kafka-init` saindo com código 0; `make topicos` mostra ambos os tópicos

**Checkpoint**: contrato compartilhado e broker com tópicos prontos — histórias podem começar

---

## Phase 3: User Story 1 - Gerar massa de eventos de cargas (Priority: P1) 🎯 MVP

**Goal**: simulador que mantém N cargas simultâneas e grava cada evento como arquivo JSON atômico em `dados/eventos`

**Independent Test**: `make simular ARGS="--cargas 20 --duracao-s 60"` → arquivos `*.json` válidos contra o contrato, cargas intercaladas, sequência coerente por carga, nenhum `.tmp` remanescente (quickstart §2)

### Tests for User Story 1 ⚠️

- [X] T021 [P] [US1] Testes da máquina de estados em `simulador/tests/unit/test_carga.py`: sequência `RECEBIDA → EM_TRANSPORTE → EM_TRANSITO (1..5 vezes) → SAIU_PARA_ENTREGA → ENTREGUE|FALHA_ENTREGA`; após falha com `tentativa < 3` volta a `SAIU_PARA_ENTREGA` com `tentativa+1`; com `tentativa = 3` a falha é terminal; `occurred_at` estritamente crescente por carga; `correlation_id` constante na jornada; determinismo com `seed` fixo
- [X] T022 [P] [US1] Testes do escritor em `simulador/tests/unit/test_escritor_arquivo.py`: nome `<occurred_at:%Y%m%dT%H%M%S%fZ>_<carga_id>_<event_id>.json`; arquivo temporário começa com `.` e termina em `.json.tmp`; após escrita não restam `.tmp`; conteúdo é JSON UTF-8 de um único objeto; erro de permissão gera exceção específica
- [X] T023 [P] [US1] Testes do serviço em `simulador/tests/unit/test_servico.py`: mantém exatamente N cargas ativas (repõe ao concluir); respeita `--max-eventos` e `--duracao-s`; eventos de cargas distintas aparecem intercalados; parada solicitada (evento de cancelamento) encerra após o ciclo corrente sem `.tmp`
- [X] T024 [P] [US1] Teste de contrato em `simulador/tests/contract/test_eventos_validos.py`: gera ≥ 500 eventos com `seed` fixo em `tmp_path` e valida cada arquivo contra `contratos/src/contratos/schemas/evento-carga.v1.schema.json` (cobrindo os 6 `event_type`)

### Implementation for User Story 1

- [X] T025 [P] [US1] Implementar `simulador/src/simulador/config.py` (`pydantic-settings`, prefixo `SIMULADOR_`): `cargas` (int ≥ 1, padrão 20), `intervalo_ms` (int ≥ 10, padrão 500), `duracao_s` (int ≥ 0, 0 = infinito), `max_eventos` (int ≥ 0, 0 = infinito), `saida` (Path, padrão `dados/eventos`), `seed` (int | None), `prob_falha` (0..1, padrão 0.15), `metrics_port` (int ≥ 0, 0 = desligado)
- [X] T026 [P] [US1] Implementar `simulador/src/simulador/dominio/gerador.py`: catálogo fictício de cidades/UF brasileiras com lat/long aproximadas, centros de distribuição, descrições de carga, nomes de recebedor fictícios, `veiculo_id` `VEI-NNNN`, `carga_id` `CRG-` + 8 hex maiúsculos; tudo a partir de `random.Random(seed)` injetado
- [X] T027 [US1] Implementar `simulador/src/simulador/dominio/carga.py`: classe `CargaSimulada` com máquina de estados de [data-model.md §4](./data-model.md) (1–5 eventos `em_transito`, `prob_falha`, máx. 3 tentativas), método `proximo_evento(agora: datetime) -> EventoCarga | None` (retorna `None` quando terminal) que garante `occurred_at` estritamente crescente e constrói eventos com os modelos de `contratos`; `source="simulador-transportadora"`
- [X] T028 [US1] Implementar `simulador/src/simulador/adapters/escritor_arquivo.py`: `EscritorArquivo.gravar(evento)` escreve em `<saida>/.<nome>.json.tmp`, `flush` + `os.fsync`, `os.replace` para `<saida>/<nome>.json`; cria a pasta se não existir; remove o `.tmp` em caso de falha
- [X] T029 [US1] Implementar `simulador/src/simulador/observabilidade.py`: `structlog` com `JSONRenderer`, campos `timestamp` (ISO UTC), `level`, `service="simulador"`; métricas `simulador_eventos_gerados_total{event_type}` (Counter) e `simulador_cargas_ativas` (Gauge); `iniciar_servidor_metricas(port)` via `prometheus_client.start_http_server` quando `port > 0`
- [X] T030 [US1] Implementar `simulador/src/simulador/servico.py`: loop que mantém N `CargaSimulada` ativas; a cada ciclo de `intervalo_ms` sorteia um subconjunto de cargas para avançar, grava o evento via `EscritorArquivo`, loga cada evento com `event_id`, `carga_id`, `correlation_id`, `event_type`; repõe cargas concluídas; respeita `duracao_s`/`max_eventos`; log de resumo a cada 10 s (`eventos_gerados`, `cargas_ativas`, `cargas_concluidas`); parada graciosa via `threading.Event`
- [X] T031 [US1] Implementar `simulador/src/simulador/__main__.py`: CLI `argparse` com as opções de [contracts/simulador-cli.md](./contracts/simulador-cli.md) sobrepondo as variáveis de ambiente; handlers de `SIGINT`/`SIGTERM` que acionam a parada; códigos de saída `0` sucesso, `2` argumentos inválidos, `1` erro de I/O
- [X] T032 [US1] Criar `simulador/Dockerfile` multi-stage (contexto = raiz): estágio `builder` `python:3.12.16-slim-trixie` com o binário `uv` copiado de `ghcr.io/astral-sh/uv:0.13.6` (`COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv`) instalando `contratos` e `simulador` (`uv sync --frozen --no-dev --package simulador`), estágio final `python:3.12.16-slim-trixie` com `.venv` copiado, `USER ${APP_UID}:${APP_GID}` (args, padrão 1000), `WORKDIR /app`, `ENTRYPOINT ["python", "-m", "simulador"]`, `SIMULADOR_SAIDA=/app/dados/eventos`
- [X] T033 [US1] Adicionar serviço `simulador` ao `docker-compose.yml` (perfil `simulacao`, build com args `APP_UID/APP_GID`, `env_file: .env`, volume `./dados/eventos:/app/dados/eventos`, porta `9100` para métricas) e alvos `simular` (`docker compose --profile simulacao run --rm --service-ports simulador $(ARGS)` — `--service-ports` é necessário para publicar a porta 9100 de métricas) e `validar-eventos` (script `uv run python -m contratos.validar dados/eventos`) ao `Makefile`
- [X] T034 [US1] Implementar `contratos/src/contratos/validar.py` (`python -m contratos.validar <pasta>`): valida todos os `*.json` da pasta (e a pasta `backup/` se informada) contra o JSON Schema e imprime total válidos/inválidos; código de saída 1 se houver inválidos

**Checkpoint**: US1 funcional e testável isoladamente (sem Kafka)

---

## Phase 4: User Story 2 - Ingerir arquivos de eventos com controle operacional (Priority: P2)

**Goal**: Kafka Connect + FilePulse publicando os arquivos no tópico; API FastAPI de controle (status, ativar, pausar, retomar, reiniciar, remover)

**Independent Test**: com o simulador gerando arquivos, `make ingestao-ativar` → estado `ATIVA`, arquivos movidos para `dados/backup` em ≤ 30 s; pausar/retomar conforme quickstart §3; arquivo inválido vai para `dados/erros`; mutação sem `X-API-Key` → 401

### Tests for User Story 2 ⚠️

- [X] T035 [P] [US2] Testes do cliente Connect em `controle_ingestao/tests/unit/test_connect_client.py` (com `respx`): `obter_status` mapeia 200/404; `aplicar_config` usa `PUT /connectors/{nome}/config` e distingue 201 (criado) de 200 (atualizado); `pausar` → `PUT /connectors/{nome}/pause`; `retomar` → `PUT /connectors/{nome}/resume`; `reiniciar` → `POST /connectors/{nome}/restart?includeTasks=true&onlyFailed=false`; `remover` trata 404 como sucesso; timeout/conexão recusada → `ConnectIndisponivelError`; 4xx/5xx → `ConnectErroError` com detalhe
- [X] T036 [P] [US2] Testes do serviço em `controle_ingestao/tests/unit/test_servico_ingestao.py`: mapeamento de estados do Connect conforme [data-model.md §6](./data-model.md) (`RUNNING`→`ATIVA`, `PAUSED`→`PAUSADA`, `FAILED` em conector ou qualquer tarefa→`COM_FALHA`, `UNASSIGNED`/`RESTARTING`→`INICIANDO`, 404→`INEXISTENTE`); idempotência (pausar já pausada e retomar já ativa retornam sem chamar o Connect); pausar/retomar/reiniciar com `INEXISTENTE` → erro de "ingestão inexistente"; contagem de arquivos ignora arquivos ocultos
- [X] T037 [P] [US2] Testes da API em `controle_ingestao/tests/unit/test_api_ingestao.py` (`httpx.AsyncClient` + `ASGITransport`, serviço substituído via `app.dependency_overrides`): GET status 200; PUT 201/200; POST pausar/retomar/reiniciar 202; DELETE 204; rotas mutáveis sem `X-API-Key` ou com chave errada → 401 `application/problem+json`; ingestão inexistente → 404 problem; Connect indisponível → 503 problem; respostas de erro contêm `correlation_id`; `/health/ready` 503 quando o Connect **ou** o broker estiver inacessível, indicando qual em `dependencias`
- [X] T038 [P] [US2] Teste de contrato em `controle_ingestao/tests/contract/test_openapi.py`: compara `app.openapi()` com [contracts/api-controle-ingestao.openapi.yaml](./contracts/api-controle-ingestao.openapi.yaml) (mesmos paths, métodos, códigos de resposta e propriedades obrigatórias de `StatusIngestao` e `Problema`), lendo o YAML diretamente de `specs/001-pipeline-eventos-transportadora/contracts/` (fonte única, sem cópia)
- [X] T039 [P] [US2] Teste e2e em `tests_e2e/test_controle_ingestao.py` (marcador `e2e`, requer `make up`): ativar → `ATIVA`; gerar 20 arquivos válidos → todos em `dados/backup` em ≤ 30 s; pausar → criar 10 arquivos → continuam pendentes por 20 s; retomar → pendentes = 0 em ≤ 30 s; arquivo `{ quebrado` → aparece em `dados/erros` e estado continua `ATIVA`; reiniciar a ingestão não republica arquivos já ingeridos

### Implementation for User Story 2

- [X] T040 [P] [US2] Criar `infra/connect/Dockerfile`: `FROM confluentinc/cp-kafka-connect:7.9.10` (mesma versão do broker), instala o FilePulse 2.18.0 a partir do zip oficial do GitHub validado por SHA-256 (`confluent-hub install <zip>`) — research R1, mantém usuário `appuser` (UID 1000)
- [X] T041 [P] [US2] Criar `controle_ingestao/conectores/arquivos-eventos-transportadora.json` com o bloco `config` de [contracts/conector-filepulse.json](./contracts/conector-filepulse.json) (apenas o objeto `config`, pronto para `PUT /connectors/{nome}/config`)
- [X] T042 [US2] Adicionar serviço `connect` ao `docker-compose.yml`: build `infra/connect`, porta `${CONNECT_PORTA}:8083`, `CONNECT_BOOTSTRAP_SERVERS=kafka:29092`, `CONNECT_GROUP_ID=connect-transportadora`, tópicos internos `_connect-configs`, `_connect-offsets`, `_connect-status` com RF 1, `CONNECT_KEY_CONVERTER`/`CONNECT_VALUE_CONVERTER` padrão `org.apache.kafka.connect.json.JsonConverter`, `CONNECT_REST_ADVERTISED_HOST_NAME=connect`, `CONNECT_PLUGIN_PATH=/usr/share/java,/usr/share/confluent-hub-components`; volumes `./dados/eventos:/data/eventos`, `./dados/backup:/data/backup`, `./dados/erros:/data/erros`; healthcheck `curl -sf localhost:8083/connector-plugins | grep -q FilePulseSourceConnector`; `depends_on: kafka-init: condition: service_completed_successfully`
- [X] T043 [US2] Subir `connect` e validar manualmente a config: aplicar `controle_ingestao/conectores/arquivos-eventos-transportadora.json` via `curl -X PUT localhost:8083/connectors/arquivos-eventos-transportadora/config`, gerar eventos com `make simular ARGS="--max-eventos 20"`, conferir com `kafka-console-consumer --property print.key=true --property print.headers=true` que chave = `carga_id` e headers `correlation_id`/`event_type` existem; ajustar nomes de propriedades se divergirem (resultado: SpoolDir rejeitado, FilePulse adotado — research R1) e atualizar também [contracts/conector-filepulse.json](./contracts/conector-filepulse.json)
- [X] T044 [P] [US2] Implementar `controle_ingestao/src/controle_ingestao/config.py` (`pydantic-settings`): `connect_url` (padrão `http://connect:8083`), `conector_nome`, `conector_config_path` (padrão `conectores/arquivos-eventos-transportadora.json`), `controle_api_key: SecretStr` (obrigatório, sem padrão), `kafka_bootstrap` (padrão `kafka:29092`), `pasta_eventos`/`pasta_backup`/`pasta_erros` (padrão `/data/*`), `timeout_connect_s` (padrão 5), `log_level`
- [X] T045 [P] [US2] Implementar `controle_ingestao/src/controle_ingestao/observabilidade.py`: `structlog` JSON (`service="controle-ingestao"`), middleware que lê ou gera `X-Correlation-ID`, coloca em `contextvars` e devolve no response; métricas `controle_requisicoes_total{rota,metodo,status}`, `controle_requisicao_duracao_segundos` (Histogram) `controle_connect_erros_total{tipo}` e `controle_arquivos{situacao}` (Gauge com `situacao` = `pendente`, `backup`, `erro`, atualizado a cada consulta de status — FR-025)
- [X] T046 [US2] Implementar `controle_ingestao/src/controle_ingestao/adapters/connect_client.py`: `ConnectClient` sobre `httpx.AsyncClient` com os métodos e erros testados em T035; propaga `X-Correlation-ID`
- [X] T047 [P] [US2] Implementar `controle_ingestao/src/controle_ingestao/adapters/pastas.py`: `contar_arquivos(pasta) -> int` contando apenas `*.json` não ocultos, executado via `asyncio.to_thread`; retorna 0 se a pasta não existir
- [X] T048 [US2] Implementar `controle_ingestao/src/controle_ingestao/services/ingestao.py`: `ServicoIngestao` com `status()`, `ativar()`, `pausar()`, `retomar()`, `reiniciar()`, `remover()` conforme tabela de transições de [data-model.md §6](./data-model.md); modelos Pydantic `EstadoIngestao`, `Tarefa`, `ContagemArquivos`, `StatusIngestao` (campos de `StatusIngestao` no OpenAPI: `nome`, `estado`, `tarefas`, `arquivos{pendentes,em_backup,com_erro}`, `connect_disponivel`, `consultado_em`); `ativar()` lê o JSON versionado do disco
- [X] T049 [US2] Implementar `controle_ingestao/src/controle_ingestao/api/dependencias.py`: `exigir_api_key` (header `X-API-Key`, `secrets.compare_digest` com `controle_api_key`, 401 caso contrário) e providers de `ConnectClient`/`ServicoIngestao` a partir de `request.app.state`
- [X] T050 [US2] Implementar `controle_ingestao/src/controle_ingestao/api/ingestao.py`: `APIRouter(prefix="/api/v1/ingestao")` com GET, PUT (201 se criado, 200 se atualizado), DELETE (204), POST `/pausar`, `/retomar`, `/reiniciar` (202 com `StatusIngestao`); `exigir_api_key` apenas nas rotas mutáveis; `response_model` em todas as rotas
- [X] T051 [P] [US2] Implementar `controle_ingestao/src/controle_ingestao/api/saude.py`: `/health/live` (sempre `ok`), `/health/ready` (checa `GET /` no Connect **e** conexão TCP com `kafka_bootstrap` (padrão `kafka:29092`, timeout 2 s, via `asyncio.open_connection`); 503 com `dependencias.kafka_connect` e/ou `dependencias.kafka` = `indisponivel` — FR-011), `/metrics` (`generate_latest`)
- [X] T052 [US2] Implementar `controle_ingestao/src/controle_ingestao/main.py`: `lifespan` cria/fecha `httpx.AsyncClient` e o `ServicoIngestao` em `app.state`; registra routers; exception handlers RFC 9457 (`application/problem+json`, campos `type`, `title`, `status`, `detail`, `instance`, `correlation_id`) para `IngestaoInexistenteError` (404), `ConnectIndisponivelError` (503), `ConnectErroError` (502), `RequestValidationError` (422) e `HTTPException`; metadados OpenAPI (título, versão 1.0.0, security scheme `ApiKey`)
- [X] T053 [US2] Criar `controle_ingestao/Dockerfile` multi-stage (mesmo padrão do T032, `--package controle_ingestao`), copiando `controle_ingestao/conectores/`, `USER 1000:1000`, `CMD ["uvicorn", "controle_ingestao.main:app", "--host", "0.0.0.0", "--port", "8000"]`, `HEALTHCHECK` via `python -c` em `/health/live`
- [X] T054 [US2] Adicionar serviço `controle-ingestao` ao `docker-compose.yml` (porta `${CONTROLE_PORTA}:8000`, `env_file: .env`, volumes `./dados/*:/data/*:ro`, `depends_on: connect: condition: service_healthy`) e alvos `ingestao-status`, `ingestao-ativar`, `ingestao-pausar`, `ingestao-retomar`, `ingestao-reiniciar`, `ingestao-remover` ao `Makefile` (curl com `-H "X-API-Key: $(CONTROLE_API_KEY)"` lido do `.env`, saída via `jq`)

**Checkpoint**: arquivos fluem para o tópico e a ingestão é operável pela API

---

## Phase 5: User Story 3 - Disponibilizar eventos em um tópico do barramento (Priority: P3)

**Goal**: tópico verificável conforme a spec — retenção de 15 min efetiva, ordenação por carga e ferramentas de inspeção

**Independent Test**: `make topicos` mostra a configuração esperada; publicar e ler um evento de teste; ordem por carga preservada; após ~17 min sem novos eventos o *log start offset* avança (quickstart §1 e §5)

### Tests for User Story 3 ⚠️

- [X] T055 [P] [US3] Teste de integração em `api_consulta/tests/integration/test_topico.py` (marcador `integration`, `testcontainers` Kafka; cria os tópicos com `AIOKafkaAdminClient` usando as mesmas configs de `.env.example` — fica em `api_consulta/tests/integration/` porque reaproveita as fixtures de Kafka desse pacote): tópico criado com 3 partições, `retention.ms=900000`, `segment.ms=60000`; 100 eventos de 10 cargas publicados com chave `carga_id` são lidos na mesma ordem por carga
- [X] T056 [P] [US3] Teste e2e em `tests_e2e/test_topico.py` (marcador `e2e`): `kafka-configs --describe` do tópico retorna os valores de `.env`; mensagens publicadas pelo Connect têm chave igual ao `carga_id` do valor e headers `correlation_id` e `event_type`

### Implementation for User Story 3

- [X] T057 [US3] Adicionar ao `Makefile` os alvos `topicos-offsets` (`kafka-get-offsets --topic $(TOPICO_EVENTOS)` com `--time -2` e `--time -1`, mostrando *log start offset* e *end offset* por partição), `consumir` (`kafka-console-consumer` com `print.key`, `print.headers`, `print.timestamp`, `--from-beginning --max-messages $(N)`) e `dlq` (mesmo, para `$(TOPICO_DLQ)`)
- [X] T058 [US3] Adicionar alvo `publicar-evento-teste` ao `Makefile` (publica via `kafka-console-producer --property parse.key=true --property key.separator='|'` um evento válido de exemplo de [contracts/evento-carga.schema.json](./contracts/evento-carga.schema.json)) e `publicar-evento-invalido` (JSON válido sem `carga_id`, usado na US4)
- [X] T059 [US3] Revisar `infra/kafka/criar-topicos.sh` para garantir idempotência ao mudar `TOPICO_RETENCAO_MS` em `.env` (o `kafka-configs --alter` reaplica a retenção a cada `make up`) e documentar no cabeçalho do script por que `segment.ms` é necessário (research R5)

**Checkpoint**: tópico com retenção e ordenação comprovadas por teste

---

## Phase 6: User Story 4 - Consultar eventos e status de cargas via API (Priority: P4)

**Goal**: API FastAPI que consome o tópico, mantém projeção em memória (dedup, ordenação, status), envia eventos fora do contrato ao DLQ e expõe consultas

**Independent Test**: com eventos no tópico (via `make publicar-evento-teste` ou pipeline completo), `/api/v1/cargas/{id}`, `/eventos`, listagem por status, `/resumo` e `/consumo/status` correspondem aos eventos publicados; carga inexistente → 404 problem; restart reconstrói o estado (quickstart §4)

### Tests for User Story 4 ⚠️

- [X] T060 [P] [US4] Testes da projeção em `api_consulta/tests/unit/test_projecao.py`: aplica eventos e calcula `status` pelo evento de maior `occurred_at`; histórico ordenado por (`occurred_at`, `event_id`); evento duplicado (mesmo `event_id`) é descartado e incrementa `eventos_duplicados_descartados`; evento fora de ordem (`entregue` sem `em_transito`) é aceito; `origem`/`destino`/`peso_kg`/`descricao` nulos quando não há `carga.recebida`; `tentativas_entrega` = maior `tentativa` (0 se nenhuma); listagem filtra por status, ordena por `ultima_atualizacao` desc e pagina (`page` ≥ 1, `size` 1..500); expiração (FR-022a, relógio injetável): evento com `occurred_at` mais antigo que a janela é ignorado ao ser aplicado; `expirar(agora)` remove eventos fora da janela, recalcula `status`/`ultima_atualizacao`/`tentativas_entrega`/`total_eventos`/dados de `carga.recebida` e remove cargas sem eventos (consulta → não encontrada); eventos expirados não contam como duplicados nem vão ao DLQ; resumo traz todas as chaves de `StatusCarga` (0 quando vazio) e `total_cargas`/`total_eventos` coerentes; consulta de 10.000 cargas < 1 s
- [X] T061 [P] [US4] Testes do processamento de mensagens em `api_consulta/tests/unit/test_processador.py`: bytes não-JSON → DLQ com `erro_tipo=JSON_INVALIDO`; JSON fora do contrato → DLQ com `erro_tipo=CONTRATO_INVALIDO` e `erro_motivo` truncado em 1000 chars; headers `topico_origem`, `particao_origem`, `offset_origem` preenchidos e `correlation_id` copiado se presente; mensagem válida aplicada na projeção; falha no DLQ não interrompe o consumo (loga e conta)
- [X] T062 [P] [US4] Testes da API em `api_consulta/tests/unit/test_api_cargas.py` (`ASGITransport`, projeção pré-carregada): GET `/api/v1/cargas` (filtro, paginação, 422 para `size=0` ou `status` inválido); GET `/api/v1/cargas/{carga_id}` 200 e 404 `application/problem+json`; `carga_id` fora de `^CRG-[0-9A-F]{8}$` → 422; GET `/eventos` em ordem cronológica; GET `/api/v1/resumo`; GET `/api/v1/consumo/status`; `/health/ready` 503 até `catch_up_concluido`
- [X] T063 [P] [US4] Teste de contrato em `api_consulta/tests/contract/test_openapi.py`: compara `app.openapi()` com [contracts/api-consulta.openapi.yaml](./contracts/api-consulta.openapi.yaml) (paths, métodos, parâmetros, códigos e propriedades obrigatórias de `Carga`, `PaginaCargas`, `Resumo`, `StatusConsumo`, `Problema`); valida também que cada item de `/eventos` valida contra o JSON Schema do evento; lê o YAML diretamente de `specs/001-pipeline-eventos-transportadora/contracts/` (fonte única, sem cópia)
- [X] T064 [P] [US4] Teste de integração em `api_consulta/tests/integration/test_consumidor.py` (marcador `integration`, testcontainers): publica 50 eventos válidos (incluindo 5 duplicados) + 2 inválidos → projeção com 45 eventos distintos, 5 duplicados descartados, 2 mensagens no DLQ com headers corretos; `catch_up_concluido` vira `true`; reiniciar o consumidor reconstrói a mesma projeção; lag total = 0 ao final; com janela de retenção de 5 s, eventos publicados com `occurred_at` antigo não aparecem e cargas somem após a limpeza periódica
- [X] T065 [P] [US4] Teste e2e em `tests_e2e/test_fluxo_completo.py` (marcador `e2e`): com ingestão ativa, `simular --cargas 10 --max-eventos 200` → em ≤ 60 s `total_eventos` da API = 200 e cada `carga_id` dos arquivos em `dados/backup` existe na API com histórico igual (por `event_id`) aos arquivos; `docker compose restart api-consulta` → mesmo `total_eventos` após ficar pronta

### Implementation for User Story 4

- [X] T066 [P] [US4] Implementar `api_consulta/src/api_consulta/config.py` (`pydantic-settings`): `kafka_bootstrap` (padrão `kafka:29092`), `topico_eventos`, `topico_dlq`, `catch_up_timeout_s` (padrão 120), `retencao_projecao_s` (env `RETENCAO_PROJECAO_S`, padrão 900 — mesma janela do tópico), `intervalo_expiracao_s` (padrão 30), `log_level`
- [X] T067 [P] [US4] Implementar `api_consulta/src/api_consulta/observabilidade.py`: `structlog` JSON (`service="api-consulta"`, `event_id`/`correlation_id` quando houver), middleware `X-Correlation-ID`; métricas `consulta_eventos_consumidos_total{event_type}`, `consulta_eventos_duplicados_total`, `consulta_eventos_dlq_total{erro_tipo}`, `consulta_eventos_expirados_total`, `consulta_lag_mensagens{particao}` (Gauge), `consulta_requisicao_duracao_segundos` (Histogram)
- [X] T068 [US4] Implementar `api_consulta/src/api_consulta/services/projecao.py`: `Projecao` em memória com `aplicar(evento) -> bool` (False se duplicado), `obter_carga`, `historico`, `listar(status, page, size)`, `resumo()`; modelos de resposta Pydantic `Carga`, `PaginaCargas`, `Resumo` conforme [data-model.md §5](./data-model.md); usa `STATUS_POR_TIPO` de `contratos`; operações síncronas e O(log n) por inserção (`bisect`) — sem locks, pois roda no mesmo event loop; `aplicar` ignora eventos fora da janela de retenção; `expirar(agora) -> int` remove eventos com `occurred_at < agora − retencao_projecao_s` usando um heap auxiliar por `occurred_at`, recalcula os campos derivados e remove cargas vazias (FR-022a, [data-model.md §5 regra 5](./data-model.md)); relógio injetável para testes
- [X] T069 [US4] Implementar `api_consulta/src/api_consulta/adapters/produtor_dlq.py`: `ProdutorDLQ` com `AIOKafkaProducer` (`acks="all"`, `enable_idempotence=True`) e `enviar(mensagem_original, erro_tipo, erro_motivo)` preservando chave e valor originais e adicionando os headers de [contracts/topicos.md](./contracts/topicos.md)
- [X] T070 [US4] Implementar `api_consulta/src/api_consulta/services/processador.py`: `processar(msg)` → `parse_evento` de `contratos`; em `ValidationError`/`JSONDecodeError` envia ao DLQ e conta; senão `Projecao.aplicar` e atualiza métricas; loga com `event_id` e `correlation_id` (header ou corpo)
- [X] T071 [US4] Implementar `api_consulta/src/api_consulta/adapters/consumidor_kafka.py`: `ConsumidorEventos` com `AIOKafkaConsumer` sem `group_id` e `enable_auto_commit=False`; no start descobre partições, `assign()` em todas, `seek_to_beginning()`, captura `end_offsets` iniciais; loop `getmany(timeout_ms=1000)` → `processador.processar`; marca `catch_up_concluido` quando a posição ≥ end offsets capturados em todas as partições; `status_consumo()` calcula `lag = end_offset − posição` por partição (atualiza Gauge); reconecta com backoff exponencial (máx. 30 s) se o broker cair; `stop()` cancela a task e fecha o consumer
- [X] T072 [US4] Implementar `api_consulta/src/api_consulta/api/cargas.py`: `APIRouter(prefix="/api/v1")` com `GET /cargas` (`status: StatusCarga | None`, `page: int = Query(1, ge=1)`, `size: int = Query(50, ge=1, le=500)`), `GET /cargas/{carga_id}` (`Path(pattern="^CRG-[0-9A-F]{8}$")`), `GET /cargas/{carga_id}/eventos`, `GET /resumo`; `CargaNaoEncontradaError` → 404
- [X] T073 [P] [US4] Implementar `api_consulta/src/api_consulta/api/consumo.py` (`GET /api/v1/consumo/status` → `StatusConsumo`) e `api_consulta/src/api_consulta/api/saude.py` (`/health/live`; `/health/ready` 200 só com broker acessível e `catch_up_concluido`, senão 503 com `dependencias`; `/metrics`)
- [X] T074 [US4] Implementar `api_consulta/src/api_consulta/main.py`: `lifespan` cria `Projecao`, `ProdutorDLQ`, `ConsumidorEventos` e inicia a task de consumo e uma task periódica que chama `Projecao.expirar(agora)` a cada `intervalo_expiracao_s` (incrementa `consulta_eventos_expirados_total`); encerra tudo no shutdown; handlers RFC 9457 (`CargaNaoEncontradaError` 404, `RequestValidationError` 422, `HTTPException`); metadados OpenAPI
- [X] T075 [US4] Criar `api_consulta/Dockerfile` (mesmo padrão do T053, `--package api_consulta`, `uvicorn api_consulta.main:app`) e adicionar serviço `api-consulta` ao `docker-compose.yml` (porta `${CONSULTA_PORTA}:8000`, `env_file: .env`, `depends_on: kafka-init: condition: service_completed_successfully`, healthcheck em `/health/live`)
- [X] T076 [US4] Adicionar ao `Makefile` os alvos `consulta-resumo`, `consulta-cargas` (`STATUS=` opcional) e `consulta-consumo` (curl + `jq`)

**Checkpoint**: pipeline ponta a ponta funcional (arquivo → Connect → tópico → API)

---

## Phase 7: User Story 5 - Documentação para operar e testar a arquitetura (Priority: P5)

**Goal**: README que permite subir, simular, operar, testar e verificar cada etapa sem ajuda

**Independent Test**: uma pessoa nova segue apenas o README numa máquina limpa e vê eventos chegando à API de consulta em ≤ 15 min (SC-001)

- [X] T077 [US5] Escrever `README.md` na raiz com: visão geral e diagrama ASCII do fluxo (simulador → `dados/eventos` → Kafka Connect/FilePulse → `transportadora.carga.eventos.v1` → API de consulta; API de controle → REST do Connect; DLQ); pré-requisitos (Docker 24+, Compose v2, Make, curl, jq, ~4 GB RAM; opcional Python 3.12 + uv); configuração (`cp .env.example .env`, trocar `CONTROLE_API_KEY`)
- [X] T078 [US5] Adicionar ao `README.md` a seção "Executando a simulação" passo a passo (`make up`, `make ingestao-ativar`, `make simular ARGS=...`, consultas) e a tabela de alvos do `Makefile` com descrição
- [X] T079 [US5] Adicionar ao `README.md` a seção "Verificando cada etapa" com comando e saída esperada para: simulador (arquivos/logs/métricas), ingestão (`make ingestao-status`, pastas), tópico (`make topicos`, `make topicos-offsets`, `make consumir N=5`), DLQ (`make dlq`), API de consulta (`/health/ready`, `/api/v1/consumo/status`, `/api/v1/resumo`), links para `/docs` de cada API
- [X] T080 [US5] Adicionar ao `README.md` as seções "Testes" (`make lint`, `make test`, `make test-integracao`, `make test-e2e` e o que cada um exige), "Retenção de 15 minutos" (comportamento e impacto no restart da API de consulta), "Solução de problemas" (permissões em `dados/` e `APP_UID`, conector `COM_FALHA` → `make ingestao-reiniciar`, portas ocupadas, `make clean`) e "Estrutura do repositório"

**Checkpoint**: documentação completa

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: requisitos de desempenho, qualidade e conformidade com a constituição

- [X] T081 [P] Teste e2e de latência e carga em `tests_e2e/test_latencia.py` (marcador `e2e`, duração via env `E2E_DURACAO_S`, padrão 300 s; 1800 s para validação completa): simulador com `--cargas 50 --intervalo-ms 100`; amostra eventos e mede `occurred_at` → visível em `/api/v1/cargas/{id}/eventos`; asserta p95 ≤ 60 s (SC-002) e nenhum evento perdido (SC-003, SC-004); alvo `test-e2e-latencia` no `Makefile`
- [X] T082 [P] Criar `tests_e2e/conftest.py` com fixtures: verificação de que o ambiente está no ar (pula testes se `/health/ready` das APIs falhar), cliente `httpx` para cada API, helper que gera arquivos via `contratos` diretamente em `dados/eventos`, limpeza de `dados/` entre testes e `X-API-Key` lido do `.env`
- [X] T083 Rodar `make lint` e corrigir todas as violações de `ruff` e `mypy --strict` nos quatro pacotes
- [X] T084 Rodar `make test` e garantir cobertura ≥ 80% nas camadas `dominio`, `services` e `adapters` dos três serviços e em `contratos`; adicionar testes onde faltar
- [X] T085 [P] Revisar os três Dockerfiles e `infra/connect/Dockerfile`: tags fixas (nenhuma `latest`), multi-stage, `python:3.12.16-slim-trixie`, `USER` não-root, sem ferramentas de build na imagem final, `.dockerignore` na raiz excluindo `.venv`, `dados`, `specs`, caches e `.env`; rodar `make scan` sem vulnerabilidades HIGH/CRITICAL corrigíveis (princípio VII)
- [X] T086 [P] Revisar `docker-compose.yml`: todos os serviços de longa duração com `healthcheck` e `depends_on: condition: service_healthy`; jobs únicos (`kafka-init`) consumidos via `service_completed_successfully` e `simulador` apenas sob demanda (constituição 1.0.1, princípio VI); portas/volumes/rede explícitos, nenhum segredo literal, `restart: unless-stopped` nos serviços longos
- [X] T087 Executar `make up` do zero e seguir [quickstart.md](./quickstart.md) §0–§4 e §7, registrando divergências; corrigir README/quickstart conforme o comportamento real
- [X] T088 [P] Verificar propagação do `correlation_id`: um evento gerado pelo simulador tem o mesmo `correlation_id` nos logs do simulador, no header Kafka e nos logs da API de consulta; documentar o comando de verificação no README
- [X] T089 Remover o arquivo vazio `a.py` da raiz após confirmar com o usuário que não é usado

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sem dependências
- **Foundational (Fase 2)**: depende da Fase 1 — **bloqueia todas as histórias**
- **US1 (Fase 3)**: depende só da Fase 2 (não precisa do Kafka para ser testada)
- **US2 (Fase 4)**: depende da Fase 2; para o teste ponta a ponta usa o simulador da US1 (ou arquivos gerados pelo helper do T082)
- **US3 (Fase 5)**: depende da Fase 2; T056 depende de US2 (mensagens publicadas pelo Connect)
- **US4 (Fase 6)**: depende da Fase 2 e de T058 (publicar eventos de teste); T065 depende de US1 + US2
- **US5 (Fase 7)**: depende de US1–US4 concluídas
- **Polish (Fase 8)**: depende de todas as histórias

### Grafo de conclusão

```text
Setup → Foundational ─┬─▶ US1 ─────────────┐
                      ├─▶ US2 ──▶ US3(T056) ├─▶ US5 ─▶ Polish
                      ├─▶ US3 ──────────────┤
                      └─▶ US4 ──────────────┘
```

### Within Each User Story

- Testes primeiro (devem falhar), depois config/observabilidade → adapters → services → api → main → Docker/compose → Makefile
- Checkpoint ao final de cada fase

### Parallel Opportunities

- Fase 1: T003–T006 e T008–T010 em paralelo
- Fase 2: T013 e T014 em paralelo (antes de T015/T016)
- Após a Fase 2, US1, US2, US3 e US4 podem ser desenvolvidas em paralelo por pessoas diferentes
- Dentro de cada história, todas as tarefas de teste [P] e as tarefas [P] de config/observabilidade/adapters independentes

---

## Parallel Example: User Story 1

```bash
# Testes da US1 em paralelo:
Task: "T021 Testes da máquina de estados em simulador/tests/unit/test_carga.py"
Task: "T022 Testes do escritor em simulador/tests/unit/test_escritor_arquivo.py"
Task: "T023 Testes do serviço em simulador/tests/unit/test_servico.py"
Task: "T024 Teste de contrato em simulador/tests/contract/test_eventos_validos.py"

# Implementação independente em paralelo:
Task: "T025 config em simulador/src/simulador/config.py"
Task: "T026 gerador em simulador/src/simulador/dominio/gerador.py"
```

## Parallel Example: User Story 2

```bash
Task: "T035 Testes do cliente Connect"      Task: "T036 Testes do serviço"
Task: "T037 Testes da API"                   Task: "T038 Contrato OpenAPI"
Task: "T040 infra/connect/Dockerfile"        Task: "T041 config versionada do conector"
Task: "T044 config.py"  Task: "T045 observabilidade.py"  Task: "T047 adapters/pastas.py"
```

## Parallel Example: User Story 4

```bash
Task: "T060 projeção"  Task: "T061 processador"  Task: "T062 API"  Task: "T063 contrato"  Task: "T064 integração"
Task: "T066 config.py"  Task: "T067 observabilidade.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Fase 1 (Setup) → Fase 2 (Foundational)
2. Fase 3 (US1) → **parar e validar**: simulador gera arquivos válidos (quickstart §2)
3. Demonstrar a massa de dados

### Incremental Delivery

1. Setup + Foundational → contrato e broker prontos
2. US1 → arquivos de eventos (MVP)
3. US2 → eventos chegam ao tópico, ingestão operável
4. US3 → retenção/ordenação comprovadas e ferramentas de inspeção
5. US4 → consultas ponta a ponta
6. US5 → README
7. Polish → desempenho (SC-002/SC-003), cobertura, revisão Docker

### Notes

- [P] = arquivos diferentes, sem dependências pendentes
- Commits em Conventional Commits ao final de cada tarefa ou grupo lógico
- Mudanças em contratos (`contracts/`, JSON Schema, OpenAPI) devem ser destacadas na revisão
- T043 é o ponto de maior risco técnico (configuração do conector): validado — FilePulse adotado

---

## Phase 9: Convergence

- [X] T090 CRITICAL: Encaminhar todo o `logging` da stdlib (uvicorn, httpx, aiokafka) pelo `structlog.stdlib.ProcessorFormatter` com `JSONRenderer` em `api_consulta/src/api_consulta/observabilidade.py` e `controle_ingestao/src/controle_ingestao/observabilidade.py` (handler raiz + `log_config` do uvicorn via `--log-config` ou `uvicorn.config.LOGGING_CONFIG` nos Dockerfiles), garantindo `timestamp`, `level`, `service` e `correlation_id` quando houver; adicionar teste que captura a saída de um logger stdlib e valida JSON per Constitution V (contradicts)
- [ ] T091 Executar `E2E_DURACAO_S=1800 make test-e2e-latencia` com 50 cargas e registrar em `specs/001-pipeline-eventos-transportadora/quickstart.md` (§6) o resultado (eventos, taxa, p95, perdas = 0) per SC-003 (partial)
- [X] T092 Criar teste e2e em `tests_e2e/test_broker_indisponivel.py` (marcador `e2e`): com ingestão ativa, `docker compose stop kafka` → gerar 20 arquivos → `/api/v1/ingestao` e `/health/ready` refletem a falha (`COM_FALHA`/`INICIANDO` ou `kafka: indisponivel`) → `docker compose start kafka` → todos os 20 eventos aparecem na API de consulta sem perda per Spec Edge Cases "Barramento indisponível" (partial)
- [ ] T093 Validar a expiração efetiva do tópico: gerar eventos, aguardar ~17 min sem novos eventos e confirmar com `make topicos-offsets` que o *log start offset* avançou e que `/api/v1/resumo` retorna `total_eventos: 0` (antes e depois de `docker compose restart api-consulta`); registrar o resultado no quickstart §5 per US3/AC3 (partial)
- [X] T094 Adicionar métrica `consulta_erros_total{tipo}` (`consumo`, `envio_dlq`) em `api_consulta/src/api_consulta/observabilidade.py`, incrementada em `adapters/consumidor_kafka.py` (falha no loop de consumo) e `services/processador.py` (falha ao publicar no DLQ), com testes unitários per Constitution V (partial)
- [X] T095 Estender `tests_e2e/test_controle_ingestao.py` com cenário de backlog: pausar, gerar ~5.000 arquivos, retomar e confirmar `pendentes = 0` e todos em `dados/backup` sem falha do conector per Spec Edge Cases "Grande volume de arquivos acumulados" (partial)
- [X] T096 Revisar e registrar no `plan.md` (Summary e Complexity Tracking) a autorrecuperação do FilePulse em `controle_ingestao/src/controle_ingestao/services/ingestao.py` (vigia de 15 s + restart da instância), justificando a complexidade adicional com o research R1 per plan: Summary / Constitution VII (unrequested)

---

## Phase 10: Convergence

- [ ] T097 Reexecutar `tests_e2e/test_broker_indisponivel.py` e `tests_e2e/test_controle_ingestao.py::test_backlog_grande_e_processado_apos_retomada` com a configuração atual do conector (limpeza `COMPLETED`, sem `fs.cleanup.policy.triggered.on`), após a T091; se passarem, manter a afirmação do research R1; se falharem, corrigir a configuração ou o texto de `research.md` per Spec Edge Cases "Barramento indisponível" / "Grande volume de arquivos" (partial)

---

## Phase 11: Convergence

- [ ] T098 Substituir o teste de carga em `tests_e2e/test_latencia.py` por uma validação de volume pequeno (≈10 cargas, até 500 eventos, poucos minutos) que verifica 100% dos eventos na API de consulta sem perda e p95 ≤ 60 s; trocar o alvo `test-e2e-latencia` do `Makefile` por `test-e2e-simulacao` (sem `E2E_DURACAO_S`); executar em ambiente limpo (`make clean && make up && make ingestao-ativar`) e marcar a T091 como substituída por esta tarefa per SC-003 (contradicts)
- [ ] T099 Reduzir o cenário de backlog em `tests_e2e/test_controle_ingestao.py::test_backlog_grande_e_processado_apos_retomada` para ~200 arquivos e ~10 cargas, mantendo a verificação de pendentes = 0 e todos em `dados/backup`, e reexecutá-lo junto com a T097 per SC-003 / Premissas (contradicts)
- [ ] T100 Alinhar ao escopo de volume pequeno o `plan.md` (Technical Context: Performance Goals e Scale/Scope), o `quickstart.md` (§6), o `README.md` (tabela de Testes e referências a carga de 30 min) e o `research.md` (R11, "escala alvo") per plan: Technical Context / Constitution (README atualizado no mesmo PR) (partial)
- [ ] T101 Reduzir `test_desempenho_10k_cargas` em `api_consulta/tests/unit/test_projecao.py` para ~500 cargas (renomeando o teste), mantendo o limite de 1 s per SC-008 (unrequested)

---

## Phase 12: Convergence

- [ ] T102 Não executar a T091 (teste de carga de 1800 s com 50 cargas, fora do escopo de volume pequeno): marcá-la como `[X]` com a nota "substituída pela T098", e marcar T100 e T101 como `[X]` após confirmar que `plan.md`/`quickstart.md` §6/`README.md`/`research.md` R11 já estão alinhados e que `test_desempenho_volume_de_simulacao` usa 500 cargas per SC-003 / Clarifications (contradicts)
- [ ] T103 Em ambiente limpo (`make clean && make up && make ingestao-ativar`), executar `tests_e2e/test_simulacao.py` (`make test-e2e-simulacao`), `tests_e2e/test_broker_indisponivel.py` e `tests_e2e/test_controle_ingestao.py::test_backlog_acumulado_e_processado_apos_retomada`; registrar no `quickstart.md` §6 o resultado (eventos, perdas = 0, p95) e marcar T097, T098 e T099 como `[X]` se passarem — se falharem, corrigir a configuração do conector ou o `research.md` R1 per SC-002 / SC-003 / Spec Edge Cases "Barramento indisponível" e "Grande volume de arquivos" (partial)
- [ ] T104 Reescrever em `research.md` R1 as justificativas baseadas no teste de carga da T091 ("~43 eventos/s", "sob carga") como observação histórica de um ensaio fora do escopo, mantendo as decisões (`fs.listing.task.delegation.enabled=true`, limpeza em `COMPLETED`) per plan: escopo de volume pequeno (partial)

---

## Phase 13: Convergence

- [ ] T105 Mudar o padrão do simulador para gerar 10 eventos e encerrar: em `simulador/src/simulador/config.py` usar `max_eventos=10` por padrão e adicionar a opção explícita `--continuo` (env `SIMULADOR_CONTINUO`, ignora `max_eventos`/`duracao_s` e roda até interrupção); expor em `simulador/src/simulador/__main__.py`, ajustar `.env.example` (`SIMULADOR_*`) e `simulador/tests/unit/` (padrão gera exatamente 10 arquivos; `--continuo` só para com o sinal de parada) per FR-005 / US1/AC1 (contradicts)
- [ ] T106 Reduzir para 10 eventos os testes e2e: `tests_e2e/test_simulacao.py` (`EVENTOS = 10`), `tests_e2e/test_fluxo_completo.py` (`gerar(10)`), `tests_e2e/test_controle_ingestao.py` (`test_arquivos_validos_vao_para_backup` e `test_backlog_acumulado_e_processado_apos_retomada` com 10 arquivos) e `tests_e2e/test_broker_indisponivel.py` (`gerar(10)`); atualizar a descrição do alvo `test-e2e-simulacao` no `Makefile`; a T103 passa a executar estes volumes per SC-003 / Spec Edge Cases "Arquivos acumulados" (contradicts)
- [ ] T107 Criar teste de integração em `api_consulta/tests/integration/test_topico.py` (marcador `integration`, testcontainers) que cria um tópico com retenção curta (`retention.ms=30000`, `segment.ms` pequeno, broker com `log.retention.check.interval.ms` reduzido), publica 10 eventos e confirma em poucos minutos que o *log start offset* avançou e as mensagens não são mais lidas; marcar a T093 como `[X]` com a nota "substituída pela T107" per US3/AC3 / FR-016 (missing)
- [ ] T108 Alinhar a documentação ao padrão de 10 eventos: `README.md` (exemplo de `make simular`, tabela de opções com o padrão 10 e `--continuo`, tabela de testes sem "300 eventos"), `specs/001-pipeline-eventos-transportadora/quickstart.md` (§2, §3, §5 com o teste de retenção curta da T107, §6), `specs/001-pipeline-eventos-transportadora/contracts/simulador-cli.md` (padrões e `--continuo`) e `plan.md` (Technical Context: Performance Goals com 10 eventos) per FR-026 / plan: Technical Context (partial)
