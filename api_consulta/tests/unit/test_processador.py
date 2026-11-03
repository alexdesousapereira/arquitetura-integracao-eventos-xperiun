from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from api_consulta.adapters.mensagem import Mensagem
from api_consulta.services.processador import Processador
from api_consulta.services.projecao import Projecao
from contratos import EventoPedidoAdapter


class DLQFalso:
    def __init__(self, falhar: bool = False) -> None:
        self.enviadas: list[tuple[Mensagem, str, str]] = []
        self.falhar = falhar

    async def enviar(self, mensagem: Mensagem, erro_tipo: str, erro_motivo: str) -> None:
        if self.falhar:
            raise RuntimeError("broker fora")
        self.enviadas.append((mensagem, erro_tipo, erro_motivo))


def _msg(valor: bytes | None, headers: list[tuple[str, bytes]] | None = None) -> Mensagem:
    return Mensagem(
        topic="t", partition=2, offset=41, key=b"PED-1", value=valor, headers=headers or []
    )


def _valido(gerar_jornada: Any, relogio: Any) -> bytes:
    evento = gerar_jornada(1, inicio=relogio())[0]
    return EventoPedidoAdapter.dump_json(evento)


@pytest.fixture
def projecao(relogio: Any) -> Projecao:
    return Projecao(timedelta(minutes=15), agora=relogio)


async def test_mensagem_valida_aplicada(projecao, relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    dlq = DLQFalso()
    await Processador(projecao, dlq).processar(_msg(_valido(gerar_jornada, relogio)))
    assert projecao.resumo().total_eventos == 1
    assert dlq.enviadas == []


@pytest.mark.parametrize("valor", [b"{ quebrado", b"", None, b"[1, 2]"])
async def test_nao_json_vai_para_dlq(projecao, valor) -> None:  # type: ignore[no-untyped-def]
    dlq = DLQFalso()
    await Processador(projecao, dlq).processar(_msg(valor))
    assert len(dlq.enviadas) == 1
    assert dlq.enviadas[0][1] == "JSON_INVALIDO"
    assert projecao.resumo().eventos_enviados_dlq == 1


async def test_fora_do_contrato_vai_para_dlq_com_motivo_truncado(projecao) -> None:  # type: ignore[no-untyped-def]
    dlq = DLQFalso()
    valor = json.dumps({"event_type": "pedido.criado", "lixo": "x" * 5000}).encode()
    await Processador(projecao, dlq).processar(_msg(valor))
    _, tipo, motivo = dlq.enviadas[0]
    assert tipo == "CONTRATO_INVALIDO"
    assert 0 < len(motivo) <= 1000


async def test_falha_no_dlq_nao_interrompe(projecao) -> None:  # type: ignore[no-untyped-def]
    from prometheus_client import REGISTRY

    antes = REGISTRY.get_sample_value("consulta_erros_total", {"tipo": "envio_dlq"}) or 0
    await Processador(projecao, DLQFalso(falhar=True)).processar(_msg(b"{ quebrado"))
    assert projecao.resumo().eventos_enviados_dlq == 0
    depois = REGISTRY.get_sample_value("consulta_erros_total", {"tipo": "envio_dlq"})
    assert depois == antes + 1


async def test_duplicado_nao_vai_ao_dlq(projecao, relogio, gerar_jornada) -> None:  # type: ignore[no-untyped-def]
    dlq = DLQFalso()
    proc = Processador(projecao, dlq)
    valor = _valido(gerar_jornada, relogio)
    await proc.processar(_msg(valor))
    await proc.processar(_msg(valor))
    assert dlq.enviadas == []
    assert projecao.resumo().eventos_duplicados_descartados == 1


def test_correlation_id_do_header_ou_corpo() -> None:
    from api_consulta.services.processador import extrair_correlation_id

    assert extrair_correlation_id(_msg(b"{}", [("correlation_id", b"h-1")]), {}) == "h-1"
    assert extrair_correlation_id(_msg(b"{}"), {"correlation_id": "c-2"}) == "c-2"
    assert extrair_correlation_id(_msg(b"{}"), None) is None
