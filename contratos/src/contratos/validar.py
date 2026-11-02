"""Valida arquivos JSON de eventos contra o contrato: `python -m contratos.validar <pasta>...`."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

from contratos.evento import parse_evento


def validar_pastas(pastas: list[Path]) -> tuple[int, list[tuple[Path, str]]]:
    """Valida todos os `*.json` não ocultos das pastas; retorna (válidos, inválidos com motivo)."""
    validos = 0
    invalidos: list[tuple[Path, str]] = []
    for pasta in pastas:
        for arquivo in sorted(pasta.glob("*.json")):
            if arquivo.name.startswith("."):
                continue
            try:
                parse_evento(arquivo.read_bytes())
            except ValidationError as exc:
                invalidos.append((arquivo, exc.errors()[0]["msg"]))
            else:
                validos += 1
    return validos, invalidos


def main(argv: list[str] | None = None) -> int:
    """Imprime o total de arquivos válidos e inválidos; código 1 se houver inválidos."""
    pastas = [Path(p) for p in (argv if argv is not None else sys.argv[1:])] or [
        Path("dados/eventos")
    ]
    validos, invalidos = validar_pastas(pastas)
    for arquivo, motivo in invalidos:
        sys.stdout.write(f"INVÁLIDO {arquivo}: {motivo}\n")
    sys.stdout.write(f"válidos={validos} inválidos={len(invalidos)}\n")
    return 1 if invalidos else 0


if __name__ == "__main__":
    sys.exit(main())
