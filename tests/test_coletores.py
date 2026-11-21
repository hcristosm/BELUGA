from __future__ import annotations

import json

import pytest
import responses
from responses import matchers

from src.coleta import arcgis_rest, arquivo
from src.coleta.http import ColetaError

BASE = "https://geo.exemplo.gov.br"
CAMADA = f"{BASE}/arcgis/rest/services/risco/MapServer/0"


def _feicao(oid: int) -> dict:
    return {"type": "Feature", "id": oid, "properties": {"OBJECTID": oid},
            "geometry": {"type": "Point", "coordinates": [-43.3, -21.7]}}


def _meta(max_registros: int = 2) -> dict:
    return {"objectIdField": "OBJECTID", "maxRecordCount": max_registros, "capabilities": "Map,Query,Data",
            "extent": {"spatialReference": {"wkid": 31983, "latestWkid": 31983}}}


def _preparar(total: int, paginas: list[list[int]]) -> None:
    responses.get(f"{BASE}/robots.txt", status=404)
    responses.get(CAMADA, json=_meta())
    responses.get(f"{CAMADA}/query", json={"count": total},
                  match=[matchers.query_param_matcher({"returnCountOnly": "true"}, strict_match=False)])
    for i, oids in enumerate(paginas):
        responses.get(
            f"{CAMADA}/query",
            json={"type": "FeatureCollection", "features": [_feicao(o) for o in oids]},
            match=[matchers.query_param_matcher(
                {"resultOffset": str(sum(len(p) for p in paginas[:i])), "orderByFields": "OBJECTID",
                 "outSR": "4326", "f": "geojson"}, strict_match=False)],
        )


@responses.activate
def test_arcgis_pagina_com_ordem_estavel(cliente):
    _preparar(3, [[1, 2], [3]])
    colecao, meta = arcgis_rest.coletar_camada(cliente, CAMADA, intervalo_minimo=0)
    assert [f["id"] for f in colecao["features"]] == [1, 2, 3]
    assert arcgis_rest.crs_da_camada(meta) == "EPSG:31983"


@responses.activate
def test_arcgis_paginacao_truncada_e_erro(cliente):
    _preparar(3, [[1, 2], []])
    with pytest.raises(ColetaError, match="truncada"):
        arcgis_rest.coletar_camada(cliente, CAMADA, intervalo_minimo=0)


@responses.activate
def test_arcgis_camada_vazia_e_erro(cliente):
    _preparar(0, [])
    with pytest.raises(ColetaError, match="vazia"):
        arcgis_rest.coletar_camada(cliente, CAMADA, intervalo_minimo=0)


@responses.activate
def test_arcgis_objectid_repetido_entre_paginas_e_erro(cliente):
    _preparar(4, [[1, 2], [2, 3]])
    with pytest.raises(ColetaError, match="repetido"):
        arcgis_rest.coletar_camada(cliente, CAMADA, intervalo_minimo=0)


@responses.activate
def test_arcgis_filtra_por_where(cliente):
    _preparar(1, [[7]])
    arcgis_rest.coletar_camada(cliente, CAMADA, where="uf='MG'", intervalo_minimo=0)
    assert all("uf%3D%27MG%27" in c.request.url for c in responses.calls if "/query" in c.request.url)


URL_ARQUIVO = "https://dados.exemplo.gov.br/recurso/setores.geojson"


@responses.activate
def test_arquivo_recusa_pagina_html_com_http_200(cliente):
    responses.get("https://dados.exemplo.gov.br/robots.txt", status=404)
    responses.get(URL_ARQUIVO, body="<!doctype html><html><title>Redirecting...</title></html>")
    with pytest.raises(ColetaError, match="HTML"):
        arquivo.baixar(cliente, URL_ARQUIVO, "geojson")


@responses.activate
def test_arquivo_geojson_sem_feicoes_e_erro(cliente):
    responses.get("https://dados.exemplo.gov.br/robots.txt", status=404)
    responses.get(URL_ARQUIVO, json={"type": "FeatureCollection", "features": []})
    with pytest.raises(ColetaError, match="sem feições"):
        arquivo.baixar(cliente, URL_ARQUIVO, "geojson")


@responses.activate
def test_arquivo_geojson_valido(cliente):
    responses.get("https://dados.exemplo.gov.br/robots.txt", status=404)
    corpo = {"type": "FeatureCollection", "features": [_feicao(1)]}
    responses.get(URL_ARQUIVO, json=corpo)
    assert json.loads(arquivo.baixar(cliente, URL_ARQUIVO, "geojson")) == corpo


def test_csv_sem_separador_declarado_e_erro():
    with pytest.raises(ColetaError, match="separador"):
        arquivo.conferir_conteudo(b"a,b\n1,2", "csv_wkt", {"separador": ";"})
