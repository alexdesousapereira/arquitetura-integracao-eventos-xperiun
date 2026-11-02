from __future__ import annotations

import json
import random
import threading
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from contratos import TipoEvento, carregar_schema
from simulador.adapters.escritor_arquivo import EscritorArquivo
from simulador.config import ConfigSimulador
from simulador.dominio.gerador import Gerador
from simulador.servico import Simulacao


def test_eventos_gerados_validam_contra_json_schema(tmp_path: Path) -> None:
    config = ConfigSimulador(cargas=30, max_eventos=600, intervalo_ms=10, seed=123, prob_falha=0.4)
    Simulacao(
        config,
        EscritorArquivo(tmp_path),
        gerador=Gerador(random.Random(123)),
        dormir=lambda _: None,
        parar=threading.Event(),
    ).executar()

    validador = Draft202012Validator(carregar_schema(), format_checker=FormatChecker())
    arquivos = sorted(tmp_path.glob("*.json"))
    assert len(arquivos) == 600
    tipos = set()
    for arquivo in arquivos:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        validador.validate(dados)
        tipos.add(dados["event_type"])
    assert tipos == {t.value for t in TipoEvento}
