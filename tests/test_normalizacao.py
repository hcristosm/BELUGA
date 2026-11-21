from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import Polygon

from src.normalizacao.esquema import COLUNAS
from src.normalizacao.leitura import LeituraError, ler_bruto
from src.normalizacao.mapeamento import Proveniencia, chave_nome, normalizar
from tests.conftest import FONTE_BASE, fazer_fonte, gdf, ponto, quadrado

PROV = Proveniencia("2026-11-21T10:00:00+00:00", "a" * 64, "EPSG:31983")


def _registro(**extra):
    base = {"ID": 1, "RISCO": "R3", "PROCESSO": "Escorregamento Planar", "BAIRRO": "Centenário",
            "NOME": "C_21", "ORIGEM": "SSPDC (2025)", "geometry": quadrado()}
    base.update(extra)
    return base


def test_normaliza_fonte_municipal(fonte):
    r = normalizar(gdf([_registro()]), fonte, PROV)
    s = r.setores.iloc[0]
    assert list(r.setores.columns) == [*COLUNAS, "geometry"]
    assert s["num_setor"] == "MG_TST_1_BELUGA"
    assert (s["uf"], s["munic"], s["cd_geocmu"]) == ("MG", "JUIZ DE FORA", "3136702")
    assert (s["grau_risco"], s["bl_grau_or"]) == ("Alto", "R3")
    assert (s["tipolo_g1"], s["tipolo_e1"], s["tipolo_g2"]) == ("Deslizamento", "Deslizamento planar", None)
    assert s["bl_tipo_or"] == "Escorregamento Planar"
    assert s["local"] == "Centenário"
    assert s["descricao"] == "Setor C_21. Origem: SSPDC (2025)"
    assert s["orgao_exec"] == "Defesa Civil de Teste"
    assert (s["bl_fonte"], s["bl_sha256"], s["bl_crs_or"]) == ("mg-teste-municipal", "a" * 64, "EPSG:31983")
    assert s["bl_geom_or"] == "Polygon"
    assert not r.avisos


def test_varios_pares_de_tipologia(fonte):
    s = normalizar(gdf([_registro(PROCESSO="Planar e Queda")]), fonte, PROV).setores.iloc[0]
    assert (s["tipolo_g1"], s["tipolo_g2"], s["tipolo_e2"]) == ("Deslizamento", "Queda", None)


def test_valor_desconhecido_vira_nulo_e_aviso_sem_inventar(fonte):
    r = normalizar(gdf([_registro(RISCO="R9", PROCESSO="Avalanche")]), fonte, PROV)
    s = r.setores.iloc[0]
    assert s["grau_risco"] is None and s["bl_grau_or"] == "R9"
    assert s["tipolo_g1"] is None and s["bl_tipo_or"] == "Avalanche"
    assert r.avisos["grau sem correspondência: 'R9'"] == 1
    assert r.avisos["tipologia sem correspondência: 'Avalanche'"] == 1


def test_valor_listado_como_nulo_nao_gera_aviso(fonte):
    r = normalizar(gdf([_registro(RISCO="Sem dado")]), fonte, PROV)
    assert r.setores.iloc[0]["grau_risco"] is None
    assert not r.avisos


def test_vazio_e_espaco_viram_nulo_e_nao_texto_nan(fonte):
    """pandas 3 infere `str` e troca None por NaN; 'nan' não pode virar valor."""
    registros = [_registro(ID=1, RISCO=" ", PROCESSO=None), _registro(ID=2, RISCO=np.nan, BAIRRO="")]
    r = normalizar(gdf(registros), fonte, PROV)
    assert r.setores["grau_risco"].tolist() == [None, None]
    assert r.setores["bl_grau_or"].tolist() == [None, None]
    assert r.setores.iloc[1]["local"] is None
    assert not r.avisos


def test_modelo_com_todas_as_colunas_vazias_vira_nulo(fonte):
    s = normalizar(gdf([_registro(NOME=" ", ORIGEM=None)]), fonte, PROV).setores.iloc[0]
    assert s["descricao"] is None


def test_id_gerado_e_estavel(fonte):
    mapa = dict(FONTE_BASE["mapeamento"], id_original={"gerar_de": ["BAIRRO", "NOME"]})
    f = fazer_fonte(mapeamento=mapa)
    a = normalizar(gdf([_registro()]), f, PROV).setores.iloc[0]["bl_id_orig"]
    b = normalizar(gdf([_registro(RISCO="R1")]), f, PROV).setores.iloc[0]["bl_id_orig"]
    c = normalizar(gdf([_registro(NOME="C_22")]), f, PROV).setores.iloc[0]["bl_id_orig"]
    assert a == b and a != c and len(a) == 12


def test_geometria_invalida_e_reparada(fonte):
    gravata = Polygon([(-43.35, -21.76), (-43.34, -21.75), (-43.34, -21.76), (-43.35, -21.75)])
    s = normalizar(gdf([_registro(geometry=gravata)]), fonte, PROV).setores.iloc[0]
    assert s.geometry.is_valid


def _cprm(**extra):
    base = {"objectid": 3741, "uf": "MG", "municipio": "JUIZ DE FORA (MG)", "num_setor": "MG_JF_SR_01_CPRM",
            "data_setor": "2017-05-02", "grau_risco": "Muito Alto", "tipolo_g1": "Deslizamento",
            "tipolo_e1": " ", "cobrade_01": "1.1.3.2.1", "local": "Vila X", "descricao": "Encosta",
            "num_pess": "350", "orgao_exec": "Serviço Geológico do Brasil", "geometry": quadrado()}
    base.update(extra)
    return base


def test_normaliza_cprm_no_esquema_do_orca(fonte_cprm):
    s = normalizar(gdf([_cprm()]), fonte_cprm, PROV).setores.iloc[0]
    assert s["num_setor"] == "MG_JF_SR_01_CPRM"  # código da CPRM preservado
    assert s["munic"] == "JUIZ DE FORA"  # sem o sufixo "(MG)" que a SGB passou a usar
    assert s["cd_geocmu"] == "3136702"
    assert s["grau_risco"] == "Muito alto"  # caixa normalizada pelo vocabulário
    assert (s["tipolo_g1"], s["tipolo_e1"], s["cobrade_01"]) == ("Deslizamento", None, "1.1.3.2.1")
    assert s["data_setor"] == "2017-05-02"
    assert s["num_pess"] == 350
    assert s["bl_id_orig"] == "3741"


def test_cprm_data_em_milissegundos(fonte_cprm):
    s = normalizar(gdf([_cprm(data_setor=1485907200000)]), fonte_cprm, PROV).setores.iloc[0]
    assert s["data_setor"] == "2017-02-01"


def test_cprm_alias_de_municipio(fonte_cprm):
    r = normalizar(gdf([_cprm(municipio="BARÃO DE MONTE ALTO (MG)")]), fonte_cprm, PROV)
    assert r.setores.iloc[0]["cd_geocmu"] == "3105509"
    assert not r.avisos


def test_cprm_municipio_desconhecido_e_aviso(fonte_cprm):
    r = normalizar(gdf([_cprm(municipio="CIDADE INEXISTENTE (MG)")]), fonte_cprm, PROV)
    assert r.setores.iloc[0]["cd_geocmu"] is None
    assert sum(r.avisos.values()) == 1


def test_chave_nome_ignora_acento_caixa_e_pontuacao():
    assert chave_nome("Santa Bárbara d'Oeste") == chave_nome("SANTA BARBARA D OESTE")


def test_le_csv_wkt_e_reprojeta():
    # Ponto em UTM 23S (SIRGAS 2000) perto de Belo Horizonte.
    csv = b"ID_ARG;RISCO_GEOLOGICO;GEOMETRIA\n1;RISCO;POINT (611000 7797000)\n"
    lido = ler_bruto(csv, "csv_wkt", {"separador": ";", "coluna_geometria": "GEOMETRIA"}, "EPSG:31983")
    assert lido.crs.to_string() == "EPSG:4326"
    x, y = lido.geometry.iloc[0].x, lido.geometry.iloc[0].y
    assert -44.0 < x < -43.9 and -20.0 < y < -19.9


def test_csv_wkt_sem_coluna_de_geometria():
    with pytest.raises(LeituraError, match="coluna de geometria"):
        ler_bruto(b"a;b\n1;2\n", "csv_wkt", {"separador": ";", "coluna_geometria": "WKT"}, "EPSG:31983")


def test_le_geojson_de_pontos():
    corpo = b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"a":1},' \
            b'"geometry":{"type":"Point","coordinates":[-34.95,-8.12]}}]}'
    lido = ler_bruto(corpo, "geojson")
    assert lido.geometry.iloc[0].equals(ponto(-34.95 + 43.35, -8.12 + 21.76))


def test_partes_do_mesmo_setor_viram_uma_geometria(fonte_cprm):
    registros = [_cprm(objectid=1, geometry=quadrado()), _cprm(objectid=2, geometry=quadrado(0.02))]
    r = normalizar(gdf(registros), fonte_cprm, PROV)
    assert len(r.setores) == 1
    s = r.setores.iloc[0]
    assert s["num_setor"] == s["bl_num_or"] == "MG_JF_SR_01_CPRM"
    assert s["bl_id_orig"] == "1,2"
    assert s.geometry.geom_type == "MultiPolygon"


def test_codigo_repetido_em_setores_diferentes_ganha_sufixo(fonte_cprm):
    registros = [
        _cprm(objectid=9915, municipio="CAMPESTRE (AL)", uf="AL", num_setor="AL_CA_SR_01_CPRM"),
        _cprm(objectid=9926, municipio="CAJUEIRO (AL)", uf="AL", num_setor="AL_CA_SR_01_CPRM"),
    ]
    r = normalizar(gdf(registros), fonte_cprm, PROV)
    assert sorted(r.setores["num_setor"]) == ["AL_CA_SR_01_CPRM_9915", "AL_CA_SR_01_CPRM_9926"]
    assert set(r.setores["bl_num_or"]) == {"AL_CA_SR_01_CPRM"}
    assert r.setores["num_setor"].is_unique


def test_linhas_identicas_na_fonte_viram_uma(fonte):
    mapa = dict(FONTE_BASE["mapeamento"], id_original={"gerar_de": ["BAIRRO", "NOME"]})
    f = fazer_fonte(mapeamento=mapa)
    r = normalizar(gdf([_registro(geometry=ponto()), _registro(geometry=ponto())]), f, PROV)
    assert len(r.setores) == 1 and r.setores.iloc[0].geometry.geom_type == "Point"


REGRAS_TEXTO = [
    {"padrao": r"escorreg|desliz", "tipologia": ["Deslizamento", None]},
    {"padrao": r"solapamento", "tipologia": ["Erosão", "Erosão de margem fluvial"]},
    {"padrao": r"inunda", "tipologia": ["Inundação", None]},
    {"padrao": r"eros", "tipologia": ["Erosão", None]},
]


def test_tipologia_por_palavra_chave_em_texto_livre(fonte):
    mapa = dict(FONTE_BASE["mapeamento"], tipologia={"campo": "PROCESSO", "palavras_chave": REGRAS_TEXTO})
    f = fazer_fonte(mapeamento=mapa)
    texto = "Escorregamento de talude de corte, erosão e solapamento da margem; inundação das moradias"
    r = normalizar(gdf([_registro(PROCESSO=texto)]), f, PROV)
    s = r.setores.iloc[0]
    # Na ordem das regras; "Erosão" entra uma vez só, pela primeira regra que casou.
    assert (s["tipolo_g1"], s["tipolo_g2"], s["tipolo_e2"], s["tipolo_g3"], s["tipolo_g4"]) == (
        "Deslizamento", "Erosão", "Erosão de margem fluvial", "Inundação", None)
    assert s["bl_tipo_or"] == texto
    assert not r.avisos


def test_texto_sem_palavra_chave_vira_um_aviso_agregado(fonte):
    mapa = dict(FONTE_BASE["mapeamento"], tipologia={"campo": "PROCESSO", "palavras_chave": REGRAS_TEXTO})
    f = fazer_fonte(mapeamento=mapa)
    registros = [_registro(ID=1, PROCESSO="Não foram observadas evidências de movimentação"),
                 _registro(ID=2, PROCESSO="Muro atua como barramento da drenagem")]
    r = normalizar(gdf(registros), f, PROV)
    assert r.setores["tipolo_g1"].tolist() == [None, None]
    assert r.avisos == {"tipologia sem palavra-chave reconhecida": 2}
