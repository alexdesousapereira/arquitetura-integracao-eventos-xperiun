"""CLI do simulador: `python -m simulador [opções]` (contracts/simulador-cli.md)."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path
from types import FrameType

import structlog
from pydantic import ValidationError

from simulador.adapters.escritor_arquivo import ErroGravacaoEvento, EscritorArquivo
from simulador.config import ConfigSimulador
from simulador.observabilidade import configurar_logs, iniciar_servidor_metricas
from simulador.servico import Simulacao

SAIDA_OK, SAIDA_IO, SAIDA_ARGS = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simulador", description="Gera eventos de pedidos como arquivos JSON."
    )
    p.add_argument("--pedidos", type=int, help="pedidos simultâneos")
    p.add_argument("--intervalo-ms", type=int, help="intervalo entre ciclos")
    p.add_argument(
        "--atraso-status-s",
        type=float,
        help="tempo mínimo que cada pedido fica em um status antes de avançar (0 = sem espera)",
    )
    p.add_argument("--duracao-s", type=int, help="encerra após S segundos (0 = sem limite)")
    p.add_argument("--max-eventos", type=int, help="encerra após N eventos (padrão 10)")
    p.add_argument(
        "--continuo",
        action="store_true",
        default=None,
        help="roda até ser interrompido, ignorando --max-eventos e --duracao-s",
    )
    p.add_argument("--saida", type=Path, help="pasta de destino dos arquivos JSON")
    p.add_argument("--seed", type=int, help="semente para execução reprodutível")
    p.add_argument("--prob-falha", type=float, help="probabilidade de recusa do pagamento")
    p.add_argument("--metrics-port", type=int, help="porta HTTP de /metrics (0 = desligado)")
    return p


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI; retorna o código de saída."""
    args = _parser().parse_args(argv)
    sobreposicoes = {k: v for k, v in vars(args).items() if v is not None}
    try:
        config = ConfigSimulador(**sobreposicoes)
    except ValidationError as exc:
        sys.stderr.write(f"argumentos inválidos:\n{exc}\n")
        return SAIDA_ARGS

    configurar_logs(config.log_level)
    log = structlog.get_logger()
    parar = threading.Event()

    def _sinal(signum: int, _frame: FrameType | None) -> None:
        log.info("parada_solicitada", sinal=signal.Signals(signum).name)
        parar.set()

    signal.signal(signal.SIGINT, _sinal)
    signal.signal(signal.SIGTERM, _sinal)
    iniciar_servidor_metricas(config.metrics_port)

    try:
        Simulacao(config, EscritorArquivo(config.saida), parar=parar).executar()
    except ErroGravacaoEvento as exc:
        log.error("erro_gravacao", erro=str(exc))
        return SAIDA_IO
    return SAIDA_OK


if __name__ == "__main__":
    sys.exit(main())
