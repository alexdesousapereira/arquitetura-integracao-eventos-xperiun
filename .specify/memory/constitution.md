<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.0.1
Bump rationale: PATCH — esclarecimento do escopo da regra de healthcheck (princípio VI) para
distinguir serviços de longa duração de jobs de execução única; sem mudança de intenção.

Modified principles:
  - VI. Infraestrutura como Código com Docker (regra de healthcheck esclarecida)
Added sections: nenhuma
Removed sections: nenhuma

Templates dependentes: nenhum impacto estrutural.
Follow-up TODOs: nenhum.
-->

# Arquitetura Orientada a Eventos Constitution

## Core Principles

### I. Arquitetura Orientada a Eventos e Contratos de Dados

- Todo evento publicado MUST possuir um schema explícito e versionado (JSON Schema ou Avro),
  armazenado no repositório e, quando houver Schema Registry, registrado nele.
- Evolução de schema MUST ser compatível retroativamente (BACKWARD); mudanças incompatíveis
  exigem novo tópico ou nova versão major do evento.
- Todo evento MUST conter metadados mínimos: `event_id` (UUID), `event_type`, `event_version`,
  `occurred_at` (ISO-8601 UTC), `source` e uma chave de negócio usada como chave de partição
  (ex.: `carga_id`) para garantir ordenação por entidade.
- Tópicos MUST seguir convenção de nomes `<dominio>.<entidade>.<evento>.v<N>` em minúsculas
  e ter retenção, partições e fator de replicação declarados explicitamente.
- Produtores e consumidores MUST ser idempotentes: reprocessar o mesmo evento não pode gerar
  efeitos colaterais duplicados. Consumidores MUST tratar entrega *at-least-once*.
- Mensagens inválidas MUST ser direcionadas a uma Dead Letter Queue (DLQ) em vez de bloquear
  o fluxo ou serem descartadas silenciosamente.
- Conectores Kafka Connect MUST ser declarados como configuração versionada (JSON) e
  gerenciados via REST API do Connect; nunca configurados manualmente sem registro no repositório.

**Rationale**: contratos explícitos e idempotência são o que torna um sistema assíncrono
previsível, reprocessável e evolutivo sem quebrar consumidores.

### II. APIs FastAPI Bem Definidas

- Toda API MUST ser implementada com FastAPI, com modelos de request/response em Pydantic v2;
  nenhum endpoint retorna `dict` não tipado.
- Rotas MUST ser organizadas em `APIRouter` por domínio, com versionamento no path (`/api/v1`).
- O contrato OpenAPI gerado MUST ser tratado como fonte de verdade e revisado em toda mudança
  de endpoint.
- Erros MUST seguir um formato padronizado (RFC 9457 – Problem Details) com códigos HTTP
  semânticos corretos.
- I/O (Kafka, HTTP, disco) MUST ser assíncrono quando a biblioteca suportar; chamadas
  bloqueantes MUST rodar fora do event loop.
- Toda API MUST expor `/health/live` e `/health/ready`; o readiness verifica dependências
  (ex.: broker Kafka, Kafka Connect).
- Configuração MUST vir de variáveis de ambiente via `pydantic-settings`; dependências
  (clientes, settings) MUST ser injetadas via `Depends`.
- Lógica de negócio MUST ficar fora das rotas (camadas `api` → `services` → `adapters`).

**Rationale**: tipagem e contratos explícitos reduzem erros de integração, e a separação de
camadas mantém o código testável e substituível.

### III. Qualidade de Código Python (NÃO NEGOCIÁVEL)

- Python 3.12+ é a versão mínima; dependências MUST ser gerenciadas com `pyproject.toml` e
  lockfile (recomendado: `uv`).
- Todo código MUST ter type hints completos e passar em `mypy --strict` (ou equivalente).
- Lint e formatação MUST usar `ruff` (lint + format); CI falha em qualquer violação.
- Funções públicas MUST ter docstrings concisas; nomes MUST ser descritivos e consistentes.
- Não é permitido `print` para diagnóstico em código de aplicação; usar logging estruturado.
- Segredos, credenciais e caminhos de ambiente MUST NOT ser escritos no código.

**Rationale**: consistência mecânica (tipos, lint, formatação) elimina classes inteiras de
defeitos e reduz o custo de revisão.

### IV. Testes em Camadas

- Testes MUST usar `pytest` (com `pytest-asyncio` para código assíncrono).
- Testes unitários MUST cobrir regras de negócio, geração e validação de eventos, sem depender
  de infraestrutura externa.
- Testes de contrato MUST validar que eventos produzidos e respostas de API obedecem aos
  schemas versionados.
- Testes de integração MUST exercitar o fluxo real (arquivo → Kafka Connect → tópico → API)
  usando containers (Docker Compose ou Testcontainers).
- Cobertura mínima de 80% nas camadas de domínio e serviços; quedas de cobertura bloqueiam merge.
- Bugs corrigidos MUST vir acompanhados de um teste que reproduz a falha.

**Rationale**: em arquiteturas distribuídas, a maior parte das falhas ocorre nas fronteiras;
testes de contrato e integração as tornam visíveis antes da execução real.

### V. Observabilidade e Operabilidade

- Logs MUST ser estruturados em JSON, com `timestamp`, `level`, `service`, `event_id` e
  `correlation_id` quando aplicável.
- O `correlation_id` MUST ser propagado do evento de origem até a API de consulta
  (headers Kafka e headers HTTP).
- Cada serviço MUST expor métricas (formato Prometheus) incluindo, no mínimo: eventos
  produzidos/consumidos, erros, mensagens em DLQ e latência de endpoints.
- O estado de cada etapa (simulador, conectores, tópicos, consumidores) MUST ser consultável
  via endpoint ou comando documentado, incluindo lag de consumidores.

**Rationale**: sistemas assíncronos falham de forma silenciosa; sem rastreabilidade de ponta a
ponta não é possível diagnosticar onde um evento se perdeu.

### VI. Infraestrutura como Código com Docker

- Todo componente (Kafka, Kafka Connect, APIs, simulador) MUST rodar em container definido
  no repositório e orquestrado por `docker compose`.
- Imagens MUST usar tags fixas (nunca `latest`), builds multi-stage, base slim e execução
  como usuário não-root.
- Kafka MUST rodar em modo KRaft (sem ZooKeeper).
- Todo serviço de longa duração MUST declarar `healthcheck`, e dependências entre serviços MUST
  usar `depends_on` com `condition: service_healthy`. Jobs de execução única (ex.: criação de
  tópicos, simulador sob demanda) MUST ser consumidos via
  `condition: service_completed_successfully` ou executados explicitamente sob demanda.
- Volumes, redes e portas MUST ser declarados explicitamente; configurações MUST vir de `.env`
  com um `.env.example` sempre atualizado e sem segredos.
- O ambiente completo MUST subir com um único comando documentado (ex.: `make up`).

**Rationale**: reprodutibilidade total do ambiente é pré-requisito para testes de integração
confiáveis e para qualquer pessoa executar a arquitetura localmente.

### VII. Simplicidade e Segurança por Padrão

- Adotar a solução mais simples que atenda ao requisito (YAGNI); toda complexidade adicional
  (novo componente, novo padrão) MUST ser justificada no plano da feature.
- Preferir componentes oficiais e mantidos (ex.: conectores Confluent/Apache, `confluent-kafka`)
  a implementações próprias.
- Entradas externas MUST ser validadas na fronteira (Pydantic/schema) antes de processamento.
- Endpoints que alteram estado (ex.: pausar/retomar conectores) MUST exigir autenticação
  (mínimo: API key via header) quando expostos fora do ambiente local.
- Dependências MUST ser auditadas (ex.: `pip-audit`) e imagens escaneadas antes de release.

**Rationale**: simplicidade reduz superfície de falha e de ataque; segurança aplicada desde
o início custa menos do que corrigida depois.

## Padrões de Stack e Restrições Técnicas

- **Linguagem**: Python 3.12+.
- **APIs**: FastAPI + Uvicorn, Pydantic v2, pydantic-settings, httpx (cliente HTTP assíncrono).
- **Mensageria**: Apache Kafka (KRaft) e Kafka Connect; cliente Python `confluent-kafka`
  (ou `aiokafka` quando I/O assíncrono for necessário).
- **Contratos**: JSON Schema ou Avro versionados no repositório; Schema Registry quando adotado.
- **Containers**: Docker e Docker Compose v2.
- **Qualidade**: ruff, mypy, pytest, pytest-asyncio, pytest-cov, pre-commit.
- **Estrutura do repositório**: cada componente em diretório próprio com `pyproject.toml`,
  `Dockerfile` e `tests/`; dados de simulação em `dados/`, que MUST permanecer fora do
  versionamento (exceto `.gitkeep`/amostras).
- **Dados**: timestamps MUST estar em UTC (ISO-8601); nomes de campos em `snake_case`;
  arquivos de evento MUST ser escritos de forma atômica (escrita em arquivo temporário +
  rename) para evitar leitura parcial pelo conector.
- **Documentação**: o README MUST permitir subir a infraestrutura, executar a simulação,
  rodar os testes e verificar o status de cada etapa.

## Fluxo de Desenvolvimento e Quality Gates

- Toda feature MUST seguir o fluxo Spec Kit: `specify` → `clarify` (quando houver ambiguidade)
  → `plan` → `tasks` → `implement`.
- O plano de cada feature MUST conter um "Constitution Check" verificando os princípios I–VII;
  violações MUST ser justificadas na seção de complexidade ou corrigidas.
- Commits MUST seguir Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:` ...).
- Gates obrigatórios antes de merge: `ruff check`, `ruff format --check`, `mypy`, `pytest`
  (unitários + contrato), build das imagens Docker e testes de integração do fluxo afetado.
- Mudanças em schemas de eventos ou contratos OpenAPI MUST ser destacadas na revisão e
  validadas quanto à compatibilidade.
- Mudanças que afetem execução ou operação MUST atualizar o README no mesmo PR.

## Governance

- Esta constituição prevalece sobre quaisquer outras práticas do projeto. Em caso de conflito,
  a constituição vence até que seja formalmente emendada.
- **Emendas**: propostas via `/speckit-constitution`, com Sync Impact Report descrevendo
  impacto, e aprovadas pelo responsável do projeto antes do merge.
- **Versionamento** (SemVer):
  - MAJOR: remoção ou redefinição incompatível de princípios ou regras de governança.
  - MINOR: novo princípio/seção ou expansão material de orientações.
  - PATCH: clarificações, ajustes de redação e correções sem efeito semântico.
- **Conformidade**: toda revisão de código e todo plano de feature MUST verificar aderência
  aos princípios; complexidade adicional MUST ser justificada por escrito.
- **Revisão periódica**: a constituição MUST ser revisada ao início de cada nova feature
  relevante ou a cada adoção de nova tecnologia na stack.

**Version**: 1.0.1 | **Ratified**: 2026-11-02 | **Last Amended**: 2026-11-02
