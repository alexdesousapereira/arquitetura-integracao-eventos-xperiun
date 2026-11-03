"""Status derivado de um pedido a partir do tipo do evento mais recente."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from contratos.evento import TipoEvento


class StatusPedido(StrEnum):
    """Status atual de um pedido."""

    CRIADO = "CRIADO"
    PAGAMENTO_APROVADO = "PAGAMENTO_APROVADO"
    PAGAMENTO_RECUSADO = "PAGAMENTO_RECUSADO"
    ENVIADO = "ENVIADO"
    EM_TRANSITO = "EM_TRANSITO"
    SAIU_PARA_ENTREGA = "SAIU_PARA_ENTREGA"
    ENTREGUE = "ENTREGUE"
    FALHA_ENTREGA = "FALHA_ENTREGA"


STATUS_POR_TIPO: Mapping[TipoEvento, StatusPedido] = MappingProxyType(
    {
        TipoEvento.PAGAMENTO_APROVADO: StatusPedido.PAGAMENTO_APROVADO,
        TipoEvento.PAGAMENTO_RECUSADO: StatusPedido.PAGAMENTO_RECUSADO,
        TipoEvento.CRIADO: StatusPedido.CRIADO,
        TipoEvento.ENVIADO: StatusPedido.ENVIADO,
        TipoEvento.EM_TRANSITO: StatusPedido.EM_TRANSITO,
        TipoEvento.SAIU_PARA_ENTREGA: StatusPedido.SAIU_PARA_ENTREGA,
        TipoEvento.ENTREGUE: StatusPedido.ENTREGUE,
        TipoEvento.ENTREGA_FALHOU: StatusPedido.FALHA_ENTREGA,
    }
)
