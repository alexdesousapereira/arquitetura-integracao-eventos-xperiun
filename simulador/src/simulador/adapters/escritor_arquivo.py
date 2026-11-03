"""Gravação atômica de eventos como arquivos JSON (research.md, R7)."""

from __future__ import annotations

import os
from pathlib import Path

from contratos import EventoPedido, serializar_evento


class ErroGravacaoEvento(Exception):
    """Falha de I/O ao gravar um evento na pasta de saída."""


class EscritorArquivo:
    """Grava cada evento em `<saida>/<occurred_at>_<pedido_id>_<event_id>.json`.

    O conteúdo é escrito primeiro em um arquivo oculto (`.<nome>.tmp`), sincronizado em disco e
    então renomeado — o `rename` no mesmo filesystem é atômico, e o conector ignora arquivos
    ocultos, então nunca há leitura parcial.
    """

    def __init__(self, saida: Path) -> None:
        self.saida = saida

    @staticmethod
    def nome_arquivo(evento: EventoPedido) -> str:
        """Nome ordenável lexicograficamente pelo instante de ocorrência."""
        instante = evento.occurred_at.strftime("%Y%m%dT%H%M%S%f")
        return f"{instante}Z_{evento.pedido_id}_{evento.event_id}.json"

    def gravar(self, evento: EventoPedido) -> Path:
        """Grava o evento de forma atômica e retorna o caminho final.

        Raises:
            ErroGravacaoEvento: se a pasta não puder ser criada ou o arquivo escrito.
        """
        nome = self.nome_arquivo(evento)
        destino = self.saida / nome
        temporario = self.saida / f".{nome}.tmp"
        try:
            self.saida.mkdir(parents=True, exist_ok=True)
            with temporario.open("wb") as arquivo:
                arquivo.write(serializar_evento(evento))
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, destino)
        except OSError as exc:
            temporario.unlink(missing_ok=True)
            raise ErroGravacaoEvento(f"não foi possível gravar {destino}: {exc}") from exc
        return destino
