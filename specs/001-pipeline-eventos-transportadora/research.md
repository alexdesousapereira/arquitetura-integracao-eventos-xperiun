# Research: Pipeline de Eventos da Transportadora

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-02

Cada item segue o formato Decision / Rationale / Alternatives considered. Nenhum
`NEEDS CLARIFICATION` permanece no Technical Context.

---

## R1. Conector para ler arquivos JSON de uma pasta

- **Decision**: Kafka Connect com o conector **FilePulse** (`streamthoughts/kafka-connect-file-pulse`
  2.18.0, classe `FilePulseSourceConnector`). Não está no Confluent Hub: a imagem própria baixa o
  zip oficial da release no GitHub, valida o SHA-256 publicado e instala com `confluent-hub install`.
  Configuração-chave ([contracts/conector-filepulse.json](./contracts/conector-filepulse.json)):
  - `LocalFSDirectoryListing` em `/data/eventos` + `RegexFileListFilter` com `^[^.].*\.json$`
    (ignora os arquivos temporários ocultos do simulador); varredura a cada 1 s
  - `LocalBytesArrayInputReader` (arquivo inteiro = 1 registro) + filtro `JSONFilter` (`merge=true`)
    + `ExcludeFilter` do campo bruto `message`
  - `fs.listing.task.delegation.enabled=true`: a própria tarefa lista a pasta. Sem isso, o
    conector pede uma reconfiguração de tarefas (parar/reiniciar a tarefa) a cada leva de arquivos
    novos; sob geração contínua (T091, ~43 eventos/s) foram 67 reconfigurações em 15 min, a
    ingestão caiu para ~30 arquivos/s e a fila cresceu sem limite. Com delegação: 0 reconfigurações
    e fila estável (< 100 arquivos) na mesma carga.
  - `LocalMoveCleanupPolicy`: sucesso → `/data/backup`, falha → `/data/erros`
  - limpeza disparada em `COMPLETED` (padrão): o arquivo vai para o backup após a leitura. A opção
    `COMMITTED` foi testada e **rejeitada**: sob carga (T091) o FilePulse 2.18 deixa de agendar
    arquivos ("Task reconfiguration requested. Skip filesystem listing") e a ingestão para. Com
    `COMPLETED`, uma queda do broker não perde eventos porque o Kafka Connect configura o producer
    de conectores source com retentativas indefinidas (comprovado no teste e2e
    `test_broker_indisponivel.py`); o risco residual é um crash do worker do Connect durante a
    queda do broker, aceito para esta simulação local.
  - `tasks.halt.on.error=false` (arquivo inválido vai para `erros/` e a ingestão continua)
  - estado dos arquivos no tópico interno `_connect-file-pulse-status` (evita reprocessar)
- **Rationale**: monitora a pasta, move os arquivos após a leitura (FR-008, FR-009), faz o parse do
  JSON **por arquivo** (cada evento mantém exatamente os seus campos) e permite definir a chave a
  partir do conteúdo. Validado na T043: 138 eventos publicados, todos válidos contra o contrato;
  arquivo malformado desviado para `dados/erros` com o conector `RUNNING`.
- **Problema conhecido e mitigação**: no FilePulse 2.18, ao parar a instância do conector (pausa,
  reconfiguração, restart) a thread de monitoramento antiga ainda chama
  `requestTaskReconfiguration`, e o Connect marca o conector `FAILED` ("has already been shut
  down"); a ingestão para até um restart. Observado nos testes e2e. A API de controle trata isso:
  (1) `ativar` não reaplica configuração idêntica; (2) após pausar/retomar/reiniciar/ativar, uma
  vigia de 15 s e toda consulta de status detectam exatamente essa falha e reiniciam só a instância
  do conector (`POST /connectors/{nome}/restart`), registrando `conector_recuperado` no log.
  Outras falhas continuam expostas como `COM_FALHA`.
- **Alternatives considered** (testadas na T043 e rejeitadas):
  - SpoolDir `SpoolDirSchemaLessJsonSourceConnector`: entrega o valor como *string*, então
    `ValueToKey`/`HeaderFrom` falham ("Only Struct objects supported"); com `errors.tolerance=all`
    os arquivos eram movidos sem nenhuma mensagem publicada. Além disso, o `MOVE` criou uma pasta
    por arquivo em `finished.path`.
  - SpoolDir `SpoolDirJsonSourceConnector` com `schema.generation.enabled`: o schema é gerado uma
    vez por conector a partir do primeiro arquivo — incompatível com 6 tipos de payload distintos.
  - `FileStreamSourceConnector` (Apache): lê um único arquivo linha a linha e não move arquivos.
  - Producer Python próprio: violaria o requisito de usar Kafka Connect e o princípio VII.

## R2. Chave de partição e headers

- **Decision**: o filtro `AppendFilter` do FilePulse define `$key = {{ $.carga_id }}` (chave =
  `carga_id`, FR-007); o SMT nativo `HeaderFrom$Value` copia `correlation_id` e `event_type` para
  headers Kafka. Conversores: `key.converter=StringConverter`, `value.converter=JsonConverter` com
  `schemas.enable=false`. O FilePulse também adiciona headers `connect.file.*` (nome, URI, hash do
  arquivo de origem), úteis para rastreabilidade.
- **Rationale**: ordenação por carga e propagação do `correlation_id` (FR-024, princípio V) sem
  código próprio.
- **Alternatives considered**: deixar chave nula (perde ordenação por carga); SMT customizado em
  Java (complexidade desnecessária).

## R3. Tratamento de erros e DLQ (fonte não suporta DLQ nativa)

- **Decision**: duas camadas:
  1. **Arquivo inválido** (JSON malformado) → FilePulse move para `dados/erros/` (FR-009).
  2. **Evento fora do contrato** (JSON válido, schema inválido) → a API de consulta valida contra o
     contrato e publica no tópico DLQ `transportadora.carga.eventos-dlq.v1`, com headers
     `erro_motivo`, `erro_tipo`, `topico_origem`, `particao_origem`, `offset_origem`.
  Conector também usa `errors.tolerance=all` + `errors.log.enable=true` para falhas de
  conversão/SMT.
- **Rationale**: `errors.deadletterqueue.*` do Connect só existe para conectores *sink*. As duas
  camadas cobrem a fronteira de arquivo e a fronteira de contrato, conforme princípio I.
- **Alternatives considered**: validar schema dentro do Connect (exigiria Schema Registry + SMT
  customizado); descartar silenciosamente (proibido pela constituição).

## R4. Distribuição Kafka e modo de operação

- **Decision**: `confluentinc/cp-kafka` e `confluentinc/cp-kafka-connect` na **mesma versão
  7.9.10** (Apache Kafka 3.9; versão consultada no Docker Hub em 2026-11-02), com FilePulse
  `2.18.0` (última release, jun/2026).
  Broker único em **KRaft** (papéis `broker,controller` no mesmo nó), fator de replicação 1 para
  tópicos de dados e internos do Connect.
- **Rationale**: KRaft é exigido pela constituição (VI); a linha 7.9 é estável, compatível com o
  FilePulse 2.18 e com o SMT `HeaderFrom`; validado na T043. Mesma linha para
  broker e Connect evita incompatibilidades.
- **Alternatives considered**: `apache/kafka` 4.x (Connect sem `confluent-hub`, sem o utilitário
  `confluent-hub` para instalar o plugin); Redpanda (fora da stack definida).

## R5. Retenção de 15 minutos efetiva

- **Decision**: tópico `transportadora.carga.eventos.v1` com `retention.ms=900000`,
  `segment.ms=60000`, `cleanup.policy=delete`; broker com
  `KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS=60000`. Valores lidos de `.env`
  (`TOPICO_RETENCAO_MS`, padrão 900000).
- **Rationale**: Kafka só apaga segmentos *fechados*; com o `segment.ms` padrão (7 dias) a retenção
  de 15 min nunca seria observada. Segmentos de 1 min + checagem a cada 1 min fazem os eventos
  expirarem entre 15 e ~17 min (FR-016, cenário 3 da US3).
- **Alternatives considered**: apenas `retention.ms` (não observável na prática); `retention.bytes`
  (não corresponde ao requisito temporal).

## R6. Criação de tópicos

- **Decision**: serviço efêmero `kafka-init` no compose, que roda `kafka-topics --create
  --if-not-exists` para o tópico principal (3 partições) e o DLQ (1 partição, retenção 24h), após
  o broker estar `healthy`. Broker com `auto.create.topics.enable=false`.
- **Rationale**: tópicos declarados explicitamente no repositório (princípio I, FR-015);
  idempotente a cada `up`.
- **Alternatives considered**: auto-create (configuração implícita); criação pela API de controle
  (mistura responsabilidades).

## R7. Escrita atômica dos arquivos pelo simulador

- **Decision**: escrever em `dados/eventos/.<nome>.json.tmp`, `flush` + `fsync`, e então
  `os.replace` para `dados/eventos/<nome>.json`. Nome:
  `<occurred_at:%Y%m%dT%H%M%S%fZ>_<carga_id>_<event_id>.json`.
- **Rationale**: `rename` no mesmo filesystem é atômico; o padrão do conector ignora arquivos que
  começam com `.`; o nome ordena lexicograficamente por tempo (FR-004, edge case de leitura parcial).
- **Alternatives considered**: escrever direto no destino (risco de leitura parcial); diretório
  temporário separado (rename entre bind mounts pode não ser atômico).

## R8. Permissões de arquivos entre containers

- **Decision**: simulador roda como UID/GID `1000:1000` (mesmo `appuser` da imagem do Connect);
  `dados/eventos`, `dados/backup`, `dados/erros` criados pelo `make up` com permissão de
  escrita para esse UID. UID configurável por `.env` (`APP_UID`, `APP_GID`).
- **Rationale**: o Connect precisa *mover* arquivos criados pelo simulador; ambos não-root
  (princípio VI).
- **Alternatives considered**: rodar como root (viola constituição); `chmod 777` (inseguro).

## R9. Framework e clientes das APIs

- **Decision**:
  - **API de controle**: FastAPI + `httpx.AsyncClient` (cliente da REST API do Connect, injetado via
    `Depends`, criado no `lifespan`).
  - **API de consulta**: FastAPI + **`aiokafka`** (consumer e producer DLQ assíncronos rodando como
    task no `lifespan`).
  - Ambas: Pydantic v2, `pydantic-settings`, Uvicorn, `structlog` (JSON), `prometheus-client`.
- **Rationale**: a constituição permite `aiokafka` quando I/O assíncrono é necessário; o consumo
  contínuo no mesmo event loop do FastAPI evita threads e locks sobre a projeção em memória.
- **Alternatives considered**: `confluent-kafka` (mais performático, porém síncrono; exigiria
  thread dedicada e sincronização); Faust (projeto pouco mantido).

## R10. Reconstrução do estado ao reiniciar a API de consulta

- **Decision**: o consumer usa `assign()` em todas as partições + `seek_to_beginning()` na
  inicialização, sem commit de offsets (sem consumer group persistente). Lag calculado como
  `end_offset − posição` por partição. `/health/ready` só fica pronto após alcançar os
  `end_offsets` capturados no startup (*catch-up*).
- **Rationale**: a projeção é em memória (assumption da spec); reler o tópico (no máximo 15 min de
  dados) a cada start é barato e determinístico (FR-022).
- **Alternatives considered**: consumer group com commit (perderia o estado após restart);
  persistir projeção em banco (fora de escopo).

## R11. Idempotência e ordenação na projeção

- **Decision**: projeção mantém `event_ids` vistos por carga (dedup, FR-019); histórico ordenado
  por `occurred_at` (desempate por `event_id`); status = tipo do evento com maior `occurred_at`
  (edge case "fora de ordem").
  **Expiração (clarificação 2026-11-02, FR-022a)**: a projeção aplica a mesma janela de retenção do
  tópico (`RETENCAO_PROJECAO_S`, padrão 900 s) sobre `occurred_at`: eventos já fora da janela são
  ignorados ao serem consumidos, e uma task periódica (a cada 30 s) remove eventos expirados dos
  históricos, recalcula status/contagens e apaga cargas sem eventos. Assim o resultado é o mesmo
  antes e depois de um restart. Índice auxiliar ordenado por `occurred_at` (heap) evita varrer
  todas as cargas a cada ciclo.
- **Rationale**: entrega *at-least-once* do Connect pode duplicar eventos após falha antes do
  commit de offset; dedup por `event_id` resolve.
- **Alternatives considered**: dedup global com LRU (desnecessário no volume de simulação, algumas centenas de cargas).

## R12. Autenticação da API de controle

- **Decision**: header `X-API-Key` comparado com `CONTROLE_API_KEY` (env, obrigatório; app não
  sobe sem ele) via `secrets.compare_digest`, aplicado como dependência apenas nas rotas mutáveis
  (FR-012). Leitura de status e health abertas.
- **Rationale**: mínimo exigido pela constituição (VII) sem gestão de usuários (assumption).
- **Alternatives considered**: OAuth2/JWT (excessivo para simulação local).

## R13. Formato de erros

- **Decision**: RFC 9457 (`application/problem+json`) com campos `type`, `title`, `status`,
  `detail`, `instance` e extensão `correlation_id`, via exception handlers globais em ambas as APIs.
  Erros do Connect (4xx/5xx) são traduzidos (ex.: conector inexistente → 404; Connect indisponível
  → 503).
- **Rationale**: princípio II, FR-020.

## R14. Gestão de dependências e estrutura Python

- **Decision**: **uv workspace** na raiz com quatro membros: `contratos` (biblioteca compartilhada
  com modelos Pydantic + JSON Schema do evento), `simulador`, `controle_ingestao`,
  `api_consulta`. Cada membro com `pyproject.toml` próprio; um `uv.lock` na raiz. Python 3.12.
  O ambiente local é o **`.venv` já existente na raiz** (único ambiente do projeto, também usado
  pelos scripts do Spec Kit); o próprio `uv` é instalado nele e listado no grupo `dev` para que
  `uv sync` não o remova. Não criar ambientes virtuais adicionais.
- **Rationale**: o contrato do evento é a fronteira entre simulador e API de consulta; uma única
  fonte evita divergência (princípio I) e permite testes de contrato reais.
- **Alternatives considered**: duplicar modelos (risco de drift); Poetry (uv é mais rápido e
  suporta workspaces nativamente).

## R15. Estratégia de testes

- **Decision**:
  - **Unit** (`pytest`, `pytest-asyncio`): máquina de estados do simulador, escrita atômica,
    projeção (dedup, ordenação, status), tradução de erros do Connect (com `respx`), auth.
  - **Contract**: eventos gerados validados contra `contracts/evento-carga.schema.json`
    (`jsonschema`); JSON Schema gerado pelos modelos Pydantic comparado ao arquivo versionado;
    `app.openapi()` de cada API comparado aos YAML em `contracts/` (snapshot — mudança exige
    atualizar o contrato no mesmo PR).
  - **Integration** (`testcontainers[kafka]`): consumer da API de consulta contra Kafka real
    (dedup, DLQ, catch-up).
  - **E2E** (marcador `e2e`, requer `make up`): simulador → Connect → tópico → API de consulta;
    pausa/retomada via API de controle.
  - Cobertura ≥ 80% em domínio e serviços (`pytest-cov`).
- **Rationale**: princípio IV — as falhas mais prováveis estão nas fronteiras arquivo/Connect/
  tópico/API.

## R16. Observabilidade

- **Decision**: `structlog` com renderer JSON e campos `timestamp`, `level`, `service`,
  `event_id`, `correlation_id`; middleware que lê/gera `X-Correlation-ID`. Métricas em `/metrics`:
  - simulador: `simulador_eventos_gerados_total{event_type}`, `simulador_cargas_ativas`
    (exposto em porta HTTP própria quando em container).
  - controle: `controle_requisicoes_total`, `controle_connect_erros_total`.
  - consulta: `consulta_eventos_consumidos_total{event_type}`, `consulta_eventos_duplicados_total`,
    `consulta_eventos_dlq_total`, `consulta_lag_mensagens{particao}`, latência HTTP (histograma).
  - Connect: status via REST (`/connectors/<nome>/status`) agregado pela API de controle.
- **Rationale**: princípio V e FR-024/FR-025; SC-007 (status de cada etapa em < 1 min).
- **Alternatives considered**: OpenTelemetry completo com collector (desproporcional para simulação
  local; pode ser adicionado depois).

## R17. Orquestração e comando único

- **Decision**: `docker-compose.yml` na raiz com serviços `kafka`, `kafka-init`, `connect`,
  `controle-ingestao`, `api-consulta` e `simulador` (perfil `simulacao`, iniciado sob demanda).
  `Makefile` com alvos `up`, `down`, `simular`, `ingestao-ativar`, `ingestao-pausar`,
  `ingestao-retomar`, `status`, `test`, `test-integracao`, `test-e2e`, `logs`, `lint`.
  Healthchecks em todos os serviços longos e `depends_on: condition: service_healthy`.
- **Rationale**: FR-023, princípio VI, SC-001.
- **Alternatives considered**: ativar o conector automaticamente no `up` (descartado: a spec pede
  ativação via API de controle; `make up` imprime a instrução `make ingestao-ativar`).
