"""Ciclo de pedido: criação, pagamento e envio, com recusa terminal."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from contratos import (
    STATUS_POR_TIPO,
    EventoCriado,
    EventoEnviado,
    EventoPagamentoAprovado,
    EventoPagamentoRecusado,
    EventoPedido,
    Localidade,
    PayloadCriado,
    PayloadEnviado,
    PayloadPagamentoAprovado,
    PayloadPagamentoRecusado,
    StatusPedido,
)
from simulador.dominio.gerador import Cidade, Gerador


class PedidoSimulado:
    """Avança um evento por chamada, preservando a ordem de cada pedido."""

    def __init__(
        self,
        gerador: Gerador,
        pedido_id: str,
        correlation_id: UUID,
        origem: Cidade,
        destino: Cidade,
        prob_falha: float,
    ) -> None:
        self._g = gerador
        self.pedido_id = pedido_id
        self.correlation_id = correlation_id
        self.origem, self.destino = origem, destino
        self.prob_falha = prob_falha
        self.cliente = gerador.recebedor()
        self.valor = gerador.rng.randint(1000, 99999) / 100
        self._etapa = 0
        self._ultimo: datetime | None = None
        self.status: StatusPedido | None = None

    @classmethod
    def nova(cls, gerador: Gerador, prob_falha: float) -> PedidoSimulado:
        """Cria um pedido fictício reprodutível com a semente configurada."""
        origem, destino = gerador.origem_destino()
        return cls(gerador, gerador.pedido_id(), gerador.uuid(), origem, destino, prob_falha)

    @property
    def concluido(self) -> bool:
        """Recusado ou enviado."""
        return self._etapa == 3

    def proximo_evento(self, agora: datetime) -> EventoPedido | None:
        """Produz novo pedido, resultado do pagamento ou envio."""
        if self.concluido:
            return None
        ocorrido = (
            agora if self._ultimo is None else max(agora, self._ultimo + timedelta(milliseconds=1))
        )
        env = dict(
            event_id=self._g.uuid(),
            occurred_at=ocorrido,
            source="simulador-loja",
            correlation_id=self.correlation_id,
            pedido_id=self.pedido_id,
        )
        evento: EventoPedido
        if self._etapa == 0:
            evento = EventoCriado(
                **env,
                payload=PayloadCriado(
                    cliente=self.cliente,
                    valor=self.valor,
                    origem=Localidade(cidade=self.origem.nome, uf=self.origem.uf),
                    destino=Localidade(cidade=self.destino.nome, uf=self.destino.uf),
                    peso_kg=self._g.peso_kg(),
                    descricao=self._g.descricao(),
                    centro_distribuicao=self._g.centro_distribuicao(self.origem),
                ),
            )
            self._etapa = 1
        elif self._etapa == 1:
            if self._g.sorteio() < self.prob_falha:
                evento = EventoPagamentoRecusado(
                    **env, payload=PayloadPagamentoRecusado(motivo="suspeita de fraude")
                )
                self._etapa = 3
            else:
                evento = EventoPagamentoAprovado(
                    **env, payload=PayloadPagamentoAprovado(valor=self.valor, metodo="pix")
                )
                self._etapa = 2
        else:
            evento = EventoEnviado(
                **env,
                payload=PayloadEnviado(
                    transportadora="Correios",
                    rastreio=f"BR{self._g.rng.randint(100000000, 999999999)}",
                    veiculo_id=self._g.veiculo_id(),
                    previsao_entrega=ocorrido + timedelta(days=2),
                ),
            )
            self._etapa = 3
        self._ultimo = ocorrido
        self.status = STATUS_POR_TIPO[evento.event_type]
        return evento
