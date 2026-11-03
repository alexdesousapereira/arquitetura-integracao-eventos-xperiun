"""Fixtures dos testes ponta a ponta (requerem o ambiente no ar: `make up`)."""

from __future__ import annotations

import json
import os
import random
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from contratos import EventoPedido
from simulador.adapters.escritor_arquivo import EscritorArquivo
from simulador.config import ConfigSimulador
from simulador.dominio.gerador import Gerador
from simulador.servico import Simulacao

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "dados"


def _env() -> dict[str, str]:
    valores: dict[str, str] = {}
    arquivo = RAIZ / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text().splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                chave, _, valor = linha.partition("=")
                valores[chave.strip()] = valor.strip()
    return {**valores, **os.environ}


ENV = _env()
URL_CONTROLE = f"http://localhost:{ENV.get('CONTROLE_PORTA', '8001')}"
URL_CONSULTA = f"http://localhost:{ENV.get('CONSULTA_PORTA', '8002')}"
TOPICO = ENV.get("TOPICO_EVENTOS", "loja.pedido.eventos.v1")


def aguardar(condicao: Callable[[], Any], timeout: float, intervalo: float = 1.0) -> Any:
    """Repete `condicao` até retornar valor verdadeiro ou estourar o tempo."""
    limite = time.monotonic() + timeout
    while True:
        resultado = condicao()
        if resultado:
            return resultado
        if time.monotonic() > limite:
            raise AssertionError(f"condição não atingida em {timeout}s")
        time.sleep(intervalo)


@pytest.fixture(scope="session", autouse=True)
def ambiente_no_ar() -> None:
    """Pula os testes e2e se as APIs não estiverem prontas."""
    for url in (URL_CONTROLE, URL_CONSULTA):
        try:
            pronta = httpx.get(f"{url}/health/ready", timeout=3).status_code == httpx.codes.OK
        except httpx.HTTPError:
            pronta = False
        if not pronta:
            pytest.skip(f"ambiente fora do ar ({url}); rode `make up`")


@pytest.fixture(scope="session")
def controle() -> Iterator[httpx.Client]:
    headers = {"X-API-Key": ENV.get("CONTROLE_API_KEY", "")}
    with httpx.Client(base_url=URL_CONTROLE, headers=headers, timeout=10) as cliente:
        yield cliente


@pytest.fixture(scope="session")
def consulta() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=URL_CONSULTA, timeout=10) as cliente:
        yield cliente


@pytest.fixture
def ingestao_ativa(controle: httpx.Client) -> httpx.Client:
    """Garante a ingestão criada e ativa."""
    controle.put("/api/v1/ingestao").raise_for_status()
    controle.post("/api/v1/ingestao/retomar").raise_for_status()
    aguardar(lambda: controle.get("/api/v1/ingestao").json()["estado"] == "ATIVA", 30)
    return controle


class GravadorEventos:
    """Gera eventos com o simulador diretamente em `dados/eventos`."""

    def __init__(self) -> None:
        self.eventos: list[EventoPedido] = []

    def gravar(self, evento: EventoPedido) -> Path:
        self.eventos.append(evento)
        return EscritorArquivo(DADOS / "eventos").gravar(evento)

    def gerar(
        self, quantidade: int = 10, pedidos: int = 3, seed: int | None = None
    ) -> list[EventoPedido]:
        inicio = len(self.eventos)
        config = ConfigSimulador(pedidos=pedidos, max_eventos=quantidade, intervalo_ms=10)
        Simulacao(
            config,
            self,
            gerador=Gerador(random.Random(seed)),
            dormir=lambda _: None,
            parar=threading.Event(),
        ).executar()
        return self.eventos[inicio:]


@pytest.fixture
def gravador() -> GravadorEventos:
    return GravadorEventos()


def arquivos(pasta: str) -> set[str]:
    """Nomes dos `*.json` não ocultos em `dados/<pasta>`."""
    return {p.name for p in (DADOS / pasta).glob("*.json") if not p.name.startswith(".")}


def kafka(*args: str) -> str:
    """Executa um utilitário do Kafka dentro do container do broker."""
    resultado = subprocess.run(
        ["docker", "compose", "exec", "-T", "kafka", *args, "--bootstrap-server", "kafka:29092"],
        cwd=RAIZ,
        check=True,
        capture_output=True,
        text=True,
    )
    return resultado.stdout


def end_offsets() -> int:
    """Soma dos offsets finais das partições do tópico de eventos."""
    saida = kafka("kafka-get-offsets", "--topic", TOPICO, "--time", "-1")
    return sum(int(linha.rsplit(":", 1)[1]) for linha in saida.split() if linha.count(":") == 2)


def consumir(n: int) -> list[dict[str, Any]]:
    """Lê as últimas mensagens do tópico com chave e headers."""
    saida = kafka(
        "kafka-console-consumer",
        "--topic",
        TOPICO,
        "--from-beginning",
        "--max-messages",
        str(n),
        "--timeout-ms",
        "10000",
        "--property",
        "print.key=true",
        "--property",
        "print.headers=true",
    )
    mensagens = []
    for linha in saida.splitlines():
        headers, chave, valor = linha.split("\t", 2)
        mensagens.append(
            {
                "headers": dict(h.split(":", 1) for h in headers.split(",") if ":" in h),
                "key": chave,
                "value": json.loads(valor),
            }
        )
    return mensagens
