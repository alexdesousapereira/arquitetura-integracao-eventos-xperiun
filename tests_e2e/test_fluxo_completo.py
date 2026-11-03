"""US4 ponta a ponta: arquivo → Kafka Connect → tópico → API de consulta."""

from __future__ import annotations

import subprocess

import httpx
import pytest

from tests_e2e.conftest import RAIZ, GravadorEventos, aguardar

pytestmark = pytest.mark.e2e


def _historico(consulta: httpx.Client, pedido_id: str) -> list[str] | None:
    resposta = consulta.get(f"/api/v1/pedidos/{pedido_id}/eventos")
    if resposta.status_code != httpx.codes.OK:
        return None
    return [e["event_id"] for e in resposta.json()["eventos"]]


def test_eventos_gerados_aparecem_na_api(
    ingestao_ativa: httpx.Client, consulta: httpx.Client, gravador: GravadorEventos
) -> None:
    eventos = gravador.gerar(10)
    por_pedido: dict[str, list[str]] = {}
    for evento in eventos:
        por_pedido.setdefault(evento.pedido_id, []).append(str(evento.event_id))

    def todas_visiveis() -> bool:
        return all(
            set(ids) <= set(_historico(consulta, pedido_id) or [])
            for pedido_id, ids in por_pedido.items()
        )

    aguardar(todas_visiveis, timeout=60, intervalo=2)
    for pedido_id, ids in por_pedido.items():
        historico = _historico(consulta, pedido_id)
        assert historico is not None
        assert [i for i in historico if i in ids] == ids  # ordem cronológica preservada

    total_antes = consulta.get("/api/v1/resumo").json()["total_eventos"]
    subprocess.run(
        ["docker", "compose", "restart", "api-consulta"],
        cwd=RAIZ,
        check=True,
        capture_output=True,
    )

    def pronta() -> bool:
        try:
            return consulta.get("/health/ready").status_code == httpx.codes.OK
        except httpx.HTTPError:
            return False

    aguardar(pronta, timeout=90, intervalo=2)
    assert consulta.get("/api/v1/resumo").json()["total_eventos"] >= total_antes - 5
    assert todas_visiveis()
