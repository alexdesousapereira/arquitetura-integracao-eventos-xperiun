"""Canais de entrega: Telegram (envio real) e log (modo demonstração, sem token)."""

from __future__ import annotations

from typing import Any, Protocol

import httpx
import structlog

log = structlog.get_logger()


class ErroEnvio(Exception):
    """Falha ao entregar uma mensagem.

    `temporario=True` indica que vale tentar de novo (rede, limite de envio, token/chat ainda
    não configurados corretamente); `False`, que a própria mensagem foi rejeitada.
    """

    def __init__(self, motivo: str, *, temporario: bool, aguardar_s: float = 0.0) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.temporario = temporario
        self.aguardar_s = aguardar_s


class Canal(Protocol):
    """Destino das mensagens."""

    nome: str

    async def enviar(self, html: str) -> None:
        """Entrega uma mensagem HTML; levanta `ErroEnvio` em caso de falha."""
        ...

    async def fechar(self) -> None:
        """Libera recursos."""
        ...


class CanalLog:
    """Modo demonstração: registra no log a mensagem que seria enviada."""

    nome = "log"

    async def enviar(self, html: str) -> None:
        """Escreve a mensagem no log."""
        log.info("mensagem_simulada", html=html)

    async def fechar(self) -> None:
        """Nada a liberar."""


class CanalTelegram:
    """Envia mensagens pela Bot API do Telegram (`sendMessage` com `parse_mode=HTML`)."""

    nome = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        api_url: str = "https://api.telegram.org",
        cliente: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = f"{api_url.rstrip('/')}/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._cliente = cliente or httpx.AsyncClient(timeout=10)

    async def enviar(self, html: str) -> None:
        """Envia a mensagem ao chat configurado."""
        corpo = {
            "chat_id": self._chat_id,
            "text": html,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        try:
            resposta = await self._cliente.post(self._url, json=corpo)
        except httpx.HTTPError as exc:
            # `from None`: a exceção original do httpx carrega a URL, que contém o token.
            raise ErroEnvio(f"falha de rede ({type(exc).__name__})", temporario=True) from None
        if resposta.status_code == 200:
            return
        dados = _json(resposta)
        descricao = str(dados.get("description", ""))[:200]
        motivo = f"HTTP {resposta.status_code}: {descricao}"
        if resposta.status_code == 429:
            espera = float(dados.get("parameters", {}).get("retry_after", 1))
            raise ErroEnvio(motivo, temporario=True, aguardar_s=espera)
        # 400 é problema da mensagem (ex.: HTML inválido), exceto chat inexistente, que é de
        # configuração. 401/403/404/5xx também são de configuração ou do serviço: tentar de novo.
        mensagem_rejeitada = resposta.status_code == 400 and "chat not found" not in descricao
        raise ErroEnvio(motivo, temporario=not mensagem_rejeitada)

    async def fechar(self) -> None:
        """Fecha o cliente HTTP."""
        await self._cliente.aclose()


def _json(resposta: httpx.Response) -> dict[str, Any]:
    try:
        dados = resposta.json()
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}
