from __future__ import annotations

import pytest

from notificador.__main__ import criar_canal
from notificador.canais import CanalLog, CanalTelegram
from notificador.config import ConfigNotificador


def test_sem_token_roda_em_modo_demonstracao() -> None:
    config = ConfigNotificador()
    assert not config.telegram_configurado
    assert isinstance(criar_canal(config), CanalLog)


def test_token_sem_chat_continua_em_modo_demonstracao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    assert isinstance(criar_canal(ConfigNotificador()), CanalLog)


def test_token_e_chat_ativam_o_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
    config = ConfigNotificador()
    assert config.telegram_configurado
    assert isinstance(criar_canal(config), CanalTelegram)
    assert "123:abc" not in repr(config)
