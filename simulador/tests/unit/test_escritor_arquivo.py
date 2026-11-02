from __future__ import annotations

import json
import random
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contratos import parse_evento
from simulador.adapters.escritor_arquivo import ErroGravacaoEvento, EscritorArquivo
from simulador.dominio.carga import CargaSimulada
from simulador.dominio.gerador import Gerador

NOME = re.compile(r"^\d{8}T\d{12}Z_CRG-[0-9A-F]{8}_[0-9a-f-]{36}\.json$")


def _evento():  # type: ignore[no-untyped-def]
    carga = CargaSimulada.nova(Gerador(random.Random(1)), prob_falha=0.0)
    return carga.proximo_evento(datetime(2026, 11, 2, 12, 0, 0, 123456, tzinfo=UTC))


def test_grava_arquivo_com_nome_padronizado(tmp_path: Path) -> None:
    evento = _evento()
    caminho = EscritorArquivo(tmp_path).gravar(evento)
    assert NOME.match(caminho.name), caminho.name
    assert caminho.name.startswith("20261102T120000123456Z_")
    assert str(evento.carga_id) in caminho.name
    assert str(evento.event_id) in caminho.name


def test_conteudo_e_um_unico_objeto_json_valido(tmp_path: Path) -> None:
    evento = _evento()
    caminho = EscritorArquivo(tmp_path).gravar(evento)
    conteudo = caminho.read_text(encoding="utf-8")
    assert isinstance(json.loads(conteudo), dict)
    assert parse_evento(conteudo) == evento


def test_nao_deixa_arquivos_temporarios(tmp_path: Path) -> None:
    escritor = EscritorArquivo(tmp_path)
    for _ in range(5):
        escritor.gravar(_evento())
    assert [p for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_arquivo_temporario_e_oculto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vistos: list[str] = []
    original = __import__("os").replace

    def espiar(src: str, dst: str) -> None:
        vistos.append(Path(src).name)
        original(src, dst)

    monkeypatch.setattr("simulador.adapters.escritor_arquivo.os.replace", espiar)
    EscritorArquivo(tmp_path).gravar(_evento())
    assert vistos[0].startswith(".")
    assert vistos[0].endswith(".json.tmp")


def test_cria_pasta_de_saida(tmp_path: Path) -> None:
    destino = tmp_path / "a" / "b"
    EscritorArquivo(destino).gravar(_evento())
    assert len(list(destino.glob("*.json"))) == 1


def test_erro_de_permissao_gera_excecao_especifica(tmp_path: Path) -> None:
    somente_leitura = tmp_path / "ro"
    somente_leitura.mkdir()
    somente_leitura.chmod(0o500)
    try:
        with pytest.raises(ErroGravacaoEvento):
            EscritorArquivo(somente_leitura).gravar(_evento())
        assert list(somente_leitura.iterdir()) == []
    finally:
        somente_leitura.chmod(0o700)
