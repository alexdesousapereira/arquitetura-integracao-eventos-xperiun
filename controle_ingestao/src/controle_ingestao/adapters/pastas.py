"""Contagem dos arquivos de evento nas pastas compartilhadas com o Kafka Connect."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Pastas:
    """Pastas de entrada, backup (ingeridos) e erros."""

    eventos: Path
    backup: Path
    erros: Path


def _contar(pasta: Path) -> int:
    # `os.scandir` usa o tipo devolvido pela listagem (sem um `stat` por arquivo): com dezenas de
    # milhares de arquivos em `dados/backup` num volume montado, `glob` + `is_file` levava ~10 s.
    try:
        with os.scandir(pasta) as entradas:
            return sum(
                1
                for e in entradas
                if e.name.endswith(".json") and not e.name.startswith(".") and e.is_file()
            )
    except FileNotFoundError:
        return 0


async def contar_arquivos(pasta: Path) -> int:
    """Conta os `*.json` não ocultos da pasta sem bloquear o event loop (0 se não existir)."""
    return await asyncio.to_thread(_contar, pasta)
