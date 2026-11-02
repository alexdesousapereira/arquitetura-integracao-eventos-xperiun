"""Máquina de estados de uma carga simulada (data-model.md §4)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum, auto
from uuid import UUID

from contratos import (
    STATUS_POR_TIPO,
    EventoCarga,
    EventoEmTransito,
    EventoEntregaFalhou,
    EventoEntregue,
    EventoRecebida,
    EventoSaiuParaEntrega,
    EventoSaiuParaTransporte,
    Localidade,
    Localizacao,
    MotivoFalha,
    PayloadEmTransito,
    PayloadEntregaFalhou,
    PayloadEntregue,
    PayloadRecebida,
    PayloadSaiuParaEntrega,
    PayloadSaiuParaTransporte,
    StatusCarga,
)
from simulador.dominio.gerador import Cidade, Gerador

SOURCE = "simulador-transportadora"
MAX_TENTATIVAS = 3
PASSO_MINIMO = timedelta(milliseconds=1)


class _Etapa(Enum):
    RECEBER = auto()
    EMBARCAR = auto()
    TRANSITAR = auto()
    SAIR_PARA_ENTREGA = auto()
    TENTAR_ENTREGA = auto()
    CONCLUIDA = auto()


class CargaSimulada:
    """Uma carga que avança uma etapa do ciclo de vida a cada chamada de `proximo_evento`."""

    def __init__(
        self,
        gerador: Gerador,
        carga_id: str,
        correlation_id: UUID,
        origem: Cidade,
        destino: Cidade,
        prob_falha: float,
    ) -> None:
        self._g = gerador
        self.carga_id = carga_id
        self.correlation_id = correlation_id
        self.origem = origem
        self.destino = destino
        self.prob_falha = prob_falha
        self.veiculo_id = gerador.veiculo_id()
        self._etapa = _Etapa.RECEBER
        self._transitos_total = gerador.transitos()
        self._transitos_feitos = 0
        self._tentativa = 0
        self._ultimo: datetime | None = None
        self.status: StatusCarga | None = None

    @classmethod
    def nova(cls, gerador: Gerador, prob_falha: float) -> CargaSimulada:
        """Cria uma carga com identificadores e trajeto sorteados."""
        origem, destino = gerador.origem_destino()
        return cls(gerador, gerador.carga_id(), gerador.uuid(), origem, destino, prob_falha)

    @property
    def concluida(self) -> bool:
        """Indica se a carga chegou a um estado terminal."""
        return self._etapa is _Etapa.CONCLUIDA

    def proximo_evento(self, agora: datetime) -> EventoCarga | None:
        """Avança uma etapa e retorna o evento correspondente, ou `None` se a carga terminou.

        O `occurred_at` é sempre estritamente maior que o do evento anterior da mesma carga.
        """
        if self.concluida:
            return None
        ocorrido = agora if self._ultimo is None else max(agora, self._ultimo + PASSO_MINIMO)
        evento = self._gerar(ocorrido)
        self._ultimo = ocorrido
        self.status = STATUS_POR_TIPO[evento.event_type]
        return evento

    def _envelope(self, ocorrido: datetime) -> dict[str, object]:
        return {
            "event_id": self._g.uuid(),
            "occurred_at": ocorrido,
            "source": SOURCE,
            "correlation_id": self.correlation_id,
            "carga_id": self.carga_id,
        }

    def _gerar(self, ocorrido: datetime) -> EventoCarga:
        env = self._envelope(ocorrido)
        match self._etapa:
            case _Etapa.RECEBER:
                self._etapa = _Etapa.EMBARCAR
                return EventoRecebida(
                    **env,
                    payload=PayloadRecebida(
                        origem=Localidade(cidade=self.origem.nome, uf=self.origem.uf),
                        destino=Localidade(cidade=self.destino.nome, uf=self.destino.uf),
                        peso_kg=self._g.peso_kg(),
                        descricao=self._g.descricao(),
                        centro_distribuicao=self._g.centro_distribuicao(self.origem),
                    ),
                )
            case _Etapa.EMBARCAR:
                self._etapa = _Etapa.TRANSITAR
                return EventoSaiuParaTransporte(
                    **env,
                    payload=PayloadSaiuParaTransporte(
                        veiculo_id=self.veiculo_id,
                        previsao_entrega=ocorrido + timedelta(days=2),
                    ),
                )
            case _Etapa.TRANSITAR:
                self._transitos_feitos += 1
                if self._transitos_feitos >= self._transitos_total:
                    self._etapa = _Etapa.SAIR_PARA_ENTREGA
                return EventoEmTransito(
                    **env,
                    payload=PayloadEmTransito(
                        veiculo_id=self.veiculo_id, localizacao=self._posicao()
                    ),
                )
            case _Etapa.SAIR_PARA_ENTREGA:
                self._tentativa += 1
                self._etapa = _Etapa.TENTAR_ENTREGA
                return EventoSaiuParaEntrega(
                    **env,
                    payload=PayloadSaiuParaEntrega(
                        veiculo_id=self.veiculo_id, tentativa=self._tentativa
                    ),
                )
            case _Etapa.TENTAR_ENTREGA:
                return self._tentar_entrega(env)
            case _Etapa.CONCLUIDA:  # pragma: no cover - protegido por `concluida`
                raise RuntimeError("carga já concluída")

    def _tentar_entrega(self, env: dict[str, object]) -> EventoCarga:
        if self._g.sorteio() < self.prob_falha:
            ultima = self._tentativa >= MAX_TENTATIVAS
            self._etapa = _Etapa.CONCLUIDA if ultima else _Etapa.SAIR_PARA_ENTREGA
            motivo = self._g.rng.choice(list(MotivoFalha))
            return EventoEntregaFalhou(
                **env,
                payload=PayloadEntregaFalhou(tentativa=self._tentativa, motivo=motivo),
            )
        self._etapa = _Etapa.CONCLUIDA
        return EventoEntregue(
            **env,
            payload=PayloadEntregue(tentativa=self._tentativa, recebedor=self._g.recebedor()),
        )

    def _posicao(self) -> Localizacao:
        fracao = self._transitos_feitos / (self._transitos_total + 1)
        lat = self.origem.latitude + (self.destino.latitude - self.origem.latitude) * fracao
        lon = self.origem.longitude + (self.destino.longitude - self.origem.longitude) * fracao
        referencia = self.origem if fracao < 0.5 else self.destino
        return Localizacao(
            latitude=round(lat, 4),
            longitude=round(lon, 4),
            cidade=referencia.nome,
            uf=referencia.uf,
        )
