"""SC-002/SC-003/SC-004 com volume de simulação: todos os eventos chegam à API, sem perda.

O objetivo é validar a arquitetura ponta a ponta, não desempenho (spec, Clarifications).
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

import httpx
import pytest

from tests_e2e.conftest import GravadorEventos, aguardar

pytestmark = pytest.mark.e2e

PEDIDOS = 3
EVENTOS = 10
P95_MAXIMO_S = 60.0


def test_simulacao_entrega_todos_os_eventos(
    ingestao_ativa: httpx.Client, consulta: httpx.Client, gravador: GravadorEventos
) -> None:
    eventos = gravador.gerar(EVENTOS, pedidos=PEDIDOS)
    pendentes = {str(e.event_id): e for e in eventos}
    latencias: list[float] = []

    def todos_visiveis() -> bool:
        for pedido_id in {e.pedido_id for e in pendentes.values()}:
            resposta = consulta.get(f"/api/v1/pedidos/{pedido_id}/eventos")
            if resposta.status_code != httpx.codes.OK:
                continue
            agora = datetime.now(UTC)
            for item in resposta.json()["eventos"]:
                if (evento := pendentes.pop(item["event_id"], None)) is not None:
                    latencias.append((agora - evento.occurred_at).total_seconds())
        return not pendentes

    aguardar(todos_visiveis, timeout=60, intervalo=1)
    assert len(latencias) == EVENTOS  # SC-003/SC-004: nenhum evento perdido
    assert statistics.quantiles(latencias, n=20)[18] <= P95_MAXIMO_S  # SC-002
    aguardar(lambda: consulta.get("/api/v1/consumo/status").json()["lag_total"] == 0, 60)
