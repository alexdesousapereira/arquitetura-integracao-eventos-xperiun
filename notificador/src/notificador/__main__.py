"""Ponto de entrada: `python -m notificador`."""

from __future__ import annotations

import asyncio
import signal
import sys

import structlog

from notificador.canais import Canal, CanalLog, CanalTelegram
from notificador.config import ConfigNotificador
from notificador.consumidor import ConsumidorNotificacoes
from notificador.observabilidade import configurar_logs, iniciar_servidor_metricas
from notificador.servico import Notificador


def criar_canal(config: ConfigNotificador) -> Canal:
    """Telegram quando token e chat estão configurados; senão, modo demonstração (log)."""
    if config.telegram_configurado:
        return CanalTelegram(
            config.telegram_bot_token.get_secret_value(),
            config.telegram_chat_id,
            api_url=config.telegram_api_url,
        )
    return CanalLog()


async def _executar(config: ConfigNotificador) -> None:
    log = structlog.get_logger()
    canal = criar_canal(config)
    if canal.nome == "log":
        log.warning("modo_demonstracao", detalhe="TELEGRAM_BOT_TOKEN/CHAT_ID vazios: só log")
    tarefa = asyncio.create_task(ConsumidorNotificacoes(config, Notificador(canal)).executar())
    loop = asyncio.get_running_loop()
    for sinal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sinal, tarefa.cancel)
    try:
        await tarefa
    except asyncio.CancelledError:
        log.info("notificador_encerrado")
    finally:
        await canal.fechar()


def main() -> int:
    """Configura logs e métricas e roda até receber SIGINT/SIGTERM."""
    config = ConfigNotificador()
    configurar_logs(config.log_level)
    iniciar_servidor_metricas(config.notificador_metrics_port)
    asyncio.run(_executar(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
