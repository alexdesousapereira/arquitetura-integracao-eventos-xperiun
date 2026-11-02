#!/usr/bin/env bash
# Cria (ou ajusta) os tópicos da transportadora de forma idempotente.
#
# Por que `segment.ms`: o Kafka só apaga segmentos de log FECHADOS. Com o padrão (7 dias) o
# segmento ativo nunca fecha e a retenção de 15 min não seria observada. Segmentos de 1 min +
# `log.retention.check.interval.ms=60000` no broker fazem os eventos expirarem entre 15 e ~17 min
# (research.md, R5). `kafka-configs --alter` reaplica os valores a cada `make up`, então mudar
# TOPICO_RETENCAO_MS no .env tem efeito sem recriar o tópico.
set -euo pipefail

BOOTSTRAP="${BOOTSTRAP:-kafka:29092}"
: "${TOPICO_EVENTOS:?}" "${TOPICO_DLQ:?}"
TOPICO_PARTICOES="${TOPICO_PARTICOES:-3}"
TOPICO_RETENCAO_MS="${TOPICO_RETENCAO_MS:-900000}"
TOPICO_SEGMENT_MS="${TOPICO_SEGMENT_MS:-60000}"
DLQ_RETENCAO_MS="${DLQ_RETENCAO_MS:-86400000}"

criar() {
  local topico="$1" particoes="$2" configs="$3"
  kafka-topics --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
    --topic "$topico" --partitions "$particoes" --replication-factor 1 \
    $(for c in ${configs//,/ }; do printf -- '--config %s ' "$c"; done)
  kafka-configs --bootstrap-server "$BOOTSTRAP" --alter --entity-type topics \
    --entity-name "$topico" --add-config "$configs"
}

criar "$TOPICO_EVENTOS" "$TOPICO_PARTICOES" \
  "cleanup.policy=delete,retention.ms=${TOPICO_RETENCAO_MS},segment.ms=${TOPICO_SEGMENT_MS}"
criar "$TOPICO_DLQ" 1 "cleanup.policy=delete,retention.ms=${DLQ_RETENCAO_MS}"

kafka-topics --bootstrap-server "$BOOTSTRAP" --describe --topic "$TOPICO_EVENTOS"
kafka-topics --bootstrap-server "$BOOTSTRAP" --describe --topic "$TOPICO_DLQ"
