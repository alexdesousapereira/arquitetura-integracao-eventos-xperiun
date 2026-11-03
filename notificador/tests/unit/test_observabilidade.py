from __future__ import annotations

import json
import logging

import pytest
import structlog

from notificador.observabilidade import configurar_logs


def test_logs_em_json_com_service(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logs("INFO")
    structlog.get_logger().info("mensagem_enviada", pedido_id="PED-0000E5E1")
    linha = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert linha["event"] == "mensagem_enviada"
    assert linha["service"] == "notificador"
    assert linha["level"] == "info"


def test_httpx_nao_registra_urls_com_o_token() -> None:
    configurar_logs("DEBUG")
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
