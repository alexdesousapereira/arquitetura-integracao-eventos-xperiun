"""US3 ponta a ponta: configuração do tópico e mensagens publicadas pelo Connect."""

from __future__ import annotations

import httpx
import pytest

from tests_e2e.conftest import ENV, TOPICO, GravadorEventos, aguardar, arquivos, consumir, kafka

pytestmark = pytest.mark.e2e


def test_configuracao_do_topico_segue_env() -> None:
    saida = kafka("kafka-configs", "--describe", "--entity-type", "topics", "--entity-name", TOPICO)
    assert f"retention.ms={ENV.get('TOPICO_RETENCAO_MS', '900000')}" in saida
    assert f"segment.ms={ENV.get('TOPICO_SEGMENT_MS', '60000')}" in saida
    descricao = kafka("kafka-topics", "--describe", "--topic", TOPICO)
    assert f"PartitionCount: {ENV.get('TOPICO_PARTICOES', '3')}" in descricao


def test_mensagens_tem_chave_e_headers(
    ingestao_ativa: httpx.Client, gravador: GravadorEventos
) -> None:
    gravador.gerar(5)
    aguardar(lambda: not arquivos("eventos"), timeout=30)
    for mensagem in consumir(20):
        assert mensagem["key"] == mensagem["value"]["pedido_id"]
        assert mensagem["headers"]["correlation_id"] == mensagem["value"]["correlation_id"]
        assert mensagem["headers"]["event_type"] == mensagem["value"]["event_type"]
