# Contrato: Tópicos Kafka

Convenção (constituição, princípio I): `<dominio>.<entidade>.<evento>.v<N>`.

## `loja.pedido.eventos.v1`

| Propriedade          | Valor                                        |
|----------------------|----------------------------------------------|
| Produtor             | Kafka Connect (conector `arquivos-eventos-loja`) |
| Consumidores         | API de consulta                              |
| Partições            | 3                                            |
| Fator de replicação  | 1 (cluster de 1 broker — simulação)          |
| `cleanup.policy`     | `delete`                                     |
| `retention.ms`       | `900000` (15 min, configurável via `TOPICO_RETENCAO_MS`) |
| `segment.ms`         | `60000` (necessário para a retenção ser observável) |
| Chave                | `pedido_id` (string UTF-8)                    |
| Valor                | JSON conforme [evento-pedido.schema.json](./evento-pedido.schema.json), sem envelope de schema |
| Headers              | `correlation_id`, `event_type`               |
| Garantia             | at-least-once; ordenação garantida por `pedido_id` |

## `loja.pedido.eventos-dlq.v1`

| Propriedade          | Valor                                        |
|----------------------|----------------------------------------------|
| Produtor             | API de consulta (eventos fora do contrato)   |
| Consumidores         | Operador (inspeção manual via CLI)           |
| Partições            | 1                                            |
| Fator de replicação  | 1                                            |
| `retention.ms`       | `86400000` (24 h)                            |
| Chave                | chave original (se houver)                   |
| Valor                | bytes originais da mensagem, sem alteração   |
| Headers              | `erro_tipo` (`JSON_INVALIDO` \| `CONTRATO_INVALIDO`), `erro_motivo` (texto, ≤ 1000 chars), `topico_origem`, `particao_origem`, `offset_origem`, `correlation_id` (se extraível) |

## Evolução

- Mudanças compatíveis (novo campo opcional no payload) mantêm `v1` e `event_version: 1`.
- Mudanças incompatíveis exigem `event_version: 2` **e** novo tópico `...eventos.v2`.
