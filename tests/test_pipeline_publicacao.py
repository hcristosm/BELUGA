from __future__ import annotations

import hashlib
import json
import zipfile

import pytest
import responses
from responses import matchers

from src.config import (
    caminho_csv_nacional,
    caminho_gpkg_nacional,
    caminho_parquet_nacional,
    caminho_pmtiles,
    caminho_proveniencia,
    dir_bruto,
    dir_shapefiles,
)
from src.export.publicacao import (
    ExportacaoError,
    centroides_do_csv,
    exportar,
)
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
    manifesto = exportar([fonte, fonte_cprm, pontos, espelho], tmp_path, saida, pmtiles=False)

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
    manifesto = exportar([fonte], tmp_path, saida, shapefiles=False, agregados=False, pmtiles=False)
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


# ---------------------------------------------------------------------------
# Formatos agregados (GeoPackage, GeoParquet, CSV e PMTiles)
# ---------------------------------------------------------------------------


@responses.activate
def test_agregados_nacionais_tem_todos_os_setores_e_sha256_no_manifest(
    tmp_path, fonte, fonte_cprm, cliente,
):
    """GPKG, Parquet e CSV cobrem o país inteiro, e o manifest descreve cada um."""
    import geopandas as gpd
    import pandas as pd

    _servir(_colecao(3))
    coletar_fonte(fonte, cliente, tmp_path)
    responses.reset()
    _servir_cprm({"MG": 2})
    coletar_fonte(fonte_cprm, cliente, tmp_path, ufs=["MG"])

    saida = tmp_path / "v1"
    manifesto = exportar([fonte, fonte_cprm], tmp_path, saida, pmtiles=False)
    total = manifesto["total_setores"]
    assert total == 5

    gpkg = caminho_gpkg_nacional(tmp_path)
    parquet = caminho_parquet_nacional(tmp_path)
    csv = caminho_csv_nacional(tmp_path)

    # Cada agregado tem o país inteiro, não uma UF.
    assert len(gpd.read_file(gpkg)) == total
    assert len(gpd.read_parquet(parquet)) == total
    tabela = pd.read_csv(csv)
    assert len(tabela) == total

    # O manifest descreve os três, com sha256 que bate e URL de Release.
    arquivos = manifesto["arquivos"]
    assert set(arquivos) >= {"gpkg", "parquet", "csv", "shapefile"}
    for chave, caminho in (("gpkg", gpkg), ("parquet", parquet), ("csv", csv)):
        info = arquivos[chave]
        assert info["arquivo"] == caminho.name
        assert info["bytes"] == caminho.stat().st_size
        assert info["sha256"] == hashlib.sha256(caminho.read_bytes()).hexdigest()
        assert info["url"].endswith(caminho.name)
        assert "releases/latest/download" in info["url"]


@responses.activate
def test_csv_tem_centroide_e_nao_tem_geometria(tmp_path, fonte, cliente):
    """O CSV troca a geometria por lat/lon, e as coordenadas caem no setor."""
    import pandas as pd

    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    exportar([fonte], tmp_path, tmp_path / "v1", shapefiles=False, pmtiles=False)

    tabela = pd.read_csv(caminho_csv_nacional(tmp_path))
    assert "geometry" not in tabela.columns
    assert list(tabela.columns[-2:]) == ["lat", "lon"]
    # Os polígonos sintéticos ficam em volta de (LAT, LON), em Juiz de Fora.
    assert tabela["lat"].between(LAT - 0.01, LAT + 0.01).all()
    assert tabela["lon"].between(LON - 0.01, LON + 0.01).all()
    # E as colunas do esquema continuam todas lá.
    assert {"num_setor", "uf", "grau_risco", "bl_fonte", "bl_sob_cp"} <= set(tabela.columns)


def test_centroide_de_ponto_e_o_proprio_ponto():
    """Para `ponto_risco` o centroide não desloca a coordenada."""
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.GeoDataFrame(
        {"num_setor": ["X"]}, geometry=[Point(LON, LAT)], crs="EPSG:4326",
    )
    centro = centroides_do_csv(gdf)
    assert centro["lat"].iloc[0] == pytest.approx(LAT, abs=1e-5)
    assert centro["lon"].iloc[0] == pytest.approx(LON, abs=1e-5)


@responses.activate
def test_pmtiles_sem_tippecanoe_falha_alto(tmp_path, fonte, cliente, monkeypatch):
    """Sem o tippecanoe a exportação recusa, em vez de publicar sem o PMTiles.

    Publicar em silêncio deixaria no ar um PMTiles de uma coleta anterior que
    o manifest não lista.
    """
    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    monkeypatch.setattr("src.export.publicacao.shutil.which", lambda _: None)

    with pytest.raises(ExportacaoError, match="tippecanoe"):
        exportar([fonte], tmp_path, tmp_path / "v1", shapefiles=False, agregados=False)


@responses.activate
def test_sem_pmtiles_nao_gera_e_nao_entra_no_manifest(tmp_path, fonte, cliente):
    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    saida = tmp_path / "v1"
    manifesto = exportar([fonte], tmp_path, saida, shapefiles=False, agregados=False, pmtiles=False)
    assert "pmtiles" not in manifesto["arquivos"]
    assert not caminho_pmtiles(saida).exists()


@responses.activate
def test_exportar_substitui_agregado_de_coleta_anterior(tmp_path, fonte, cliente):
    """Agregado antigo é substituído, não fica no diretório sem constar no manifest."""
    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    velho = caminho_gpkg_nacional(tmp_path)
    velho.parent.mkdir(parents=True, exist_ok=True)
    velho.write_bytes(b"gpkg de ontem")

    exportar([fonte], tmp_path, tmp_path / "v1", shapefiles=False, pmtiles=False)
    assert velho.read_bytes() != b"gpkg de ontem"


@responses.activate
def test_sem_agregados_nao_apaga_o_da_coleta_anterior(tmp_path, fonte, cliente):
    """Apagar o que esta execução não regera destruiria o arquivo anterior sem substituto.

    Vale para o PMTiles também, que é o caso real: `--sem-pmtiles` numa
    máquina sem tippecanoe não pode tirar do ar o PMTiles que está publicado.
    """
    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    saida = tmp_path / "v1"
    saida.mkdir(parents=True, exist_ok=True)
    gpkg_velho = caminho_gpkg_nacional(tmp_path)
    gpkg_velho.parent.mkdir(parents=True, exist_ok=True)
    gpkg_velho.write_bytes(b"gpkg de ontem")
    tiles_velho = caminho_pmtiles(saida)
    tiles_velho.write_bytes(b"pmtiles de ontem")

    exportar([fonte], tmp_path, saida, shapefiles=False, agregados=False, pmtiles=False)
    assert gpkg_velho.read_bytes() == b"gpkg de ontem"
    assert tiles_velho.read_bytes() == b"pmtiles de ontem"


def _tippecanoe_falso(diretorio, corpo: str) -> None:
    """Põe um `tippecanoe` executável no PATH, para exercitar o invólucro.

    O tippecanoe de verdade é um binário C++ que não está nas dependências do
    projeto; o CI o instala pelo apt. O que precisa de teste aqui é o nosso
    invólucro: os argumentos montados, a troca atômica e o erro quando ele
    reprova.
    """
    binario = diretorio / "tippecanoe"
    binario.write_text(corpo)
    binario.chmod(0o755)


@responses.activate
def test_pmtiles_monta_o_comando_e_troca_atomicamente(tmp_path, fonte, cliente, monkeypatch):
    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    falso = tmp_path / "bin"
    falso.mkdir()
    _tippecanoe_falso(falso, '#!/bin/sh\nprintf "%s\\n" "$@" > "$TIPPE_LOG"\n: > "$2"\n')
    log = tmp_path / "args.txt"
    monkeypatch.setenv("PATH", str(falso), prepend=False)
    monkeypatch.setenv("TIPPE_LOG", str(log))

    saida = tmp_path / "v1"
    manifesto = exportar([fonte], tmp_path, saida, shapefiles=False, agregados=False)

    argumentos = log.read_text().split("\n")
    assert "-l" in argumentos and "setores" in argumentos
    assert "--drop-densest-as-needed" in argumentos
    assert "-Z" in argumentos and "-z" in argumentos
    # Recebe os GeoJSON por UF já gravados, não um temporário nosso.
    assert str(saida / "setores_mg.geojson") in argumentos
    # O `-o` aponta para o temporário, e o final é o nome definitivo.
    assert any(a.endswith(".pmtiles.tmp") for a in argumentos)
    assert caminho_pmtiles(saida).exists()
    assert not caminho_pmtiles(saida).with_name("setores.pmtiles.tmp").exists()
    assert manifesto["arquivos"]["pmtiles"]["url"].endswith("v1/setores.pmtiles")


@responses.activate
def test_pmtiles_que_reprova_nao_deixa_arquivo_pela_metade(tmp_path, fonte, cliente, monkeypatch):
    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    falso = tmp_path / "bin"
    falso.mkdir()
    _tippecanoe_falso(falso, '#!/bin/sh\n: > "$2"\necho "geometria invalida" >&2\nexit 3\n')
    monkeypatch.setenv("PATH", str(falso), prepend=False)

    saida = tmp_path / "v1"
    with pytest.raises(ExportacaoError, match="geometria invalida"):
        exportar([fonte], tmp_path, saida, shapefiles=False, agregados=False)
    assert not caminho_pmtiles(saida).exists()


@responses.activate
def test_sob_cp_mantem_os_tres_estados_em_cada_formato(tmp_path, fonte, fonte_cprm, cliente):
    """`bl_sob_cp` tem três estados, e nenhum formato pode colapsar dois.

    True = a CPRM cobre; False = conferido e não cobre; nulo = é setor da
    própria CPRM, não se aplica. GeoJSON, GeoPackage e GeoParquet guardam
    booleano; o Shapefile, cujo DBF não tem booleano, guarda 1 / 0 / vazio.

    O GeoPackage é conferido pelo tipo declarado no arquivo e pelo valor cru
    no SQLite, não pelo que o pandas devolve: pandas converte coluna inteira
    com nulo para real, e isso é do leitor, não do arquivo.
    """
    import geopandas as gpd
    import pandas as pd

    _servir(_colecao(2))
    coletar_fonte(fonte, cliente, tmp_path)
    responses.reset()
    _servir_cprm({"MG": 2})
    coletar_fonte(fonte_cprm, cliente, tmp_path, ufs=["MG"])

    saida = tmp_path / "v1"
    exportar([fonte, fonte_cprm], tmp_path, saida, pmtiles=False)

    # GeoParquet: booleano de verdade, com o nulo preservado.
    parquet = gpd.read_parquet(caminho_parquet_nacional(tmp_path))
    assert parquet["bl_sob_cp"].dtype == "boolean"
    cprm = parquet["bl_fonte"] == "br-sgb-setorizacao"
    assert parquet.loc[cprm, "bl_sob_cp"].isna().all()
    assert not parquet.loc[~cprm, "bl_sob_cp"].isna().any()

    # GeoPackage: coluna declarada BOOLEAN e NULL de verdade no SQLite.
    import sqlite3

    caminho_gpkg = caminho_gpkg_nacional(tmp_path)
    con = sqlite3.connect(caminho_gpkg)
    try:
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'setores_risco'"
        ).fetchone()[0]
        assert '"bl_sob_cp" BOOLEAN' in ddl
        tipos = dict(con.execute(
            "SELECT bl_fonte, typeof(bl_sob_cp) FROM setores_risco"
        ).fetchall())
    finally:
        con.close()
    assert tipos["br-sgb-setorizacao"] == "null"
    assert tipos["mg-teste-municipal"] == "integer"

    # CSV: os três estados continuam distinguíveis (vazio para a CPRM).
    tabela = pd.read_csv(caminho_csv_nacional(tmp_path))
    assert tabela.loc[tabela["bl_fonte"] == "br-sgb-setorizacao", "bl_sob_cp"].isna().all()


@responses.activate
def test_exemplo_de_duckdb_da_documentacao_funciona(tmp_path, fonte, fonte_cprm, cliente):
    """A consulta que docs/usar-os-dados.md promete roda, e bate com o manifest.

    É o que justifica o duckdb estar nas dependências de desenvolvimento:
    exemplo de documentação que ninguém executa é exemplo que apodrece.
    """
    duckdb = pytest.importorskip("duckdb")

    _servir(_colecao(3))
    coletar_fonte(fonte, cliente, tmp_path)
    responses.reset()
    _servir_cprm({"MG": 2})
    coletar_fonte(fonte_cprm, cliente, tmp_path, ufs=["MG"])

    manifesto = exportar([fonte, fonte_cprm], tmp_path, tmp_path / "v1", pmtiles=False)
    parquet = caminho_parquet_nacional(tmp_path)

    con = duckdb.connect()
    try:
        por_fonte = dict(con.execute(
            "SELECT bl_fonte, count(*) FROM read_parquet(?) GROUP BY 1",
            [str(parquet)],
        ).fetchall())
        total = con.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(parquet)],
        ).fetchone()[0]
    finally:
        con.close()

    assert total == manifesto["total_setores"]
    assert por_fonte == manifesto["ufs"]["mg"]["por_fonte"]
