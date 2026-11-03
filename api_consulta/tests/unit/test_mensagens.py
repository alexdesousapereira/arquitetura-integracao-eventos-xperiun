from datetime import timedelta

from api_consulta.services.projecao import Projecao, Resultado
from contratos import EventoCriado, formatar_mensagem


def test_replay_nao_duplica_avisos(relogio, gerar_jornada):
    proj = Projecao(timedelta(minutes=15), agora=relogio)
    eventos = gerar_jornada(1, inicio=relogio() - timedelta(seconds=10))
    for evento in eventos:
        assert proj.aplicar(evento) is Resultado.APLICADO
    for evento in eventos:
        assert proj.aplicar(evento) is Resultado.DUPLICADO
    avisos = [formatar_mensagem(e) for e in proj.historico(eventos[0].pedido_id)]
    assert len(avisos) == 3
    assert "Novo pedido" in avisos[0]
    assert "Pagamento aprovado" in avisos[1]
    assert "Pedido enviado" in avisos[2]


def test_html_escapa_cliente_e_formata_reais(gerar_jornada):
    original = gerar_jornada(1)[0]
    dados = original.model_dump()
    dados["payload"]["cliente"] = "<Carla & Ana>"
    dados["payload"]["valor"] = 111.88
    evento = EventoCriado.model_validate(dados)
    html = formatar_mensagem(evento)
    assert "&lt;Carla &amp; Ana&gt;" in html
    assert "R$ 111,88" in html
    assert "<Carla" not in html


def test_recusa_tem_motivo_sem_envio(gerar_jornada):
    eventos = gerar_jornada(1, prob_falha=1)
    avisos = [formatar_mensagem(e) for e in eventos]
    assert len(avisos) == 2
    assert "Pagamento recusado" in avisos[-1]
    assert "suspeita de fraude" in avisos[-1]


async def test_rota_mensagens_replay(relogio, gerar_jornada):
    import httpx
    from fastapi import FastAPI

    from api_consulta.api.dependencias import obter_projecao
    from api_consulta.api.pedidos import router

    proj = Projecao(timedelta(minutes=15), agora=relogio)
    eventos = gerar_jornada(1, inicio=relogio() - timedelta(seconds=10))
    for evento in eventos + eventos:
        proj.aplicar(evento)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[obter_projecao] = lambda: proj
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://teste"
    ) as client:
        resposta = await client.get(f"/api/v1/pedidos/{eventos[0].pedido_id}/mensagens")
    assert resposta.status_code == 200
    mensagens = resposta.json()
    assert len(mensagens) == 3
    assert len({m["event_id"] for m in mensagens}) == 3
    assert "Pagamento aprovado" in mensagens[1]["html"]
