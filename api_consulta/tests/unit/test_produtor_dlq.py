from __future__ import annotations

from typing import Any

from api_consulta.adapters.mensagem import Mensagem
from api_consulta.adapters.produtor_dlq import ProdutorDLQ


class ProducerFalso:
    def __init__(self) -> None:
        self.envios: list[dict[str, Any]] = []

    async def send_and_wait(self, topic: str, **kwargs: Any) -> None:
        self.envios.append({"topic": topic, **kwargs})


async def test_preserva_chave_valor_e_adiciona_headers() -> None:
    producer = ProducerFalso()
    msg = Mensagem(
        topic="eventos",
        partition=1,
        offset=7,
        key=b"CRG-1",
        value=b"{ quebrado",
        headers=[("correlation_id", b"corr-9")],
    )
    await ProdutorDLQ(producer, "dlq").enviar(msg, "JSON_INVALIDO", "x" * 2000)  # type: ignore[arg-type]
    envio = producer.envios[0]
    assert envio["topic"] == "dlq"
    assert envio["key"] == b"CRG-1"
    assert envio["value"] == b"{ quebrado"
    headers = dict(envio["headers"])
    assert headers["erro_tipo"] == b"JSON_INVALIDO"
    assert len(headers["erro_motivo"]) == 1000
    assert headers["topico_origem"] == b"eventos"
    assert headers["particao_origem"] == b"1"
    assert headers["offset_origem"] == b"7"
    assert headers["correlation_id"] == b"corr-9"
