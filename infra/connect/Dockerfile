# syntax=docker/dockerfile:1
FROM confluentinc/cp-kafka-connect:7.9.10

# Kafka Connect FilePulse (research.md, R1): lê arquivos de uma pasta, faz o parse do JSON e
# permite definir a chave da mensagem a partir de um campo (pedido_id). Não está no Confluent Hub;
# o zip oficial é baixado do GitHub e validado pelo SHA-256 publicado na release.
ARG FILEPULSE_VERSION=2.18.0
ARG FILEPULSE_SHA256=34caa96f5dac797be69cb529c578b767ad123c357e794dc5ef582aa008e98930
RUN curl -fsSL -o /tmp/filepulse.zip \
      "https://github.com/streamthoughts/kafka-connect-file-pulse/releases/download/v${FILEPULSE_VERSION}/streamthoughts-kafka-connect-file-pulse-${FILEPULSE_VERSION}.zip" \
    && echo "${FILEPULSE_SHA256}  /tmp/filepulse.zip" | sha256sum -c - \
    && confluent-hub install --no-prompt /tmp/filepulse.zip \
    && rm /tmp/filepulse.zip
# Mantém o usuário não-root da imagem base (appuser, UID 1000).
