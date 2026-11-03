"""Mensagens HTML por evento (Telegram, `parse_mode=HTML`); dados externos são escapados."""

from html import escape

from contratos.evento import (
    EventoCriado,
    EventoEnviado,
    EventoPagamentoAprovado,
    EventoPagamentoRecusado,
    EventoPedido,
)


def formatar_mensagem(evento: EventoPedido) -> str:
    """Formata uma mensagem por evento, no padrão do exemplo da aula."""
    pedido = escape(evento.pedido_id)

    def reais(valor: float) -> str:
        return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    if isinstance(evento, EventoCriado):
        return (
            f"🛒 <b>Novo pedido {pedido}</b>\n"
            f"Cliente: {escape(evento.payload.cliente)} · Valor: {reais(evento.payload.valor)}"
        )
    if isinstance(evento, EventoPagamentoAprovado):
        return (
            f"✅ <b>Pagamento aprovado {pedido}</b>\n"
            f"{reais(evento.payload.valor)} via {escape(evento.payload.metodo)}"
        )
    if isinstance(evento, EventoPagamentoRecusado):
        return f"❌ <b>Pagamento recusado {pedido}</b>\nMotivo: {escape(evento.payload.motivo)}"
    if isinstance(evento, EventoEnviado):
        return (
            f"📦 <b>Pedido enviado {pedido}</b>\n"
            f"{escape(evento.payload.transportadora)}, rastreio {escape(evento.payload.rastreio)}"
        )
    return f"<b>{escape(evento.event_type.value)} {pedido}</b>"
