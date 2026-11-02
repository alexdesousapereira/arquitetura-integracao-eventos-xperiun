# Quickstart: Validação ponta a ponta

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Guia de validação dos cenários da spec. Comandos referem-se aos alvos do `Makefile` e às portas
padrão definidas em `.env.example`. Contratos: [contracts/](./contracts/).

## Pré-requisitos

- Docker Engine 24+ e Docker Compose v2
- GNU Make, `curl`, `jq`
- (opcional, para testes locais) Python 3.12 e `uv`
- ~4 GB de RAM livres para os containers

## 0. Configuração

```bash
cp .env.example .env          # ajuste CONTROLE_API_KEY
make up                       # kafka, kafka-init, connect, controle-ingestao, api-consulta
make status                   # todos devem aparecer healthy
```

**Esperado**: `make up` retorna em < 3 min; `make status` lista os serviços `healthy` e o
`kafka-init` como `exited (0)`.

## 1. Tópicos (US3)

```bash
make topicos                  # descreve os tópicos
```

**Esperado**: `transportadora.carga.eventos.v1` com 3 partições, `retention.ms=900000`,
`segment.ms=60000`; `transportadora.carga.eventos-dlq.v1` com 1 partição.

## 2. Simulador (US1)

```bash
make simular ARGS="--cargas 20 --duracao-s 60"
ls dados/eventos | head       # (antes de ativar a ingestão os arquivos acumulam aqui)
```

**Esperado**: arquivos `*.json` sem nenhum `.tmp` remanescente após o término; cada arquivo valida
contra [evento-carga.schema.json](./contracts/evento-carga.schema.json)
(`make validar-eventos`).

## 3. Ingestão e controle (US2)

```bash
curl -s localhost:8001/api/v1/ingestao | jq .estado                 # "INEXISTENTE"
make ingestao-ativar                                                # PUT com X-API-Key
curl -s localhost:8001/api/v1/ingestao | jq '{estado, arquivos}'    # "ATIVA"; pendentes → 0
```

**Esperado**: em ≤ 30 s os arquivos saem de `dados/eventos` para `dados/backup`.

Pausa/retomada (SC-005):

```bash
make ingestao-pausar
make simular ARGS="--max-eventos 50"
curl -s localhost:8001/api/v1/ingestao | jq .arquivos.pendentes     # 50, sem ingestão
make ingestao-retomar                                               # pendentes → 0 em ≤ 30 s
```

Arquivo inválido (edge case):

```bash
echo '{ quebrado' > dados/eventos/invalido.json
```

**Esperado**: o arquivo vai para `dados/erros/`; `arquivos.com_erro` incrementa; estado continua
`ATIVA`.

Autorização: `curl -X POST localhost:8001/api/v1/ingestao/pausar` sem `X-API-Key` → `401`
`application/problem+json`.

## 4. API de consulta (US4)

```bash
curl -s localhost:8002/api/v1/resumo | jq
ID=$(curl -s 'localhost:8002/api/v1/cargas?size=1' | jq -r '.itens[0].carga_id')
curl -s localhost:8002/api/v1/cargas/$ID | jq
curl -s localhost:8002/api/v1/cargas/$ID/eventos | jq '.eventos[].event_type'
curl -s 'localhost:8002/api/v1/cargas?status=ENTREGUE&size=5' | jq '.itens[].status'
curl -s -o /dev/null -w '%{http_code}\n' localhost:8002/api/v1/cargas/CRG-00000000   # 404
curl -s localhost:8002/api/v1/consumo/status | jq .lag_total                          # ~0
```

**Esperado**: histórico em ordem cronológica e coerente com o ciclo de vida; contagens do resumo
batem com a soma da listagem por status.

Reconstrução após restart (FR-022):

```bash
docker compose restart api-consulta && sleep 15
curl -s localhost:8002/api/v1/resumo | jq .total_eventos   # mesmo valor (dentro da retenção)
```

Contrato inválido → DLQ:

```bash
make publicar-evento-invalido    # publica JSON válido sem carga_id direto no tópico
make dlq                         # mostra a mensagem com header erro_tipo=CONTRATO_INVALIDO
```

## 5. Retenção (US3, cenário 3)

Rode `make simular ARGS="--duracao-s 60"` e aguarde ~17 min sem gerar novos eventos;
`make topicos-offsets` mostra o *log start offset* avançado. Já após ~15 min (sem precisar de
restart), `/api/v1/resumo` retorna `total_cargas: 0` e `total_eventos: 0`, e consultar uma das
cargas antigas retorna `404`; o mesmo vale depois de `docker compose restart api-consulta`.

## 6. Simulação ponta a ponta (SC-002, SC-003)

```bash
make test-e2e-simulacao   # 10 cargas, 300 eventos: todos visíveis na API, p95 ≤ 60 s, lag 0
```

**Esperado**: 100% dos eventos gerados aparecem no histórico da API de consulta, sem perda nem
duplicidade. O projeto é uma simulação de arquitetura: testes de carga/estresse estão fora do
escopo.

## 7. Testes automatizados

```bash
make lint                # ruff check + ruff format --check + mypy
make test                # unit + contract (sem Docker)
make test-integracao     # testcontainers (requer Docker)
make test-e2e            # requer `make up`
make scan                # Trivy nas imagens (HIGH/CRITICAL)
make ci                  # todos os gates de merge da constituição
```

## 8. Encerramento

```bash
make down                # remove containers; `make clean` também apaga `dados/eventos`, `dados/backup` e `dados/erros` (remoção manual do backup)
```
