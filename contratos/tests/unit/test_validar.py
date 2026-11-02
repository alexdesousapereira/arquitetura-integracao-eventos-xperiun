from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contratos.exemplo import evento_exemplo
from contratos.exemplo import main as main_exemplo
from contratos.validar import main, validar_pastas


def test_valida_pasta_mista(tmp_path: Path, evento_valido: dict[str, Any]) -> None:
    (tmp_path / "ok.json").write_text(json.dumps(evento_valido))
    (tmp_path / "ruim.json").write_text("{ quebrado")
    (tmp_path / ".oculto.json.tmp").write_text("x")
    validos, invalidos = validar_pastas([tmp_path])
    assert validos == 1
    assert [p.name for p, _ in invalidos] == ["ruim.json"]
    assert main([str(tmp_path)]) == 1


def test_pasta_so_com_validos_retorna_zero(tmp_path: Path, evento_valido: dict[str, Any]) -> None:
    (tmp_path / "ok.json").write_text(json.dumps(evento_valido))
    assert main([str(tmp_path)]) == 0


def test_exemplo_e_valido(capsys: Any) -> None:
    assert evento_exemplo().carga_id == "CRG-0000E5E1"
    assert main_exemplo() == 0
    chave, valor = capsys.readouterr().out.strip().split("|", 1)
    assert chave == "CRG-0000E5E1"
    assert json.loads(valor)["event_type"] == "carga.recebida"
