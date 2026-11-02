"""Modelos Pydantic do evento de carga (contrato v1).

Espelham `schemas/evento-carga.v1.schema.json`. O teste de contrato garante que os dois
permanecem equivalentes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from importlib.resources import files
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    TypeAdapter,
)

TOLERANCIA_FUTURO = timedelta(minutes=5)


class TipoEvento(StrEnum):
    """Tipos de evento do ciclo de vida de uma carga."""

    RECEBIDA = "carga.recebida"
    SAIU_PARA_TRANSPORTE = "carga.saiu_para_transporte"
    EM_TRANSITO = "carga.em_transito"
    SAIU_PARA_ENTREGA = "carga.saiu_para_entrega"
    ENTREGUE = "carga.entregue"
    ENTREGA_FALHOU = "carga.entrega_falhou"


class MotivoFalha(StrEnum):
    """Motivos possíveis para uma tentativa de entrega sem sucesso."""

    DESTINATARIO_AUSENTE = "DESTINATARIO_AUSENTE"
    ENDERECO_NAO_ENCONTRADO = "ENDERECO_NAO_ENCONTRADO"
    RECUSADA = "RECUSADA"


def _exigir_sufixo_z(valor: Any) -> Any:
    if isinstance(valor, str) and not valor.endswith("Z"):
        raise ValueError("data/hora deve estar em UTC e terminar com 'Z'")
    return valor


def _exigir_utc(valor: datetime) -> datetime:
    if valor.utcoffset() != timedelta(0):
        raise ValueError("data/hora deve estar em UTC")
    return valor.astimezone(UTC)


def _nao_futuro(valor: datetime) -> datetime:
    if valor > datetime.now(UTC) + TOLERANCIA_FUTURO:
        raise ValueError("occurred_at não pode estar mais de 5 minutos no futuro")
    return valor


def _iso_z(valor: datetime) -> str:
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[
    AwareDatetime,
    BeforeValidator(_exigir_sufixo_z),
    AfterValidator(_exigir_utc),
    PlainSerializer(_iso_z, return_type=str, when_used="json"),
]
"""Data/hora obrigatoriamente em UTC, serializada em ISO-8601 com sufixo `Z`."""

OcorridoEm = Annotated[UtcDatetime, AfterValidator(_nao_futuro)]
Uf = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
Cidade = Annotated[str, Field(min_length=1, max_length=100)]
VeiculoId = Annotated[str, Field(pattern=r"^VEI-[0-9]{4}$")]
Tentativa = Annotated[int, Field(ge=1, le=3)]
CargaId = Annotated[str, Field(pattern=r"^CRG-[0-9A-F]{8}$")]


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Localidade(_Modelo):
    """Cidade e UF."""

    cidade: Cidade
    uf: Uf


class Localizacao(_Modelo):
    """Posição geográfica durante o trajeto."""

    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    cidade: Cidade
    uf: Uf


class PayloadRecebida(_Modelo):
    """Dados da carga recebida no centro de distribuição."""

    origem: Localidade
    destino: Localidade
    peso_kg: Annotated[float, Field(gt=0, le=30000)]
    descricao: Annotated[str, Field(max_length=200)]
    centro_distribuicao: Cidade


class PayloadSaiuParaTransporte(_Modelo):
    """Dados do embarque no veículo de transferência."""

    veiculo_id: VeiculoId
    previsao_entrega: UtcDatetime


class PayloadEmTransito(_Modelo):
    """Atualização de posição durante o trajeto."""

    veiculo_id: VeiculoId
    localizacao: Localizacao


class PayloadSaiuParaEntrega(_Modelo):
    """Saída para entrega de última milha."""

    veiculo_id: VeiculoId
    tentativa: Tentativa


class PayloadEntregue(_Modelo):
    """Entrega concluída."""

    tentativa: Tentativa
    recebedor: Annotated[str, Field(min_length=1, max_length=100)]


class PayloadEntregaFalhou(_Modelo):
    """Tentativa de entrega sem sucesso."""

    tentativa: Tentativa
    motivo: MotivoFalha


class _Envelope(_Modelo):
    event_id: UUID
    event_version: Literal[1] = 1
    occurred_at: OcorridoEm
    source: Annotated[str, Field(min_length=1, max_length=100)]
    correlation_id: UUID
    carga_id: CargaId


class EventoRecebida(_Envelope):
    """Evento `carga.recebida`."""

    event_type: Literal[TipoEvento.RECEBIDA] = TipoEvento.RECEBIDA
    payload: PayloadRecebida


class EventoSaiuParaTransporte(_Envelope):
    """Evento `carga.saiu_para_transporte`."""

    event_type: Literal[TipoEvento.SAIU_PARA_TRANSPORTE] = TipoEvento.SAIU_PARA_TRANSPORTE
    payload: PayloadSaiuParaTransporte


class EventoEmTransito(_Envelope):
    """Evento `carga.em_transito`."""

    event_type: Literal[TipoEvento.EM_TRANSITO] = TipoEvento.EM_TRANSITO
    payload: PayloadEmTransito


class EventoSaiuParaEntrega(_Envelope):
    """Evento `carga.saiu_para_entrega`."""

    event_type: Literal[TipoEvento.SAIU_PARA_ENTREGA] = TipoEvento.SAIU_PARA_ENTREGA
    payload: PayloadSaiuParaEntrega


class EventoEntregue(_Envelope):
    """Evento `carga.entregue`."""

    event_type: Literal[TipoEvento.ENTREGUE] = TipoEvento.ENTREGUE
    payload: PayloadEntregue


class EventoEntregaFalhou(_Envelope):
    """Evento `carga.entrega_falhou`."""

    event_type: Literal[TipoEvento.ENTREGA_FALHOU] = TipoEvento.ENTREGA_FALHOU
    payload: PayloadEntregaFalhou


EventoCarga = Annotated[
    EventoRecebida
    | EventoSaiuParaTransporte
    | EventoEmTransito
    | EventoSaiuParaEntrega
    | EventoEntregue
    | EventoEntregaFalhou,
    Field(discriminator="event_type"),
]
"""União discriminada por `event_type` com todos os eventos do contrato v1."""

EventoCargaAdapter: TypeAdapter[EventoCarga] = TypeAdapter(EventoCarga)


def parse_evento(raw: bytes | str) -> EventoCarga:
    """Valida um evento serializado em JSON contra o contrato.

    Raises:
        pydantic.ValidationError: se o JSON for malformado ou estiver fora do contrato.
    """
    return EventoCargaAdapter.validate_json(raw)


def serializar_evento(evento: EventoCarga) -> bytes:
    """Serializa o evento em JSON UTF-8 conforme o contrato."""
    return EventoCargaAdapter.dump_json(evento)


def carregar_schema() -> dict[str, Any]:
    """Retorna o JSON Schema v1 versionado junto ao pacote."""
    texto = files("contratos").joinpath("schemas/evento-carga.v1.schema.json").read_text("utf-8")
    schema: dict[str, Any] = json.loads(texto)
    return schema
