from __future__ import annotations

import json
import logging

import pytest
import structlog

from controle_ingestao.observabilidade import configurar_logs, correlation_id_var


def _linhas(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    return [json.loads(linha) for linha in capsys.readouterr().out.splitlines() if linha]


@pytest.mark.parametrize("logger", ["httpx", "aiokafka", "uvicorn.error", "uvicorn.access"])
def test_logs_da_stdlib_saem_em_json(capsys: pytest.CaptureFixture[str], logger: str) -> None:
    configurar_logs("INFO")
    logging.getLogger(logger).warning("mensagem %s", "formatada")
    (linha,) = _linhas(capsys)
    assert linha["event"] == "mensagem formatada"
    assert linha["level"] == "warning"
    assert linha["service"] == "controle-ingestao"
    assert linha["logger"] == logger
    assert str(linha["timestamp"]).endswith("Z")


def test_logs_structlog_e_correlation_id(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logs("INFO")
    token = correlation_id_var.set("corr-42")
    try:
        structlog.get_logger().info("evento", event_id="e-1")
        logging.getLogger("httpx").info("requisicao")
    finally:
        correlation_id_var.reset(token)
    linhas = _linhas(capsys)
    assert [linha["correlation_id"] for linha in linhas] == ["corr-42", "corr-42"]
    assert linhas[0]["event_id"] == "e-1"
    assert linhas[0]["service"] == "controle-ingestao"


def test_nivel_filtra_debug(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logs("INFO")
    structlog.get_logger().debug("oculto")
    logging.getLogger("aiokafka").debug("oculto")
    assert _linhas(capsys) == []


def test_excecao_serializada(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logs("INFO")
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("uvicorn.error").exception("falhou")
    (linha,) = _linhas(capsys)
    assert "ValueError: boom" in str(linha["exception"])
