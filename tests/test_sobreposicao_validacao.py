from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, box

from src.cprm.sobreposicao import marcar_sobreposicao
from src.normalizacao.esquema import COLUNAS
from src.validacao import validar
from tests.conftest import LAT, LON, ponto, quadrado


def _setor(num: str, fonte: str, geom, **extra) -> dict:
    base = dict.fromkeys(COLUNAS)
    base.update({"num_setor": num, "bl_fonte": fonte, "uf": "MG", "cd_geocmu": "3136702",
                 "grau_risco": "Alto", "geometry": geom})
    base.update(extra)
    return base


def _gdf(setores: list[dict]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(setores, geometry="geometry", crs="EPSG:4326")


CPRM = "br-sgb-setorizacao"


def test_marca_sobreposicao_sem_descartar():
    setores = _gdf([
        _setor("MG_A_CPRM", CPRM, quadrado(lado=0.02)),
        _setor("MG_PJF_1_BELUGA", "mg-pjf", quadrado(0.005, 0.005, 0.005)),   # dentro
        _setor("MG_PJF_2_BELUGA", "mg-pjf", quadrado(0.015, 0.0, 0.01)),      # metade fora
        _setor("MG_PJF_3_BELUGA", "mg-pjf", quadrado(0.1, 0.1)),              # longe
        _setor("MG_PJF_4_BELUGA", "mg-pjf", quadrado(0.02, 0.0)),             # só encosta a borda
        _setor("MG_PJF_6_BELUGA", "mg-pjf", quadrado(0.01995, 0.0)),          # faixa de 0,5% na borda
        _setor("PE_PCR_5_BELUGA", "pe-pcr", ponto()),                         # ponto dentro
    ])
    r = marcar_sobreposicao(setores).set_index("num_setor")
    assert len(r) == 7
    assert r.loc["MG_PJF_1_BELUGA", "bl_sob_cp"] is True
    assert r.loc["MG_PJF_1_BELUGA", "bl_cp_frac"] == pytest.approx(1.0)
    assert r.loc["MG_PJF_1_BELUGA", "bl_cp_set"] == "MG_A_CPRM"
    assert r.loc["MG_PJF_2_BELUGA", "bl_cp_frac"] == pytest.approx(0.5, abs=0.02)
    assert r.loc["MG_PJF_3_BELUGA", "bl_sob_cp"] is False
    assert r.loc["MG_PJF_4_BELUGA", "bl_sob_cp"] is False
    assert r.loc["MG_PJF_6_BELUGA", "bl_sob_cp"] is False  # abaixo de FRACAO_MINIMA
    assert 0 < r.loc["MG_PJF_6_BELUGA", "bl_cp_frac"] < 0.01
    assert r.loc["PE_PCR_5_BELUGA", "bl_sob_cp"] is True
    assert r.loc["PE_PCR_5_BELUGA", "bl_cp_frac"] is None
    assert r.loc["MG_A_CPRM", "bl_sob_cp"] is None  # não se aplica à própria CPRM


def test_validacao_separa_erro_de_aviso():
    gravata = Polygon([(LON, LAT), (LON + 0.01, LAT + 0.01), (LON + 0.01, LAT), (LON, LAT + 0.01)])
    setores = _gdf([
        _setor("OK", "f", quadrado()),
        _setor("REPARADO", "f", gravata),
        _setor("VAZIO", "f", Polygon()),
        _setor("OK", "f", quadrado(0.02)),                     # num_setor repetido
        _setor("FORA_BR", "f", box(10, 10, 11, 11)),
        _setor("GRAU", "f", quadrado(0.04), grau_risco="Altíssimo"),
        _setor("SEM_CD", "f", quadrado(0.06), cd_geocmu=None),
    ])
    publicaveis, rel = validar(setores)
    assert sorted(publicaveis["num_setor"]) == ["OK", "REPARADO", "SEM_CD"]
    assert publicaveis.set_index("num_setor").loc["REPARADO"].geometry.is_valid
    d = rel.como_dict()["por_fonte"]["f"]
    assert d["entrada"] == 7 and d["publicados"] == 3
    assert d["erros"] == {"geometria vazia": 1, "num_setor repetido": 1,
                          "geometria fora do Brasil": 1, "grau fora do vocabulário": 1}
    assert d["avisos"]["sem código IBGE do município"] == 1
    assert "teste de município pulado" in rel.como_dict()["avisos_globais"][0]


def test_validacao_confere_municipio_com_tolerancia():
    juiz_de_fora = box(LON - 0.05, LAT - 0.05, LON + 0.05, LAT + 0.05)
    malhas = gpd.GeoDataFrame({"cd_ibge": ["3136702"]}, geometry=[juiz_de_fora], crs="EPSG:4326")
    setores = _gdf([
        _setor("DENTRO", "f", quadrado()),
        _setor("BORDA", "f", box(LON + 0.0502, LAT, LON + 0.0505, LAT + 0.001)),  # ~25 m fora
        _setor("LONGE", "f", quadrado(0.2)),
    ])
    publicaveis, rel = validar(setores, malhas)
    assert len(publicaveis) == 3  # aviso não tira da publicação
    assert rel.como_dict()["por_fonte"]["f"]["avisos"] == {"fora do município declarado": 1}
    assert rel.como_dict()["por_fonte"]["f"]["exemplos"]["fora do município declarado"] == ["LONGE"]


def test_validacao_recusa_crs_errado():
    setores = _gdf([_setor("A", "f", quadrado())]).to_crs("EPSG:31983")
    with pytest.raises(ValueError, match="EPSG:4326"):
        validar(setores)
