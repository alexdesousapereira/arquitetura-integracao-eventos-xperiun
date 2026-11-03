from __future__ import annotations

from pathlib import Path

import pytest

from simulador.__main__ import main


def test_cli_gera_eventos_e_sai_com_zero(tmp_path: Path) -> None:
    codigo = main(
        ["--saida", str(tmp_path), "--max-eventos", "15", "--intervalo-ms", "10", "--seed", "1"]
    )
    assert codigo == 0
    assert len(list(tmp_path.glob("*.json"))) == 15


def test_cli_padrao_gera_dez_eventos(tmp_path: Path) -> None:
    assert main(["--saida", str(tmp_path), "--intervalo-ms", "10", "--seed", "1"]) == 0
    assert len(list(tmp_path.glob("*.json"))) == 10


def test_cli_max_eventos_zero_e_invalido(tmp_path: Path) -> None:
    assert main(["--saida", str(tmp_path), "--max-eventos", "0"]) == 2


def test_cli_argumento_invalido_sai_com_dois(tmp_path: Path) -> None:
    assert main(["--saida", str(tmp_path), "--pedidos", "0"]) == 2


def test_cli_tipo_invalido_sai_com_dois() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--pedidos", "muitas"])
    assert exc.value.code == 2


def test_cli_erro_de_io_sai_com_um(tmp_path: Path) -> None:
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        assert main(["--saida", str(ro), "--max-eventos", "1", "--intervalo-ms", "10"]) == 1
    finally:
        ro.chmod(0o700)
