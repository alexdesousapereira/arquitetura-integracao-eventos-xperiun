# Data Model: Pipeline de Eventos da Transportadora

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-02

Contrato formal do evento: [contracts/evento-carga.schema.json](./contracts/evento-carga.schema.json).
Convenções (constituição): campos em `snake_case`, timestamps ISO-8601 em UTC (`Z`).

---

## 1. EventoCarga (envelope — imutável)

Fato ocorrido no ciclo de vida de uma carga. Um arquivo JSON = um evento = uma mensagem Kafka.

| Campo            | Tipo                  | Obrigatório | Regras                                                                 |
|------------------|-----------------------|-------------|------------------------------------------------------------------------|
| `event_id`       | string (UUID v4)      | sim         | Único globalmente; chave de deduplicação                               |
| `event_type`     | enum `TipoEvento`     | sim         | Ver seção 2                                                            |
| `event_version`  | integer               | sim         | `1` nesta versão do contrato                                           |
| `occurred_at`    | string date-time UTC  | sim         | Termina em `Z`; não pode estar mais de 5 min no futuro                 |
| `source`         | string                | sim         | Ex.: `simulador-transportadora`                                        |
| `correlation_id` | string (UUID v4)      | sim         | Constante para toda a jornada de uma carga                             |
| `carga_id`       | string                | sim         | Padrão `^CRG-[0-9A-F]{8}$`; chave de partição                          |
| `payload`        | object                | sim         | Estrutura determinada por `event_type` (seção 3)                       |

Campos extras no envelope são rejeitados (`additionalProperties: false`).

## 2. TipoEvento

| `event_type`                  | Status resultante    | Descrição                                   |
|-------------------------------|----------------------|---------------------------------------------|
| `carga.recebida`              | `RECEBIDA`           | Carga recebida no centro de distribuição    |
| `carga.saiu_para_transporte`  | `EM_TRANSPORTE`      | Carga embarcada em veículo de transferência |
| `carga.em_transito`           | `EM_TRANSITO`        | Atualização de posição durante o trajeto    |
| `carga.saiu_para_entrega`     | `SAIU_PARA_ENTREGA`  | Carga em rota de última milha               |
| `carga.entregue`              | `ENTREGUE`           | Entrega concluída (terminal)                |
| `carga.entrega_falhou`        | `FALHA_ENTREGA`      | Tentativa de entrega falhou                 |

## 3. Payloads por tipo

**Localidade** (reutilizada): `cidade` (string, 1–100), `uf` (string, `^[A-Z]{2}$`).

| `event_type`                 | Campos do `payload`                                                                                      |
|------------------------------|-----------------------------------------------------------------------------------------------------------|
| `carga.recebida`             | `origem` (Localidade), `destino` (Localidade), `peso_kg` (number > 0, ≤ 30000), `descricao` (string ≤ 200), `centro_distribuicao` (string) |
| `carga.saiu_para_transporte` | `veiculo_id` (`^VEI-[0-9]{4}$`), `previsao_entrega` (date-time UTC)                                       |
| `carga.em_transito`          | `veiculo_id`, `localizacao` { `latitude` (−90..90), `longitude` (−180..180), `cidade`, `uf` }            |
| `carga.saiu_para_entrega`    | `veiculo_id`, `tentativa` (integer 1..3)                                                                   |
| `carga.entregue`             | `tentativa` (integer 1..3), `recebedor` (string ≤ 100, nome fictício)                                     |
| `carga.entrega_falhou`       | `tentativa` (integer 1..3), `motivo` (enum `DESTINATARIO_AUSENTE`, `ENDERECO_NAO_ENCONTRADO`, `RECUSADA`) |

## 4. Carga e máquina de estados (simulador)

O simulador mantém N cargas ativas; cada uma avança segundo a máquina abaixo. Quando uma carga
termina, outra é criada para manter N simultâneas.

```text
            ┌──────────────┐
  (nova) ──▶│   RECEBIDA   │
            └──────┬───────┘
                   ▼
            ┌──────────────┐
            │ EM_TRANSPORTE│
            └──────┬───────┘
                   ▼
            ┌──────────────┐  (0..k atualizações de posição)
            │  EM_TRANSITO │◀─┐
            └──────┬───────┴──┘
                   ▼
            ┌───────────────────┐
     ┌─────▶│ SAIU_PARA_ENTREGA │
     │      └──────┬────────────┘
     │             ├──────────────▶ ENTREGUE (terminal)
     │             ▼
     │      ┌───────────────┐
     └──────│ FALHA_ENTREGA │  tentativa < 3 → nova saída para entrega
            └───────────────┘  tentativa = 3 → terminal
```

Regras do simulador:
- `occurred_at` de cada evento de uma carga é estritamente crescente.
- `tentativa` começa em 1 e incrementa a cada `carga.saiu_para_entrega` após falha.
- Probabilidades padrão: falha na entrega 15%; número de `em_transito` entre 1 e 5.

## 5. Projeção da API de consulta (em memória)

### CargaView

| Campo                  | Tipo          | Origem                                                    |
|------------------------|---------------|-----------------------------------------------------------|
| `carga_id`             | string        | envelope                                                  |
| `status`               | StatusCarga   | `event_type` do evento com maior `occurred_at`            |
| `origem`, `destino`    | Localidade?   | payload de `carga.recebida` (nulo se expirado/ausente)    |
| `peso_kg`, `descricao` | number?, str? | payload de `carga.recebida`                               |
| `tentativas_entrega`   | integer       | maior `tentativa` observada (0 se nenhuma)                |
| `ultima_atualizacao`   | date-time     | maior `occurred_at`                                       |
| `total_eventos`        | integer       | eventos distintos no histórico                            |
| `correlation_id`       | string        | envelope                                                  |

### HistoricoCarga

Lista de `EventoCarga` da carga, ordenada por (`occurred_at`, `event_id`), sem duplicatas.

### Resumo

`total_cargas`, `total_eventos`, `cargas_por_status` (mapa StatusCarga → contagem),
`eventos_duplicados_descartados`, `eventos_enviados_dlq`, `atualizado_em`.

### Regras de aplicação de evento

1. Validar contra o contrato; se inválido → publicar no DLQ com motivo, contar, seguir adiante.
2. Se `event_id` já existe no histórico da carga → descartar e incrementar contador de duplicados.
3. Inserir no histórico mantendo a ordenação; recalcular `status` e `ultima_atualizacao`.
4. Evento fora de ordem (ex.: `entregue` sem `em_transito`) é aceito; o status reflete o evento
   mais recente por `occurred_at`.
5. **Expiração (FR-022a)**: evento com `occurred_at` anterior a `agora − janela de retenção`
   (padrão 15 min, mesmo valor do tópico) é ignorado ao ser consumido e removido do histórico na
   limpeza periódica (a cada 30 s). Após a remoção, `status`, `ultima_atualizacao`,
   `tentativas_entrega`, `total_eventos` e os dados de `carga.recebida` são recalculados com os
   eventos restantes; carga sem eventos é removida (consulta → 404). Eventos expirados não vão ao
   DLQ e não contam como duplicados.

## 6. Ingestão (conector) — visão da API de controle

| Campo                 | Tipo                                                     | Origem                          |
|-----------------------|----------------------------------------------------------|---------------------------------|
| `nome`                | string                                                   | config versionada               |
| `estado`              | enum `ATIVA`, `PAUSADA`, `COM_FALHA`, `INEXISTENTE`, `INICIANDO` | REST do Connect (mapeado) |
| `tarefas`             | lista { `id`, `estado`, `erro`? }                         | REST do Connect                 |
| `arquivos_pendentes`  | integer                                                  | contagem em `dados/eventos`     |
| `arquivos_em_backup` | integer                                                  | contagem em `dados/backup` |
| `arquivos_com_erro`   | integer                                                  | contagem em `dados/erros`       |
| `connect_disponivel`  | boolean                                                  | ping na REST do Connect         |

Mapeamento de estados do Connect: `RUNNING` (com todas as tarefas `RUNNING` **ou sem tarefas** —
o FilePulse só cria tarefas enquanto há arquivos a processar)→`ATIVA`, `PAUSED`/`STOPPED`→`PAUSADA`,
`FAILED` (conector ou qualquer tarefa)→`COM_FALHA`, `UNASSIGNED`/`RESTARTING`→`INICIANDO`,
404→`INEXISTENTE`. `ativar` não reaplica a configuração quando ela já é a versionada (um `PUT`
no Connect reinicia o conector mesmo com configuração idêntica); `retomar` só age se `PAUSADA`.

Transições permitidas via API:

| Ação       | De                               | Para        | Idempotência                          |
|------------|----------------------------------|-------------|---------------------------------------|
| `ativar`   | `INEXISTENTE`, qualquer          | `ATIVA`     | PUT de config; reaplicar não altera   |
| `pausar`   | `ATIVA`, `INICIANDO`, `PAUSADA`  | `PAUSADA`   | já pausada → 202 sem efeito           |
| `retomar`  | `PAUSADA`, `ATIVA`               | `ATIVA`     | já ativa → 202 sem efeito             |
| `reiniciar`| `ATIVA`, `COM_FALHA`, `PAUSADA`  | `INICIANDO` | sempre reinicia conector + tarefas    |
| `remover`  | qualquer                         | `INEXISTENTE` | inexistente → 204                   |

## 7. Tópicos

| Tópico                                  | Partições | RF | Retenção     | Chave      | Valor                |
|-----------------------------------------|-----------|----|--------------|------------|----------------------|
| `transportadora.carga.eventos.v1`       | 3         | 1  | 15 min       | `carga_id` | EventoCarga (JSON)   |
| `transportadora.carga.eventos-dlq.v1`   | 1         | 1  | 24 h         | chave original (se houver) | mensagem original |

Headers no tópico principal: `correlation_id`, `event_type`. Headers no DLQ: `erro_tipo`,
`erro_motivo`, `topico_origem`, `particao_origem`, `offset_origem`, `correlation_id` (se houver).
Detalhes: [contracts/topicos.md](./contracts/topicos.md).
