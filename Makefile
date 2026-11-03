# Pipeline de Eventos da Loja — comandos de operação e desenvolvimento.
# Uso: `make help`

-include .env
export

UV ?= .venv/bin/uv
COMPOSE ?= docker compose
APP_UID ?= 1000
APP_GID ?= 1000
CONTROLE_PORTA ?= 8001
CONSULTA_PORTA ?= 8002
TOPICO_EVENTOS ?= loja.pedido.eventos.v1
TOPICO_DLQ ?= loja.pedido.eventos-dlq.v1
NOTIFICADOR_GRUPO ?= notificador
INSTANCIAS ?= 2
N ?= 10
ARGS ?=
TRIVY_IMAGE ?= aquasec/trivy:0.76.1
IMAGENS_PROPRIAS ?= pipeline-eventos/simulador:local pipeline-eventos/controle-ingestao:local \
	pipeline-eventos/api-consulta:local pipeline-eventos/notificador:local
# Imagem derivada da Confluent (RHEL + jars do Kafka/FilePulse): achados só são reportados, pois a
# correção depende do fornecedor (constituição, princípio VII: as imagens são varridas antes do release).
IMAGENS_TERCEIROS ?= pipeline-eventos/connect:local
TRIVY = docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
	-v pipeline-eventos-trivy-cache:/root/.cache/ $(TRIVY_IMAGE) image --quiet \
	--severity HIGH,CRITICAL --ignore-unfixed

KAFKA_EXEC = $(COMPOSE) exec -T kafka
BOOTSTRAP = --bootstrap-server kafka:29092
CONTROLE_URL = http://localhost:$(CONTROLE_PORTA)/api/v1/ingestao
CONSULTA_URL = http://localhost:$(CONSULTA_PORTA)/api/v1
AUTH = -H "X-API-Key: $(CONTROLE_API_KEY)"

.DEFAULT_GOAL := help
.PHONY: help install lint format test test-integracao test-e2e test-e2e-simulacao ci build scan \
	up down clean logs status pastas topicos topicos-offsets consumir dlq \
	publicar-evento-teste publicar-evento-invalido simular simular-aula validar-eventos \
	ingestao-status ingestao-ativar ingestao-pausar ingestao-retomar ingestao-reiniciar \
	ingestao-remover consulta-resumo consulta-pedidos consulta-consumo \
	notificador notificador-logs notificador-parar notificador-escalar notificador-grupo

help: ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- desenvolvimento
install: ## Instala dependências no .venv (uv sync)
	$(UV) sync

lint: ## ruff (lint + format check), mypy --strict e pip-audit
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy contratos/src simulador/src controle_ingestao/src api_consulta/src notificador/src
	$(UV) run pip-audit --skip-editable --progress-spinner off

format: ## Formata o código com ruff
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test: ## Testes unitários e de contrato com cobertura (>= 80%)
	$(UV) run pytest --cov --cov-report=term-missing --cov-fail-under=80

# Socket do Docker visto de DENTRO da VM/daemon (necessário no Colima/Docker Desktop para o Ryuk).
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE ?= /var/run/docker.sock

test-integracao: ## Testes de integração (testcontainers, requer Docker)
	$(UV) run pytest -m integration api_consulta/tests/integration

test-e2e: ## Testes ponta a ponta (requer `make up`)
	$(UV) run pytest -m e2e tests_e2e

test-e2e-simulacao: ## Só a simulação ponta a ponta (10 eventos, sem perda)
	$(UV) run pytest -m e2e tests_e2e/test_simulacao.py

ci: lint test build scan test-integracao ## Todos os gates de merge da constituição

build: ## Constrói as imagens próprias
	$(COMPOSE) --profile simulacao --profile notificacao build

scan: ## Trivy: falha em HIGH/CRITICAL corrigíveis nas imagens próprias; reporta a do Connect
	@for img in $(IMAGENS_PROPRIAS); do \
		echo "== $$img"; $(TRIVY) --exit-code 1 $$img || exit 1; \
	done
	@for img in $(IMAGENS_TERCEIROS); do \
		echo "== $$img (somente relatório)"; $(TRIVY) --exit-code 0 --format table $$img | grep -E "^Total|\(redhat|^Java|^Python" ; \
	done

# ---------------------------------------------------------------- ambiente
pastas:
	@mkdir -p dados/eventos dados/backup dados/erros
	@chown $(APP_UID):$(APP_GID) dados/eventos dados/backup dados/erros 2>/dev/null || true
	@chmod 775 dados/eventos dados/backup dados/erros

up: pastas ## Sobe kafka, connect e as APIs (aguarda ficarem saudáveis)
	$(COMPOSE) up -d --build --wait
	@echo ""
	@echo "Ambiente no ar. Ative a ingestão com: make ingestao-ativar"

down: ## Derruba o ambiente
	$(COMPOSE) --profile simulacao --profile notificacao down

clean: ## Derruba o ambiente, remove volumes e apaga dados/ (inclui o backup)
	$(COMPOSE) --profile simulacao --profile notificacao down -v
	@find dados/eventos dados/backup dados/erros -type f ! -name .gitkeep -delete 2>/dev/null || true

logs: ## Acompanha os logs (S=serviço opcional)
	$(COMPOSE) logs -f $(S)

status: ## Estado dos containers
	$(COMPOSE) ps -a

# ---------------------------------------------------------------- tópicos
topicos: ## Descreve os tópicos de eventos e DLQ
	$(KAFKA_EXEC) kafka-topics $(BOOTSTRAP) --describe --topic $(TOPICO_EVENTOS)
	$(KAFKA_EXEC) kafka-configs $(BOOTSTRAP) --describe --entity-type topics --entity-name $(TOPICO_EVENTOS)
	$(KAFKA_EXEC) kafka-topics $(BOOTSTRAP) --describe --topic $(TOPICO_DLQ)

topicos-offsets: ## Offsets inicial (log start) e final por partição
	@echo "log start offset:"; $(KAFKA_EXEC) kafka-get-offsets $(BOOTSTRAP) --topic $(TOPICO_EVENTOS) --time -2
	@echo "end offset:";       $(KAFKA_EXEC) kafka-get-offsets $(BOOTSTRAP) --topic $(TOPICO_EVENTOS) --time -1

consumir: ## Lê N mensagens do tópico de eventos (com chave e headers)
	$(KAFKA_EXEC) kafka-console-consumer $(BOOTSTRAP) --topic $(TOPICO_EVENTOS) --from-beginning \
		--max-messages $(N) --timeout-ms 10000 --property print.key=true \
		--property print.headers=true --property print.timestamp=true

dlq: ## Lê N mensagens do DLQ
	$(KAFKA_EXEC) kafka-console-consumer $(BOOTSTRAP) --topic $(TOPICO_DLQ) --from-beginning \
		--max-messages $(N) --timeout-ms 10000 --property print.key=true --property print.headers=true

publicar-evento-teste: ## Publica um evento válido de exemplo direto no tópico
	@$(UV) run python -m contratos.exemplo | \
		$(KAFKA_EXEC) kafka-console-producer $(BOOTSTRAP) --topic $(TOPICO_EVENTOS) \
		--property parse.key=true --property key.separator='|'

publicar-evento-invalido: ## Publica JSON válido fora do contrato (sem pedido_id) → DLQ
	@echo 'PED-00000000|{"event_id":"00000000-0000-4000-8000-000000000000","event_type":"pedido.criado"}' | \
		$(KAFKA_EXEC) kafka-console-producer $(BOOTSTRAP) --topic $(TOPICO_EVENTOS) \
		--property parse.key=true --property key.separator='|'

# ---------------------------------------------------------------- simulador
simular: pastas ## Executa o simulador (padrão: 10 eventos; ARGS="--continuo" para rodar sem parar)
	$(COMPOSE) --profile simulacao run --rm --service-ports simulador $(ARGS)

ATRASO ?= 10
simular-aula: pastas ## Um pedido por vez, ATRASO=10 s entre cada mudança de status (demo no Telegram)
	$(COMPOSE) --profile simulacao run --rm --service-ports simulador \
		--pedidos 1 --atraso-status-s $(ATRASO) --continuo $(ARGS)

validar-eventos: ## Valida os JSON em dados/eventos e dados/backup contra o contrato
	$(UV) run python -m contratos.validar dados/eventos dados/backup

# ---------------------------------------------------------------- ingestão (API de controle)
ingestao-status: ## Status da ingestão
	@curl -s $(CONTROLE_URL) | jq .

ingestao-ativar: ## Cria/ativa a ingestão com a configuração versionada
	@curl -s -X PUT $(AUTH) $(CONTROLE_URL) | jq .

ingestao-pausar: ## Pausa a ingestão
	@curl -s -X POST $(AUTH) $(CONTROLE_URL)/pausar | jq .

ingestao-retomar: ## Retoma a ingestão
	@curl -s -X POST $(AUTH) $(CONTROLE_URL)/retomar | jq .

ingestao-reiniciar: ## Reinicia o conector e suas tarefas
	@curl -s -X POST $(AUTH) $(CONTROLE_URL)/reiniciar | jq .

ingestao-remover: ## Remove a ingestão
	@curl -s -o /dev/null -w "%{http_code}\n" -X DELETE $(AUTH) $(CONTROLE_URL)

# ---------------------------------------------------------------- consulta
consulta-resumo: ## Resumo dos pedidos
	@curl -s $(CONSULTA_URL)/resumo | jq .

consulta-pedidos: ## Lista pedidos (STATUS=ENVIADO opcional)
	@curl -s "$(CONSULTA_URL)/pedidos?size=20$(if $(STATUS),&status=$(STATUS),)" | jq .

consulta-consumo: ## Status do consumo (lag)
	@curl -s $(CONSULTA_URL)/consumo/status | jq .

# ---------------------------------------------------------------- notificador (bot do Telegram)
notificador: ## Liga o bot (sem TELEGRAM_BOT_TOKEN/CHAT_ID no .env: modo demonstração, só log)
	$(COMPOSE) --profile notificacao up -d --build notificador

notificador-logs: ## Acompanha o bot (mensagens enviadas, partições atribuídas)
	$(COMPOSE) --profile notificacao logs -f notificador

notificador-parar: ## Para o bot; o grupo guarda o offset e, ao religar, ele envia o que perdeu
	$(COMPOSE) --profile notificacao stop notificador

notificador-escalar: ## Roda INSTANCIAS=2 bots no mesmo grupo: as partições são divididas
	$(COMPOSE) --profile notificacao up -d --scale notificador=$(INSTANCIAS) notificador

notificador-grupo: ## Offset commitado e lag do consumer group do bot, por partição
	$(KAFKA_EXEC) kafka-consumer-groups $(BOOTSTRAP) --describe --group $(NOTIFICADOR_GRUPO)
