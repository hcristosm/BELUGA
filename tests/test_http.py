from __future__ import annotations

import pytest
import responses

from src.coleta.http import BloqueadoPorRobots, Cliente, ColetaError
from src.config import USER_AGENT

BASE = "https://dados.exemplo.gov.br"


@responses.activate
def test_envia_user_agent_identificado(cliente):
    responses.get(f"{BASE}/robots.txt", status=404)
    responses.get(f"{BASE}/arquivo.csv", body="a;b\n1;2")
    cliente.get(f"{BASE}/arquivo.csv")
    assert responses.calls[-1].request.headers["User-Agent"] == USER_AGENT
    assert "github.com/hcristosm/BELUGA" in USER_AGENT


@responses.activate
def test_robots_proibindo_bloqueia_sem_tocar_na_url(cliente):
    responses.get(f"{BASE}/robots.txt", body="User-agent: *\nDisallow: /api/\n")
    alvo = responses.get(f"{BASE}/api/3/action/package_show", json={})
    with pytest.raises(BloqueadoPorRobots):
        cliente.get(f"{BASE}/api/3/action/package_show")
    assert alvo.call_count == 0


@responses.activate
def test_robots_e_lido_uma_vez_por_host(cliente):
    robots = responses.get(f"{BASE}/robots.txt", status=404)
    responses.get(f"{BASE}/a", body="x")
    responses.get(f"{BASE}/b", body="y")
    cliente.get(f"{BASE}/a")
    cliente.get(f"{BASE}/b")
    assert robots.call_count == 1


@responses.activate
def test_robots_fora_do_ar_bloqueia_a_coleta(cliente):
    responses.get(f"{BASE}/robots.txt", status=503)
    with pytest.raises(ColetaError, match="robots.txt"):
        cliente.get(f"{BASE}/arquivo.csv")


@responses.activate
def test_robots_inacessivel_e_lembrado_por_host(cliente):
    robots = responses.get(f"{BASE}/robots.txt", status=503)
    with pytest.raises(ColetaError, match="não respondeu"):
        cliente.get(f"{BASE}/a")
    with pytest.raises(ColetaError, match="não respondeu"):
        cliente.get(f"{BASE}/b")
    assert robots.call_count == 2  # duas tentativas na primeira URL, nenhuma na segunda


@responses.activate
def test_excecao_explicita_segue_sem_robots_mas_respeita_proibicao():
    livre = Cliente(backoff=0.0, dormir=lambda _s: None, robots_inacessivel_bloqueia=False)
    responses.get(f"{BASE}/robots.txt", status=503)
    responses.get(f"{BASE}/a", body="ok")
    assert livre.get(f"{BASE}/a").text == "ok"

    responses.replace(responses.GET, f"{BASE}/robots.txt", body="User-agent: *\nDisallow: /\n")
    outro = Cliente(backoff=0.0, dormir=lambda _s: None, robots_inacessivel_bloqueia=False)
    with pytest.raises(BloqueadoPorRobots):
        outro.get(f"{BASE}/a")


@responses.activate
def test_crawl_delay_vira_intervalo_entre_requisicoes():
    esperas: list[float] = []
    agora = [100.0]
    cliente = Cliente(backoff=0.0, dormir=esperas.append, relogio=lambda: agora[0])
    responses.get(f"{BASE}/robots.txt", body="User-agent: *\nCrawl-Delay: 10\n")
    responses.get(f"{BASE}/a", body="x")
    cliente.get(f"{BASE}/a")
    cliente.get(f"{BASE}/a")
    assert esperas == [10.0]


@responses.activate
def test_intervalo_minimo_do_catalogo_vale_sem_crawl_delay():
    esperas: list[float] = []
    cliente = Cliente(backoff=0.0, dormir=esperas.append, relogio=lambda: 50.0)
    responses.get(f"{BASE}/robots.txt", status=404)
    responses.get(f"{BASE}/a", body="x")
    cliente.get(f"{BASE}/a", intervalo_minimo=2)
    cliente.get(f"{BASE}/a", intervalo_minimo=2)
    assert esperas == [2.0]


@responses.activate
def test_retenta_erro_transitorio(cliente):
    responses.get(f"{BASE}/robots.txt", status=404)
    responses.get(f"{BASE}/a", status=503)
    responses.get(f"{BASE}/a", body="ok")
    assert cliente.get(f"{BASE}/a").text == "ok"


@responses.activate
def test_404_falha_na_hora_sem_retentar(cliente):
    responses.get(f"{BASE}/robots.txt", status=404)
    alvo = responses.get(f"{BASE}/a", status=404)
    with pytest.raises(ColetaError, match="HTTP 404"):
        cliente.get(f"{BASE}/a")
    assert alvo.call_count == 1


@responses.activate
def test_erro_do_arcgis_com_http_200_e_retentado(cliente):
    responses.get(f"{BASE}/robots.txt", status=404)
    responses.get(f"{BASE}/q", json={"error": {"message": "Error performing query operation"}})
    responses.get(f"{BASE}/q", json={"count": 3})
    assert cliente.get_json(f"{BASE}/q") == {"count": 3}


@responses.activate
def test_desiste_depois_do_limite_de_tentativas(cliente):
    responses.get(f"{BASE}/robots.txt", status=404)
    responses.get(f"{BASE}/q", json={"error": {"message": "falhou"}})
    with pytest.raises(ColetaError, match="3 tentativas"):
        cliente.get_json(f"{BASE}/q")
