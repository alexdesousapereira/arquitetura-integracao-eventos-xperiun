"""Edge case da spec: barramento indisponível com a ingestão ativa.

A ingestão deve reportar a falha e, quando o broker voltar, retomar sem perder eventos.
"""

from __future__ import annotations

import subprocess

import httpx
import pytest

from tests_e2e.conftest import RAIZ, GravadorEventos, aguardar

pytestmark = pytest.mark.e2e


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=RAIZ, check=True, capture_output=True)


def _visivel(consulta: httpx.Client, event_id: str, pedido_id: str) -> bool:
    try:
        resposta = consulta.get(f"/api/v1/pedidos/{pedido_id}/eventos")
    except httpx.HTTPError:
        return False
    if resposta.status_code != httpx.codes.OK:
        return False
    return event_id in {e["event_id"] for e in resposta.json()["eventos"]}


def test_queda_do_broker_e_retomada_sem_perda(
    ingestao_ativa: httpx.Client, consulta: httpx.Client, gravador: GravadorEventos
) -> None:
    _compose("stop", "kafka")
    try:
        eventos = gravador.gerar(10)

        def falha_reportada() -> bool:
            pronto = ingestao_ativa.get("/health/ready")
            return (
                pronto.status_code == httpx.codes.SERVICE_UNAVAILABLE
                and pronto.json()["dependencias"]["kafka"] == "indisponivel"
            )

        aguardar(falha_reportada, timeout=30)
    finally:
        _compose("start", "kafka")

    aguardar(lambda: ingestao_ativa.get("/health/ready").status_code == httpx.codes.OK, timeout=120)
    aguardar(
        lambda: all(_visivel(consulta, str(e.event_id), e.pedido_id) for e in eventos),
        timeout=180,
        intervalo=3,
    )
    estado = aguardar(
        lambda: (e := ingestao_ativa.get("/api/v1/ingestao").json()["estado"]) == "ATIVA" and e,
        timeout=60,
    )
    assert estado == "ATIVA"
