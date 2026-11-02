# Pipeline de Eventos da Transportadora

Simulação local de uma arquitetura orientada a eventos: um simulador gera eventos do ciclo de vida de
cargas (recebimento → transporte → entrega), o **Kafka Connect** ingere os arquivos JSON e publica em
um tópico **Kafka**, e uma **API de consulta** mantém o status atual de cada carga. Uma **API de
controle** opera a ingestão (status, ativar, pausar, retomar, reiniciar, remover).

```text
                     ┌──────────────────────────────┐
 make simular  ──▶   │ simulador (Python)           │
                     │ grava 1 JSON por evento      │
                     └──────────────┬───────────────┘
                                    ▼  escrita atômica (.tmp + rename)
                          dados/eventos/*.json
                                    │
            ┌───────────────────────┼─────────────────────────────┐
            │  Kafka Connect + FilePulse                          │
            │  lê o arquivo, faz o parse, chave = carga_id         │◀── API de controle :8001
            │  sucesso → dados/backup   inválido → dados/erros     │    (REST do Connect)
            └───────────────────────┬─────────────────────────────┘
                                    ▼
             tópico transportadora.carga.eventos.v1  (3 partições, retenção 15 min)
                                    │
                                    ▼
            ┌───────────────────────────────────────────────┐
            │ API de consulta :8002 (FastAPI + aiokafka)     │──▶ fora do contrato →
            │ projeção em memória (janela de 15 min)        │    transportadora.carga.eventos-dlq.v1
            └───────────────────────────────────────────────┘
```

| Componente | Tecnologia | Porta |
|---|---|---|
| Broker | Kafka 3.9 (Confluent 7.9.10), KRaft, 1 nó | 9092 |
| Ingestão | Kafka Connect 7.9.10 + FilePulse 2.18.0 | 8083 |
| API de controle | FastAPI | 8001 |
| API de consulta | FastAPI + aiokafka | 8002 |
| Simulador | Python 3.12 (sob demanda) | 9100 (métricas) |

O projeto é uma **simulação de arquitetura** com volumes pequenos de dados (dezenas de cargas,
centenas de eventos): o foco é o fluxo, os contratos e a operação, não desempenho.

Especificação, plano e contratos: [specs/001-pipeline-eventos-transportadora/](specs/001-pipeline-eventos-transportadora/).

## Pré-requisitos

- Docker Engine 24+ (ou Docker Desktop/Colima) com Docker Compose v2 e ~4 GB de RAM livres
- GNU Make, `curl` e `jq`
- Para rodar testes e ferramentas localmente: Python 3.12 e o ambiente virtual `.venv` do projeto
  (`.venv/bin/pip install uv==0.13.6 && make install`)

## Configuração

```bash
cp .env.example .env
# edite CONTROLE_API_KEY (chave exigida nas rotas que alteram a ingestão)
```

As principais variáveis estão comentadas em [.env.example](.env.example): portas, nomes dos tópicos,
retenção (`TOPICO_RETENCAO_MS`, `RETENCAO_PROJECAO_S`), UID/GID dos containers e parâmetros do
simulador.

## Executando a simulação

```bash
make up                                    # sobe kafka, connect e as duas APIs (aguarda ficarem saudáveis)
make ingestao-ativar                       # cria o conector (a ingestão NÃO começa sozinha)
make simular ARGS="--cargas 20 --duracao-s 120"   # gera eventos por 2 min
make consulta-resumo                       # contagem de cargas por status
make consulta-cargas STATUS=ENTREGUE       # lista cargas entregues
curl -s localhost:8002/api/v1/cargas/<carga_id>/eventos | jq   # histórico de uma carga
make down                                  # derruba o ambiente
```

Opções do simulador (`make simular ARGS="..."`):

| Opção | Padrão | Descrição |
|---|---|---|
| `--cargas N` | 20 | cargas em andamento ao mesmo tempo |
| `--intervalo-ms MS` | 500 | intervalo entre ciclos (a cada ciclo ~10% das cargas avançam uma etapa) |
| `--duracao-s S` / `--max-eventos N` | 0 (infinito) | critérios de parada |
| `--prob-falha P` | 0.15 | probabilidade de falha em cada tentativa de entrega (máx. 3) |
| `--seed N` | aleatório | execução reprodutível |

`Ctrl+C` encerra o simulador sem deixar arquivos parciais.

### Alvos do Makefile

| Alvo | O que faz |
|---|---|
| `make up` / `make down` / `make clean` | sobe / derruba / derruba e apaga volumes e `dados/` (inclusive o backup) |
| `make status` / `make logs S=<serviço>` | estado dos containers / logs |
| `make simular ARGS=...` | executa o simulador em container |
| `make validar-eventos` | valida os JSON de `dados/eventos` e `dados/backup` contra o contrato |
| `make ingestao-status` / `-ativar` / `-pausar` / `-retomar` / `-reiniciar` / `-remover` | operam a ingestão via API de controle |
| `make topicos` / `make topicos-offsets` | configuração dos tópicos / offsets inicial e final por partição |
| `make consumir N=5` / `make dlq N=5` | lê mensagens (com chave e headers) do tópico / do DLQ |
| `make publicar-evento-teste` / `make publicar-evento-invalido` | publica direto no tópico um evento válido / fora do contrato |
| `make consulta-resumo` / `consulta-cargas` / `consulta-consumo` | consultas rápidas à API de consulta |
| `make lint` / `make test` / `make test-integracao` / `make test-e2e` | qualidade e testes (ver abaixo) |
| `make build` / `make scan` / `make ci` | imagens; varredura Trivy (falha em HIGH/CRITICAL corrigíveis nas imagens próprias e apenas reporta a imagem do Connect, derivada da Confluent); todos os gates |

## Verificando cada etapa

| Etapa | Comando | Resultado esperado |
|---|---|---|
| Containers | `make status` | `kafka`, `connect`, `controle-ingestao`, `api-consulta` *healthy*; `kafka-init` `Exited (0)` |
| Simulador | logs do `make simular`; `curl localhost:9100/metrics` durante a execução | linhas JSON `simulacao_resumo` a cada 10 s; `simulador_eventos_gerados_total` |
| Arquivos | `ls dados/eventos dados/backup dados/erros` | pendentes em `eventos/`, ingeridos em `backup/`, inválidos em `erros/` |
| Ingestão | `make ingestao-status` | `estado: ATIVA` e contagem `arquivos.{pendentes,em_backup,com_erro}` |
| Saúde da ingestão | `curl localhost:8001/health/ready` | `kafka_connect` e `kafka` = `ok` |
| Tópico | `make topicos`, `make topicos-offsets`, `make consumir N=5` | 3 partições, `retention.ms=900000`; chave = `carga_id`; headers `correlation_id`, `event_type` |
| DLQ | `make publicar-evento-invalido && make dlq N=1` | mensagem com header `erro_tipo:CONTRATO_INVALIDO` |
| API de consulta | `curl localhost:8002/health/ready`, `make consulta-consumo`, `make consulta-resumo` | `catch_up_concluido: true`, `lag_total` ≈ 0, contagens por status |
| Documentação interativa | <http://localhost:8001/docs> e <http://localhost:8002/docs> | OpenAPI de cada API |

Rastreabilidade: o `correlation_id` de uma carga é o mesmo no arquivo, no header Kafka e nos logs das
APIs. Para seguir uma carga:

```bash
ID=$(make -s consulta-cargas | jq -r '.itens[0].correlation_id')
grep -l "$ID" dados/backup/*.json | head -1                     # arquivo de origem
make -s consumir N=500 | grep -c "correlation_id:$ID"            # mensagens no tópico
docker compose logs api-consulta | grep -c "$ID"                 # logs (nível DEBUG)
```

## Testes

| Comando | Escopo | Requer |
|---|---|---|
| `make lint` | `ruff` (lint + format), `mypy --strict`, `pip-audit` | `.venv` |
| `make test` | unitários + contrato, cobertura mínima de 80% | `.venv` |
| `make test-integracao` | consumidor e tópicos contra Kafka real (testcontainers) | Docker |
| `make test-e2e` | fluxo completo, controle da ingestão, tópico | `make up` |
| `make test-e2e-simulacao` | simulação ponta a ponta (10 cargas, 300 eventos): todos chegam à API, p95 ≤ 60 s | `make up` |
| `make ci` | lint → test → build → scan → integração | Docker |

Os testes de contrato comparam o código com os contratos versionados em
[specs/.../contracts/](specs/001-pipeline-eventos-transportadora/contracts/) (JSON Schema do evento,
OpenAPI das duas APIs, configuração do conector). Toda mudança de contrato deve atualizar esses
arquivos no mesmo PR.

## Retenção de 15 minutos

- O tópico guarda mensagens por 15 min (`retention.ms`), com segmentos de 1 min para que a expiração
  ocorra de fato (entre 15 e ~17 min).
- A API de consulta aplica a **mesma janela** sobre o `occurred_at` dos eventos: eventos antigos são
  removidos a cada 30 s e a carga deixa de existir (404) quando todos os seus eventos expiram. O
  resultado é o mesmo antes e depois de reiniciar a API, que relê o tópico ao subir.
- Os arquivos ingeridos ficam em `dados/backup` **sem limpeza automática**; remova-os com
  `make clean` ou manualmente.

## Solução de problemas

| Sintoma | Causa provável / ação |
|---|---|
| Arquivos ficam em `dados/eventos` e o Connect não os move | Permissão: os containers rodam com `APP_UID`/`APP_GID` (padrão 1000). Ajuste no `.env` ou `chmod 775 dados/*`. Confirme também se a ingestão está `ATIVA`. |
| `make ingestao-status` mostra `COM_FALHA` | Veja `tarefas[].erro`; `make ingestao-reiniciar`. A falha conhecida do FilePulse ao pausar/retomar ("has already been shut down") é corrigida automaticamente pela API de controle (log `conector_recuperado`). |
| `estado: INEXISTENTE` | A ingestão não é ativada automaticamente: `make ingestao-ativar`. |
| `401` nas rotas de ingestão | Header `X-API-Key` diferente de `CONTROLE_API_KEY` do `.env`. |
| API de consulta `503` em `/health/ready` | Ainda relendo o tópico (catch-up) ou broker fora; veja `make consulta-consumo` e `make logs S=api-consulta`. |
| Container `connect` reiniciando (exit 137 / OOM) | Pouca memória na VM do Docker. As JVMs têm heap fixo (`KAFKA_HEAP_OPTS` no compose: broker 768 MB, Connect 1 GB); garanta ~4 GB livres para o Docker. |
| Porta ocupada | Altere `*_PORTA` no `.env`. |
| `make test-integracao` falha ao subir o container Ryuk (Colima/Docker Desktop) | O Makefile já define `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`; rode pelo `make`. |
| Recomeçar do zero | `make clean && make up`. |

## Estrutura do repositório

```text
contratos/           contrato do evento (Pydantic + JSON Schema v1), compartilhado
simulador/           gerador de eventos (CLI + Dockerfile)
controle_ingestao/   API de controle do Kafka Connect (+ conectores/ com a config versionada)
api_consulta/        API de consulta (consumidor aiokafka, projeção, DLQ)
infra/connect/       imagem do Kafka Connect com FilePulse
infra/kafka/         script idempotente de criação dos tópicos
tests_e2e/           testes ponta a ponta contra o ambiente em execução
dados/               eventos/, backup/, erros/ (fora do git)
specs/               especificação, plano, contratos e tarefas (Spec Kit)
```
