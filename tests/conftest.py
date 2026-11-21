from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from src.catalogo import Fonte
from src.coleta.http import Cliente

# Um quadrado de ~1 km em Juiz de Fora (MG), dentro do município.
LON, LAT = -43.35, -21.76


def quadrado(dx: float = 0.0, dy: float = 0.0, lado: float = 0.01):
    return box(LON + dx, LAT + dy, LON + dx + lado, LAT + dy + lado)


def ponto(dx: float = 0.005, dy: float = 0.005) -> Point:
    return Point(LON + dx, LAT + dy)


FONTE_BASE: dict[str, Any] = {
    "id": "mg-teste-municipal",
    "sigla": "TST",
    "nome": "Fonte de teste",
    "orgao": "Defesa Civil de Teste",
    "esfera": "municipal",
    "abrangencia": {"uf": "MG", "municipios": [{"nome": "Juiz de Fora", "cd_ibge": "3136702"}]},
    "produto": "setorizacao_risco",
    "tipologias": ["Deslizamento"],
    "acesso": {"tipo": "arquivo", "url": "https://dados.exemplo.gov.br/setores.geojson",
               "formato": "geojson", "crs_origem": "EPSG:4326"},
    "licenca": {"nome": "CC-BY"},
    "ultima_verificacao": "2026-11-21",
    "status": "ativa",
    "coletor": "arquivo",
    "intervalo_minimo_s": 0,
    "mapeamento": {
        "id_original": "ID",
        "grau": {"campo": "RISCO", "valores": {"R4": "Muito alto", "R3": "Alto", "R2": "Médio",
                                                "R1": "Baixo", "Sem dado": None}},
        "tipologia": {"campo": "PROCESSO", "valores": {
            "Escorregamento Planar": [["Deslizamento", "Deslizamento planar"]],
            "Planar e Queda": [["Deslizamento", "Deslizamento planar"], ["Queda", None]],
        }},
        "campos": {"local": "{BAIRRO}", "descricao": "Setor {NOME}. Origem: {ORIGEM}"},
    },
}

FONTE_CPRM: dict[str, Any] = {
    "id": "br-sgb-setorizacao",
    "sigla": "CPRM",
    "nome": "Setorização CPRM",
    "orgao": "Serviço Geológico do Brasil (SGB/CPRM)",
    "esfera": "federal",
    "abrangencia": {"uf": "BR", "nacional": True},
    "produto": "setorizacao_risco",
    "tipologias": ["Deslizamento"],
    "acesso": {"tipo": "arcgis_rest", "url": "https://geo.exemplo.gov.br/arcgis/rest/services/risco/FeatureServer/0",
               "formato": "geojson", "crs_origem": "EPSG:3857",
               "parametros": {"particionar_por_uf": True, "campo_uf": "uf"}},
    "licenca": {"nome": "não declarada"},
    "ultima_verificacao": "2026-11-21",
    "status": "ativa",
    "coletor": "arcgis_rest",
    "intervalo_minimo_s": 0,
    "mapeamento": {
        "id_original": "objectid",
        "num_setor": {"campo": "num_setor"},
        "uf": {"campo": "uf"},
        "municipio": {"campo": "municipio", "remover_sufixo_uf": True},
        "grau": {"campo": "grau_risco"},
        "data_setor": {"campo": "data_setor"},
        "tipologia": {"copiar_colunas_cprm": True},
        "copiar": ["local", "descricao", "num_pess", "orgao_exec"],
    },
}


def fazer_fonte(base: dict[str, Any] = FONTE_BASE, **mudancas: Any) -> Fonte:
    dados = copy.deepcopy(base)
    dados.update(mudancas)
    return Fonte(dados, Path(f"{dados['id']}.yaml"))


@pytest.fixture
def fonte() -> Fonte:
    return fazer_fonte()


@pytest.fixture
def fonte_cprm() -> Fonte:
    return fazer_fonte(FONTE_CPRM)


@pytest.fixture
def cliente() -> Cliente:
    return Cliente(max_tentativas=3, backoff=0.0, dormir=lambda _s: None)


def gdf(registros: list[dict[str, Any]], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    geoms = [r.pop("geometry") for r in registros]
    return gpd.GeoDataFrame(registros, geometry=geoms, crs=crs)
