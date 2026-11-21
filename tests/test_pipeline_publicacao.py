from __future__ import annotations

import hashlib
import json
import zipfile

import pytest
import responses
from responses import matchers

from src.config import caminho_proveniencia, dir_bruto, dir_shapefiles
from src.export.publicacao import ExportacaoError, exportar
from src.pipeline import coletar_fonte, ler_normalizado
from tests.conftest import FONTE_BASE, LAT, LON, fazer_fonte

URL = FONTE_BASE["acesso"]["url"]


def _colecao(n: int, risco: str = "R3", ponto: bool = False) -> dict:
    feicoes = []
    for i in range(1, n + 1):
        x = LON + i * 0.001
        geom = (
            {"type": "Point", "coordinates": [x, LAT]} if ponto else
            {"type": "Polygon", "coordinates": [[[x, LAT], [x + 0.0005, LAT], [x + 0.0005, LAT + 0.0005],
                                                 [x, LAT + 0.0005], [x, LAT]]]}
        )
        feicoes.append({"type": "Feature", "geometry": geom, "properties": {
            "ID": i, "RISCO": risco, "PROCESSO": "Escorregamento Planar", "BAIRRO": "B", "NOME": f"S{i}",
            "ORIGEM": "SSPDC"}})
    return {"type": "FeatureCollection", "features": feicoes}


def _servir(colecao: dict) -> None:
    responses.get("https://dados.exemplo.gov.br/robots.txt", status=404)
    responses.get(URL, json=colecao)


@responses.activate
def test_coleta_grava_bruto_normalizado_e_proveniencia(tmp_path, fonte, cliente):
    _servir(_colecao(3))
    [r] = coletar_fonte(fonte, cliente, tmp_path)
    assert r.ok and r.setores == 3

    bruto = dir_bruto(fonte.id, tmp_path) / "completo.geojson"
    meta = json.loads((dir_bruto(fonte.id, tmp_path) / "completo.json").read_text())
    assert meta["sha256"] == hashlib.sha256(bruto.read_bytes()).hexdigest()

    normal = ler_normalizado(fonte.id, tmp_path)
    assert len(normal) == 3 and set(normal["bl_sha256"]) == {meta["sha256"]}
    prov = json.loads(caminho_proveniencia(fonte.id, tmp_path).read_text())
    assert prov["particoes"]["completo"]["setores"] == 3


@responses.activate
def test_renormaliza_do_bruto_sem_rede(tmp_path, fonte, cliente):
    _servir(_colecao(3))
    coletar_fonte(fonte, cliente, tmp_path)
    chamadas = len(responses.calls)
    [r] = coletar_fonte(fonte, cliente, tmp_path, do_bruto=True)
    assert r.ok and r.setores == 3
    assert len(responses.calls) == chamadas


def test_renormalizar_recusa_bruto_adulterado(tmp_path, fonte, cliente):
    destino = dir_bruto(fonte.id, tmp_path)
    destino.mkdir(parents=True)
    (destino / "completo.geojson").write_text(json.dumps(_colecao(1)))
    (destino / "completo.json").write_text(json.dumps({"sha256": "0" * 64, "coletado_em": "x"}))
    [r] = coletar_fonte(fonte, cliente, tmp_path, do_bruto=True)
    assert not r.ok and "sha256" in r.mensagem


@responses.activate
def test_queda_grande_e_recusada_e_mantem_o_anterior(tmp_path, fonte, cliente):
    _servir(_colecao(20))
    coletar_fonte(fonte, cliente, tmp_path)
    responses.replace(responses.GET, URL, json=_colecao(10))
    [r] = coletar_fonte(fonte, cliente, tmp_path)
    assert not r.ok and "recusado" in r.mensagem
    assert len(ler_normalizado(fonte.id, tmp_path)) == 20

    [r] = coletar_fonte(fonte, cliente, tmp_path, aceitar_queda=True)
    assert r.ok and len(ler_normalizado(fonte.id, tmp_path)) == 10


@responses.activate
def test_fonte_fora_do_ar_nao_apaga_o_normalizado(tmp_path, fonte, cliente):
    _servir(_colecao(5))
    coletar_fonte(fonte, cliente, tmp_path)
    responses.replace(responses.GET, URL, body="<!doctype html><html>manutenção</html>")
    [r] = coletar_fonte(fonte, cliente, tmp_path)
    assert not r.ok and "HTML" in r.mensagem
    assert len(ler_normalizado(fonte.id, tmp_path)) == 5


CAMADA = "https://geo.exemplo.gov.br/arcgis/rest/services/risco/FeatureServer/0"


def _servir_cprm(por_uf: dict[str, int]) -> None:
    responses.get("https://geo.exemplo.gov.br/robots.txt", status=404)
    responses.get(CAMADA, json={"objectIdField": "objectid", "maxRecordCount": 2000,
                                "extent": {"spatialReference": {"wkid": 102100, "latestWkid": 3857}}})
    for uf, n in por_uf.items():
        where = {"where": f"uf='{uf}'"}
        responses.get(f"{CAMADA}/query", json={"count": n}, match=[
            matchers.query_param_matcher(where | {"returnCountOnly": "true"}, strict_match=False)])
        feicoes = [{"type": "Feature", "id": i, "properties": {
            "objectid": i, "uf": uf, "municipio": "JUIZ DE FORA (MG)" if uf == "MG" else "RECIFE (PE)",
            "num_setor": f"{uf}_X_SR_{i}_CPRM", "grau_risco": "Alto", "data_setor": "2020-01-01"},
            "geometry": {"type": "Point", "coordinates": [LON, LAT]}} for i in range(1, n + 1)]
        responses.get(f"{CAMADA}/query", json={"type": "FeatureCollection", "features": feicoes}, match=[
            matchers.query_param_matcher(where | {"f": "geojson"}, strict_match=False)])


@responses.activate
def test_fonte_por_uf_so_substitui_as_ufs_coletadas(tmp_path, fonte_cprm, cliente):
    _servir_cprm({"MG": 3, "PE": 2})
    resultados = coletar_fonte(fonte_cprm, cliente, tmp_path, ufs=["MG", "PE"])
    assert [r.ok for r in resultados] == [True, True]
    assert (dir_bruto(fonte_cprm.id, tmp_path) / "mg.geojson").exists()

    responses.reset()
    _servir_cprm({"MG": 4})
    coletar_fonte(fonte_cprm, cliente, tmp_path, ufs=["MG"])
    normal = ler_normalizado(fonte_cprm.id, tmp_path)
    assert normal["uf"].value_counts().to_dict() == {"MG": 4, "PE": 2}


@responses.activate
def test_exporta_geojson_manifest_e_shapefile(tmp_path, fonte, fonte_cprm, cliente):
    _servir(_colecao(3))
    coletar_fonte(fonte, cliente, tmp_path)
    responses.reset()
    _servir_cprm({"MG": 2})
    coletar_fonte(fonte_cprm, cliente, tmp_path, ufs=["MG"])
    pontos = fazer_fonte(id="pe-pontos", sigla="PTS", abrangencia={
        "uf": "PE", "municipios": [{"nome": "Recife", "cd_ibge": "2611606"}]})
    responses.reset()
    _servir(_colecao(2, ponto=True))
    coletar_fonte(pontos, cliente, tmp_path)
    espelho = fazer_fonte(id="mg-espelho", sigla="ESP", publicar=False)

    saida = tmp_path / "v1"
    manifesto = exportar([fonte, fonte_cprm, pontos, espelho], tmp_path, saida)

    assert manifesto["contrato"] == "v1"
    assert manifesto["total_setores"] == 7
    assert set(manifesto["ufs"]) == {"mg", "pe"}
    mg = manifesto["ufs"]["mg"]
    arquivo = saida / mg["arquivo"]
    assert mg["sha256"] == hashlib.sha256(arquivo.read_bytes()).hexdigest()
    assert mg["por_fonte"] == {"br-sgb-setorizacao": 2, "mg-teste-municipal": 3}
    dados = json.loads(arquivo.read_text())
    nums = [f["properties"]["num_setor"] for f in dados["features"]]
    assert nums == sorted(nums)
    props = dados["features"][0]["properties"]
    assert set(props) >= {"num_setor", "munic", "grau_risco", "bl_fonte", "bl_sob_cp"}
    # Tipos de verdade no GeoJSON, não texto: o ORCA lê `bl_sob_cp is True`.
    externos = [f["properties"] for f in dados["features"] if f["properties"]["bl_fonte"] != "br-sgb-setorizacao"]
    assert all(isinstance(p["bl_sob_cp"], bool) for p in externos)
    cprm = [f["properties"] for f in dados["features"] if f["properties"]["bl_fonte"] == "br-sgb-setorizacao"]
    assert all(p["bl_sob_cp"] is None for p in cprm)

    fontes = {f["id"]: f for f in manifesto["fontes"]}
    assert fontes["mg-espelho"]["setores_publicados"] == 0 and not fontes["mg-espelho"]["publicada"]
    assert (saida / "relatorio_validacao.json").exists()

    with zipfile.ZipFile(dir_shapefiles(tmp_path) / "setores_pe.zip") as zf:
        assert "setores_pe_pontos.shp" in zf.namelist()
    with zipfile.ZipFile(dir_shapefiles(tmp_path) / "setores_mg.zip") as zf:
        nomes = zf.namelist()
        assert "setores_mg_poligonos.shp" in nomes and "setores_mg_pontos.shp" in nomes
        assert "setores_mg_poligonos.prj" in nomes


def test_exportar_sem_normalizado_e_erro(tmp_path, fonte):
    with pytest.raises(ExportacaoError):
        exportar([fonte], tmp_path, tmp_path / "v1")


@responses.activate
def test_exportar_remove_uf_que_sumiu(tmp_path, fonte, cliente):
    """Arquivo de UF fora do manifest não pode ficar servindo dado velho."""
    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    saida = tmp_path / "v1"
    saida.mkdir()
    (saida / "setores_sp.geojson").write_text("{}")
    manifesto = exportar([fonte], tmp_path, saida, shapefiles=False)
    assert not (saida / "setores_sp.geojson").exists()
    assert sorted(p.name for p in saida.glob("setores_*.geojson")) == ["setores_mg.geojson"]
    assert set(manifesto["ufs"]) == {"mg"}


@responses.activate
def test_unir_partes_de_setor_nao_dispara_a_guarda_de_queda(tmp_path, fonte, cliente):
    """A guarda compara feições recebidas, não setores depois da união."""
    _servir(_colecao(20))
    coletar_fonte(fonte, cliente, tmp_path)
    multipartes = _colecao(20)
    for i, feicao in enumerate(multipartes["features"]):
        feicao["properties"].update(ID=i // 2, NOME=f"S{i // 2}")  # 10 setores de 2 partes
    responses.replace(responses.GET, URL, json=multipartes)
    [r] = coletar_fonte(fonte, cliente, tmp_path)
    assert r.ok and r.setores == 10
    prov = json.loads(caminho_proveniencia(fonte.id, tmp_path).read_text())
    assert prov["particoes"]["completo"]["feicoes"] == 20
