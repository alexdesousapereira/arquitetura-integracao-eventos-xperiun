"""Status derivado de uma carga a partir do tipo do evento mais recente."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from contratos.evento import TipoEvento


class StatusCarga(StrEnum):
    """Status atual de uma carga."""

    RECEBIDA = "RECEBIDA"
    EM_TRANSPORTE = "EM_TRANSPORTE"
    EM_TRANSITO = "EM_TRANSITO"
    SAIU_PARA_ENTREGA = "SAIU_PARA_ENTREGA"
    ENTREGUE = "ENTREGUE"
    FALHA_ENTREGA = "FALHA_ENTREGA"


STATUS_POR_TIPO: Mapping[TipoEvento, StatusCarga] = MappingProxyType(
    {
        TipoEvento.RECEBIDA: StatusCarga.RECEBIDA,
        TipoEvento.SAIU_PARA_TRANSPORTE: StatusCarga.EM_TRANSPORTE,
        TipoEvento.EM_TRANSITO: StatusCarga.EM_TRANSITO,
        TipoEvento.SAIU_PARA_ENTREGA: StatusCarga.SAIU_PARA_ENTREGA,
        TipoEvento.ENTREGUE: StatusCarga.ENTREGUE,
        TipoEvento.ENTREGA_FALHOU: StatusCarga.FALHA_ENTREGA,
    }
)
