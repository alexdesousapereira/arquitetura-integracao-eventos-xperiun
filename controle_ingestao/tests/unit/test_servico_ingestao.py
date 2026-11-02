from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from controle_ingestao.adapters.connect_client import ConnectIndisponivelError
from controle_ingestao.adapters.pastas import Pastas, contar_arquivos
from controle_ingestao.services.ingestao import (
    EstadoIngestao,
    IngestaoInexistenteError,
    ServicoIngestao,
    mapear_estado,
)


def _status(conector: str, *tarefas: str) -> dict[str, Any]:
    return {
        "connector": {"state": conector},
        "tasks": [
            {"id": i, "state": t, **({"trace": "boom\nlinha2"} if t == "FAILED" else {})}
            for i, t in enumerate(tarefas)
        ],
    }


@pytest.mark.parametrize(
    ("status", "esperado"),
    [
        (None, EstadoIngestao.INEXISTENTE),
        (_status("RUNNING", "RUNNING"), EstadoIngestao.ATIVA),
        (_status("PAUSED", "PAUSED"), EstadoIngestao.PAUSADA),
        (_status("FAILED"), EstadoIngestao.COM_FALHA),
        (_status("RUNNING", "FAILED"), EstadoIngestao.COM_FALHA),
        (_status("RUNNING"), EstadoIngestao.ATIVA),
        (_status("UNASSIGNED"), EstadoIngestao.INICIANDO),
        (_status("RESTARTING", "RESTARTING"), EstadoIngestao.INICIANDO),
        (_status("RUNNING", "UNASSIGNED"), EstadoIngestao.INICIANDO),
    ],
)
def test_mapear_estado(status: dict[str, Any] | None, esperado: EstadoIngestao) -> None:
    assert mapear_estado(status) is esperado


class ClienteFalso:
    def __init__(self, status: dict[str, Any] | None = None) -> None:
        self.status = status
        self.chamadas: list[str] = []
        self.disponivel = True
        self.config: dict[str, Any] = {"name": "arquivos", "connector.class": "Antiga"}

    async def ping(self) -> bool:
        return self.disponivel

    async def obter_status(self, nome: str) -> dict[str, Any] | None:
        if not self.disponivel:
            raise ConnectIndisponivelError("fora")
        return self.status

    async def obter_config(self, nome: str) -> dict[str, Any] | None:
        return None if self.status is None else self.config

    async def aplicar_config(self, nome: str, config: dict[str, Any]) -> bool:
        self.chamadas.append("config")
        criado = self.status is None
        self.status = _status("RUNNING", "RUNNING")
        self.config = {"name": nome, **config}
        return criado

    async def pausar(self, nome: str) -> None:
        self.chamadas.append("pausar")

    async def retomar(self, nome: str) -> None:
        self.chamadas.append("retomar")

    async def reiniciar(self, nome: str) -> None:
        self.chamadas.append("reiniciar")

    async def reiniciar_conector(self, nome: str) -> None:
        self.chamadas.append("reiniciar_conector")
        self.status = _status("RUNNING", "RUNNING")

    async def remover(self, nome: str) -> None:
        self.chamadas.append("remover")
        self.status = None


@pytest.fixture
def pastas(tmp_path: Path) -> Pastas:
    p = Pastas(tmp_path / "eventos", tmp_path / "backup", tmp_path / "erros")
    for pasta in (p.eventos, p.backup, p.erros):
        pasta.mkdir()
    return p


@pytest.fixture
def config_conector(tmp_path: Path) -> Path:
    caminho = tmp_path / "conector.json"
    caminho.write_text(json.dumps({"connector.class": "X"}))
    return caminho


def _servico(cliente: ClienteFalso, pastas: Pastas, config: Path) -> ServicoIngestao:
    return ServicoIngestao(  # type: ignore[arg-type]
        cliente, "arquivos", config, pastas, vigia_duracao_s=0.05, vigia_intervalo_s=0.01
    )


FALHA_SHUTDOWN = {
    "connector": {
        "state": "FAILED",
        "trace": "ConnectException: ... connector 'x' has already been shut down.",
    },
    "tasks": [{"id": 0, "state": "RUNNING"}],
}


async def test_status_recupera_falha_conhecida_do_filepulse(
    pastas: Pastas, config_conector: Path
) -> None:
    cliente = ClienteFalso(dict(FALHA_SHUTDOWN))
    status = await _servico(cliente, pastas, config_conector).status()
    assert cliente.chamadas == ["reiniciar_conector"]
    assert status.estado is EstadoIngestao.ATIVA


async def test_outras_falhas_nao_sao_recuperadas(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso(_status("FAILED"))
    status = await _servico(cliente, pastas, config_conector).status()
    assert cliente.chamadas == []
    assert status.estado is EstadoIngestao.COM_FALHA


async def test_vigia_apos_pausa_recupera_falha(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso(_status("RUNNING", "RUNNING"))
    servico = _servico(cliente, pastas, config_conector)
    await servico.pausar()
    cliente.status = dict(FALHA_SHUTDOWN)  # a falha aparece depois da resposta ao cliente
    await servico.aguardar_vigias()
    assert cliente.chamadas == ["pausar", "reiniciar_conector"]


async def test_status_inclui_tarefas_e_arquivos(pastas: Pastas, config_conector: Path) -> None:
    (pastas.eventos / "a.json").write_text("{}")
    (pastas.eventos / ".b.json.tmp").write_text("{}")
    (pastas.backup / "c.json").write_text("{}")
    (pastas.backup / "d.json").write_text("{}")
    cliente = ClienteFalso(_status("RUNNING", "FAILED"))
    status = await _servico(cliente, pastas, config_conector).status()
    assert status.estado is EstadoIngestao.COM_FALHA
    assert status.tarefas[0].erro == "boom"
    assert status.arquivos.pendentes == 1
    assert status.arquivos.em_backup == 2
    assert status.arquivos.com_erro == 0
    assert status.connect_disponivel is True


async def test_status_com_connect_fora_propaga_erro(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso()
    cliente.disponivel = False
    with pytest.raises(ConnectIndisponivelError):
        await _servico(cliente, pastas, config_conector).status()


async def test_ativar_cria_com_config_versionada(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso(None)
    status, criado = await _servico(cliente, pastas, config_conector).ativar()
    assert criado is True
    assert status.estado is EstadoIngestao.ATIVA
    status, criado = await _servico(cliente, pastas, config_conector).ativar()
    assert criado is False
    assert cliente.chamadas == ["config"]  # config idêntica não é reaplicada


async def test_ativar_aguarda_registro_do_conector(pastas: Pastas, config_conector: Path) -> None:
    class ClienteLento(ClienteFalso):
        async def aplicar_config(self, nome: str, config: dict[str, Any]) -> bool:
            self.chamadas.append("config")
            self.pendentes = 2
            return True

        async def obter_status(self, nome: str) -> dict[str, Any] | None:
            if getattr(self, "pendentes", 0):
                self.pendentes -= 1
                if self.pendentes == 0:
                    self.status = _status("RUNNING")
                return None
            return self.status

    status, criado = await _servico(ClienteLento(None), pastas, config_conector).ativar()
    assert criado is True
    assert status.estado is EstadoIngestao.ATIVA


async def test_ativar_reaplica_config_divergente(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso(_status("RUNNING", "RUNNING"))
    _, criado = await _servico(cliente, pastas, config_conector).ativar()
    assert criado is False
    assert cliente.chamadas == ["config"]


async def test_retomar_nao_chama_connect_se_iniciando(
    pastas: Pastas, config_conector: Path
) -> None:
    cliente = ClienteFalso(_status("RUNNING", "UNASSIGNED"))
    await _servico(cliente, pastas, config_conector).retomar()
    assert cliente.chamadas == []


async def test_pausar_idempotente(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso(_status("PAUSED", "PAUSED"))
    await _servico(cliente, pastas, config_conector).pausar()
    assert cliente.chamadas == []


async def test_retomar_idempotente(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso(_status("RUNNING", "RUNNING"))
    await _servico(cliente, pastas, config_conector).retomar()
    assert cliente.chamadas == []


async def test_pausar_e_retomar_chamam_connect(pastas: Pastas, config_conector: Path) -> None:
    servico = _servico(
        cliente := ClienteFalso(_status("RUNNING", "RUNNING")), pastas, config_conector
    )
    await servico.pausar()
    cliente.status = _status("PAUSED", "PAUSED")
    await servico.retomar()
    await servico.reiniciar()
    assert cliente.chamadas == ["pausar", "retomar", "reiniciar"]


@pytest.mark.parametrize("acao", ["pausar", "retomar", "reiniciar"])
async def test_acoes_em_ingestao_inexistente(
    pastas: Pastas, config_conector: Path, acao: str
) -> None:
    servico = _servico(ClienteFalso(None), pastas, config_conector)
    with pytest.raises(IngestaoInexistenteError):
        await getattr(servico, acao)()


async def test_remover(pastas: Pastas, config_conector: Path) -> None:
    cliente = ClienteFalso(_status("RUNNING", "RUNNING"))
    await _servico(cliente, pastas, config_conector).remover()
    assert cliente.chamadas == ["remover"]


async def test_contar_arquivos_pasta_inexistente(tmp_path: Path) -> None:
    assert await contar_arquivos(tmp_path / "nao-existe") == 0


async def test_contar_ignora_ocultos_e_subpastas(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / ".b.json.tmp").write_text("{}")
    (tmp_path / ".c.json").write_text("{}")
    (tmp_path / "d.txt").write_text("x")
    (tmp_path / "sub.json").mkdir()
    assert await contar_arquivos(tmp_path) == 1
