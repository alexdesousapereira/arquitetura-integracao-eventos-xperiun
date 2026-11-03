"""Regras de operação da ingestão (data-model.md §6)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, Field

from controle_ingestao.adapters.pastas import Pastas, contar_arquivos
from controle_ingestao.observabilidade import ARQUIVOS

# Condição de corrida conhecida do FilePulse 2.18: ao parar a instância do conector (pausa,
# reconfiguração), a thread de monitoramento antiga ainda pede reconfiguração de tarefas e o
# Connect marca o conector como FAILED. Reiniciar só a instância do conector resolve.
FALHA_FILEPULSE_SHUTDOWN = "has already been shut down"
VIGIA_DURACAO_S = 15.0
VIGIA_INTERVALO_S = 1.0
TENTATIVAS_REGISTRO = 20

log = structlog.get_logger()


class IngestaoInexistenteError(Exception):
    """A ingestão (conector) ainda não foi criada."""


class EstadoIngestao(StrEnum):
    """Estado da ingestão exposto pela API."""

    ATIVA = "ATIVA"
    PAUSADA = "PAUSADA"
    COM_FALHA = "COM_FALHA"
    INICIANDO = "INICIANDO"
    INEXISTENTE = "INEXISTENTE"


class Tarefa(BaseModel):
    """Tarefa do conector."""

    id: int
    estado: str = Field(examples=["RUNNING"])
    erro: str | None = Field(default=None, description="Primeira linha do trace quando FAILED")


class ContagemArquivos(BaseModel):
    """Arquivos por situação nas pastas de dados."""

    pendentes: int = Field(ge=0)
    em_backup: int = Field(ge=0)
    com_erro: int = Field(ge=0)


class StatusIngestao(BaseModel):
    """Visão consolidada da ingestão."""

    nome: str = Field(examples=["arquivos-eventos-loja"])
    estado: EstadoIngestao
    tarefas: list[Tarefa]
    arquivos: ContagemArquivos
    connect_disponivel: bool
    consultado_em: datetime


class ClienteConnect(Protocol):
    """Operações do Kafka Connect usadas pelo serviço."""

    async def obter_status(self, nome: str) -> dict[str, Any] | None:
        """Status do conector ou `None`."""
        ...

    async def obter_config(self, nome: str) -> dict[str, Any] | None:
        """Configuração atual ou `None`."""
        ...

    async def aplicar_config(self, nome: str, config: dict[str, Any]) -> bool:
        """Cria/atualiza o conector; `True` se criado."""
        ...

    async def pausar(self, nome: str) -> None:
        """Pausa o conector."""
        ...

    async def retomar(self, nome: str) -> None:
        """Retoma o conector."""
        ...

    async def reiniciar(self, nome: str) -> None:
        """Reinicia conector e tarefas."""
        ...

    async def reiniciar_conector(self, nome: str) -> None:
        """Reinicia apenas a instância do conector."""
        ...

    async def remover(self, nome: str) -> None:
        """Remove o conector."""
        ...


_INICIANDO = {"UNASSIGNED", "RESTARTING"}


def falha_recuperavel(status: dict[str, Any] | None) -> bool:
    """Indica a falha do FilePulse ao parar a instância (ver `FALHA_FILEPULSE_SHUTDOWN`)."""
    conector = (status or {}).get("connector", {})
    return conector.get("state") == "FAILED" and FALHA_FILEPULSE_SHUTDOWN in (
        conector.get("trace") or ""
    )


def mapear_estado(status: dict[str, Any] | None) -> EstadoIngestao:
    """Converte o status do Kafka Connect no estado exposto pela API."""
    if status is None:
        return EstadoIngestao.INEXISTENTE
    conector = status.get("connector", {}).get("state")
    tarefas = [t.get("state") for t in status.get("tasks", [])]
    if conector == "FAILED" or "FAILED" in tarefas:
        return EstadoIngestao.COM_FALHA
    if conector in {"PAUSED", "STOPPED"}:
        return EstadoIngestao.PAUSADA
    # O FilePulse só mantém tarefas enquanto há arquivos a processar: conector RUNNING sem
    # tarefas é o estado ocioso normal da ingestão ativa.
    if conector == "RUNNING" and all(t == "RUNNING" for t in tarefas):
        return EstadoIngestao.ATIVA
    return EstadoIngestao.INICIANDO


def _tarefas(status: dict[str, Any] | None) -> list[Tarefa]:
    if status is None:
        return []
    return [
        Tarefa(
            id=t["id"],
            estado=t["state"],
            erro=(t.get("trace") or "").splitlines()[0] if t.get("trace") else None,
        )
        for t in status.get("tasks", [])
    ]


class ServicoIngestao:
    """Aplica as transições permitidas sobre o conector de ingestão."""

    def __init__(
        self,
        cliente: ClienteConnect,
        nome: str,
        config_path: Path,
        pastas: Pastas,
        vigia_duracao_s: float = VIGIA_DURACAO_S,
        vigia_intervalo_s: float = VIGIA_INTERVALO_S,
    ) -> None:
        self.cliente = cliente
        self.nome = nome
        self.config_path = config_path
        self.pastas = pastas
        self.vigia_duracao_s = vigia_duracao_s
        self.vigia_intervalo_s = vigia_intervalo_s
        self._vigias: set[asyncio.Task[None]] = set()

    async def _obter_status(self) -> dict[str, Any] | None:
        """Status do Connect, recuperando automaticamente a falha conhecida do FilePulse."""
        status = await self.cliente.obter_status(self.nome)
        if falha_recuperavel(status):
            log.warning("conector_recuperado", motivo="filepulse_shutdown_race")
            await self.cliente.reiniciar_conector(self.nome)
            status = await self.cliente.obter_status(self.nome)
        return status

    async def _vigiar(self) -> None:
        tempo = 0.0
        while tempo < self.vigia_duracao_s:
            await asyncio.sleep(self.vigia_intervalo_s)
            tempo += self.vigia_intervalo_s
            try:
                await self._obter_status()
            except Exception:  # pragma: no cover - melhor esforço
                log.exception("falha_na_vigia")

    def _iniciar_vigia(self) -> None:
        """Acompanha o conector por alguns segundos após uma ação que reinicia a instância."""
        tarefa = asyncio.create_task(self._vigiar())
        self._vigias.add(tarefa)
        tarefa.add_done_callback(self._vigias.discard)

    async def cancelar_vigias(self) -> None:
        """Interrompe as vigias em andamento (shutdown da aplicação)."""
        for tarefa in list(self._vigias):
            tarefa.cancel()
        await self.aguardar_vigias()

    async def aguardar_vigias(self) -> None:
        """Aguarda as vigias em andamento (usado em testes e no shutdown)."""
        if self._vigias:
            await asyncio.gather(*self._vigias, return_exceptions=True)

    async def _arquivos(self) -> ContagemArquivos:
        pendentes, backup, erros = await asyncio.gather(
            contar_arquivos(self.pastas.eventos),
            contar_arquivos(self.pastas.backup),
            contar_arquivos(self.pastas.erros),
        )
        ARQUIVOS.labels("pendente").set(pendentes)
        ARQUIVOS.labels("backup").set(backup)
        ARQUIVOS.labels("erro").set(erros)
        return ContagemArquivos(pendentes=pendentes, em_backup=backup, com_erro=erros)

    async def _montar(self, status: dict[str, Any] | None) -> StatusIngestao:
        return StatusIngestao(
            nome=self.nome,
            estado=mapear_estado(status),
            tarefas=_tarefas(status),
            arquivos=await self._arquivos(),
            connect_disponivel=True,
            consultado_em=datetime.now(UTC),
        )

    async def _status_existente(self) -> dict[str, Any]:
        status = await self._obter_status()
        if status is None:
            raise IngestaoInexistenteError(self.nome)
        return status

    async def status(self) -> StatusIngestao:
        """Estado atual (inclui `INEXISTENTE`)."""
        return await self._montar(await self._obter_status())

    async def ativar(self) -> tuple[StatusIngestao, bool]:
        """Aplica a configuração versionada; retorna o status e se o conector foi criado.

        Se a configuração em uso já for a versionada, não reaplica: um `PUT` no Kafka Connect
        reinicia o conector mesmo com a configuração idêntica.
        """
        config: dict[str, Any] = await asyncio.to_thread(
            lambda: json.loads(self.config_path.read_text(encoding="utf-8"))
        )
        atual = await self.cliente.obter_config(self.nome)
        if atual is not None and {k: v for k, v in atual.items() if k != "name"} == config:
            return await self.status(), False
        criado = await self.cliente.aplicar_config(self.nome, config)
        self._iniciar_vigia()
        # O Connect registra o conector de forma assíncrona: aguarda ele aparecer no status.
        for _ in range(TENTATIVAS_REGISTRO):
            status = await self.status()
            if status.estado is not EstadoIngestao.INEXISTENTE:
                break
            await asyncio.sleep(self.vigia_intervalo_s / 2)
        return status, criado

    async def pausar(self) -> StatusIngestao:
        """Pausa a ingestão; sem efeito se já estiver pausada."""
        status = await self._status_existente()
        if mapear_estado(status) is not EstadoIngestao.PAUSADA:
            await self.cliente.pausar(self.nome)
            self._iniciar_vigia()
        return await self.status()

    async def retomar(self) -> StatusIngestao:
        """Retoma a ingestão; sem efeito se ela não estiver pausada."""
        status = await self._status_existente()
        if mapear_estado(status) is EstadoIngestao.PAUSADA:
            await self.cliente.retomar(self.nome)
            self._iniciar_vigia()
        return await self.status()

    async def reiniciar(self) -> StatusIngestao:
        """Reinicia conector e tarefas."""
        await self._status_existente()
        await self.cliente.reiniciar(self.nome)
        self._iniciar_vigia()
        return await self.status()

    async def remover(self) -> None:
        """Remove a ingestão (idempotente)."""
        await self.cliente.remover(self.nome)
