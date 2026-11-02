from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola os testes das variáveis `SIMULADOR_*` exportadas pelo Makefile a partir do `.env`."""
    for nome in list(os.environ):
        if nome.startswith("SIMULADOR_"):
            monkeypatch.delenv(nome)
