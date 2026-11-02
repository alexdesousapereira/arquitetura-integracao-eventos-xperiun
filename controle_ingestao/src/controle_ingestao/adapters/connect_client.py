"""Cliente assíncrono da REST API do Kafka Connect."""

from __future__ import annotations

from typing import Any

import httpx

from controle_ingestao.observabilidade import (
    ERROS_CONNECT,
    HEADER_CORRELACAO,
    correlation_id_var,
)


class ConnectIndisponivelError(Exception):
    """O Kafka Connect não respondeu (conexão recusada, timeout etc.)."""


class ConectorInexistenteError(Exception):
    """O conector solicitado não existe no Kafka Connect."""


class ConnectErroError(Exception):
    """O Kafka Connect respondeu com erro (4xx/5xx)."""

    def __init__(self, status: int, detalhe: str) -> None:
        super().__init__(f"Kafka Connect respondeu {status}: {detalhe}")
        self.status = status
        self.detalhe = detalhe


NAO_ENCONTRADO = 404


class ConnectClient:
    """Operações sobre um conector via REST API do Kafka Connect."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _requisitar(self, metodo: str, caminho: str, **kwargs: Any) -> httpx.Response:
        headers = {}
        if correlacao := correlation_id_var.get():
            headers[HEADER_CORRELACAO] = correlacao
        try:
            return await self._http.request(metodo, caminho, headers=headers, **kwargs)
        except httpx.TransportError as exc:
            ERROS_CONNECT.labels("indisponivel").inc()
            raise ConnectIndisponivelError(str(exc) or type(exc).__name__) from exc

    @staticmethod
    def _verificar(resposta: httpx.Response, inexistente_ok: bool = False) -> None:
        if resposta.status_code == NAO_ENCONTRADO and not inexistente_ok:
            raise ConectorInexistenteError(resposta.url.path)
        if resposta.is_error and not (inexistente_ok and resposta.status_code == NAO_ENCONTRADO):
            ERROS_CONNECT.labels("resposta_erro").inc()
            try:
                detalhe = str(resposta.json().get("message", resposta.text))
            except ValueError:
                detalhe = resposta.text
            raise ConnectErroError(resposta.status_code, detalhe)

    async def ping(self) -> bool:
        """Retorna `True` se a REST API do Connect responder."""
        try:
            resposta = await self._requisitar("GET", "/")
        except ConnectIndisponivelError:
            return False
        return resposta.is_success

    async def obter_status(self, nome: str) -> dict[str, Any] | None:
        """Status do conector e de suas tarefas, ou `None` se não existir."""
        resposta = await self._requisitar("GET", f"/connectors/{nome}/status")
        if resposta.status_code == NAO_ENCONTRADO:
            return None
        self._verificar(resposta)
        dados: dict[str, Any] = resposta.json()
        return dados

    async def obter_config(self, nome: str) -> dict[str, Any] | None:
        """Configuração atual do conector, ou `None` se não existir."""
        resposta = await self._requisitar("GET", f"/connectors/{nome}/config")
        if resposta.status_code == NAO_ENCONTRADO:
            return None
        self._verificar(resposta)
        dados: dict[str, Any] = resposta.json()
        return dados

    async def aplicar_config(self, nome: str, config: dict[str, Any]) -> bool:
        """Cria ou atualiza o conector (idempotente); retorna `True` se foi criado."""
        resposta = await self._requisitar("PUT", f"/connectors/{nome}/config", json=config)
        self._verificar(resposta)
        return resposta.status_code == httpx.codes.CREATED

    async def pausar(self, nome: str) -> None:
        """Pausa o conector."""
        self._verificar(await self._requisitar("PUT", f"/connectors/{nome}/pause"))

    async def retomar(self, nome: str) -> None:
        """Retoma o conector pausado."""
        self._verificar(await self._requisitar("PUT", f"/connectors/{nome}/resume"))

    async def reiniciar(self, nome: str) -> None:
        """Reinicia o conector e todas as suas tarefas."""
        resposta = await self._requisitar(
            "POST",
            f"/connectors/{nome}/restart",
            params={"includeTasks": "true", "onlyFailed": "false"},
        )
        self._verificar(resposta)

    async def reiniciar_conector(self, nome: str) -> None:
        """Reinicia apenas a instância do conector (sem as tarefas)."""
        self._verificar(await self._requisitar("POST", f"/connectors/{nome}/restart"))

    async def remover(self, nome: str) -> None:
        """Remove o conector; não falha se ele já não existir."""
        resposta = await self._requisitar("DELETE", f"/connectors/{nome}")
        self._verificar(resposta, inexistente_ok=True)
