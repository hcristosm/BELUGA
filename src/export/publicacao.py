"""Monta a saída publicada (contrato v1, ver docs/contrato-dados.md).

Lê o normalizado de cada fonte publicável, marca a sobreposição com a CPRM,
valida e grava em `saida_dir`:

- `setores_<uf>.geojson`: todos os setores da UF, de todas as fontes,
  ordenados por `num_setor` (diff estável entre execuções);
- `manifest.json`: índice com contagem, sha256 e bytes de cada arquivo, as
  fontes do catálogo (inclusive as não coletadas) e a versão do esquema;
- `relatorio_validacao.json`: erros e avisos por fonte.

- `setores.pmtiles`: tiles vetoriais do país inteiro. Fica no Pages porque
  PMTiles é lido por requisição Range, que o Pages serve com CORS.

E, em `dir_release`, os arquivos que vão anexados à Release da coleta, não ao
Pages: `setores_<uf>.zip` por UF em Shapefile (um .shp para polígonos e outro
para pontos, porque o formato não mistura os dois), mais o país inteiro em
`setores.gpkg`, `setores.parquet` e `setores.csv`.

A divisão entre Pages e Release não é arbitrária. O `gh-pages` guarda
histórico (sem `force_orphan`), então cada megabyte publicado ali fica no
repositório para sempre, e o git recusa arquivo acima de 100 MiB. Só vai para
o Pages o que precisa de URL servida com CORS: o contrato v1 do ORCA e o
PMTiles. O resto vai para a Release, que não é objeto git e aceita até 2 GB.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess  # nosec B404
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from src import __version__
from src.catalogo import Fonte
from src.config import (
    CAMADA_SETORES,
    CRS_METRICO,
    CRS_PUBLICACAO,
    DATA_DIR,
    PUBLICACAO_DIR,
    URL_PAGES,
    URL_RELEASE,
    VERSAO_CONTRATO,
    VERSAO_ESQUEMA,
    caminho_csv_nacional,
    caminho_gpkg_nacional,
    caminho_manifesto,
    caminho_parquet_nacional,
    caminho_pmtiles,
    caminho_relatorio,
    caminho_setores_uf,
    caminho_shapefile_uf,
    dir_release,
    dir_shapefiles,
)
from src.cprm.sobreposicao import marcar_sobreposicao
from src.normalizacao.esquema import COLUNAS, COLUNAS_NUMERICAS
from src.pipeline import ler_normalizado, ler_proveniencia
from src.validacao import validar

logger = logging.getLogger(__name__)

PRECISAO_COORDENADAS = 7  # ~1 cm; basta para setor de risco e encolhe o arquivo
CASAS_CENTROIDE = 6  # ~10 cm; o centroide do CSV é referência, não geometria

# Zoom do PMTiles. Em z14 um setor de 50 m já tem alguns pixels. O teto é
# teto mesmo: sem `--extend-zooms-if-still-dropping`, que estenderia o zoom
# além do -z justamente quando ainda há descarte. O arquivo vai para a
# `gh-pages`, que guarda histórico, então tamanho previsível vale mais que
# detalhe extra. Abaixo de z5 o país inteiro não cabe num tile sem descartar
# quase tudo.
PMTILES_ZOOM_MIN = 5
PMTILES_ZOOM_MAX = 14
PMTILES_CAMADA = "setores"
PMTILES_DESCRICAO = "Setores de risco geológico do Brasil (BELUGA, contrato v1)"
# Assinatura de um PMTiles v3: "PMTiles" e a versão do formato. O tippecanoe
# escolhe o formato de saída pela EXTENSÃO do arquivo, então um temporário
# terminado em .tmp faz ele gravar MBTiles (SQLite) com nome de PMTiles, sem
# reclamar. Conferir os bytes é o que pega isso.
PMTILES_ASSINATURA = b"PMTiles\x03"


class ExportacaoError(RuntimeError):
    """Nada publicável: nenhuma fonte tem normalizado."""


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _gravar_atomico(texto: str, destino: Path) -> None:
    temporario = destino.with_name(destino.name + ".tmp")
    # encoding explícito: o manifest tem acento ("não declarada"), e
    # write_text sem encoding usa o locale do processo.
    temporario.write_text(texto, encoding="utf-8")
    os.replace(temporario, destino)


def juntar_fontes(fontes: list[Fonte], data_dir: Path = DATA_DIR) -> gpd.GeoDataFrame:
    partes = []
    for fonte in fontes:
        if not fonte.publicar:
            continue
        gdf = ler_normalizado(fonte.id, data_dir)
        if gdf is None or gdf.empty:
            logger.warning("%s: sem normalizado em %s; fica fora desta publicação.", fonte.id, data_dir)
            continue
        partes.append(gdf)
    if not partes:
        raise ExportacaoError("nenhuma fonte publicável tem setores normalizados; rode `coletar` antes")
    return gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=CRS_PUBLICACAO)


def _tipar(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Tipos explícitos antes de gravar. Coluna `object` com None e bool sai
    como texto ('True') no GeoJSON; com None e float pode sair vazia."""
    gdf = gdf.copy()
    gdf["bl_sob_cp"] = gdf["bl_sob_cp"].astype("boolean")
    for coluna in COLUNAS_NUMERICAS:
        gdf[coluna] = pd.to_numeric(gdf[coluna], errors="coerce").astype("float64")
    return gdf


def _gravar_geojson(gdf: gpd.GeoDataFrame, destino: Path) -> None:
    temporario = destino.with_name(destino.name + ".tmp")
    if temporario.exists():
        temporario.unlink()
    try:
        gdf.to_file(
            temporario, driver="GeoJSON", layer_options={
                "COORDINATE_PRECISION": PRECISAO_COORDENADAS, "RFC7946": "YES", "WRITE_BBOX": "NO",
            },
        )
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def _sob_cp_como_inteiro(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """`bl_sob_cp` como 1 / 0 / vazio, para o Shapefile, cujo DBF não tem booleano.

    Só o Shapefile precisa disto. GeoJSON, GeoPackage e GeoParquet guardam
    booleano com nulo, e os três estados sobrevivem (nulo = setor da própria
    CPRM, "não se aplica").
    """
    saida = gdf.copy()
    saida["bl_sob_cp"] = saida["bl_sob_cp"].map({True: 1, False: 0}).astype("Int64")
    return saida


def _gravar_shapefile(gdf: gpd.GeoDataFrame, uf: str, data_dir: Path) -> Path:
    dir_shapefiles(data_dir).mkdir(parents=True, exist_ok=True)
    zip_path = caminho_shapefile_uf(uf, data_dir)
    # 1 = sobrepõe, 0 = não sobrepõe, vazio = não se aplica (setor da CPRM).
    shp = _sob_cp_como_inteiro(gdf)
    grupos = {
        "poligonos": shp[shp.geom_type.isin(["Polygon", "MultiPolygon"])],
        "pontos": shp[shp.geom_type.isin(["Point", "MultiPoint"])],
    }
    with tempfile.TemporaryDirectory() as tmp:
        for nome, parte in grupos.items():
            if parte.empty:
                continue
            parte.to_file(Path(tmp) / f"setores_{uf.lower()}_{nome}.shp", encoding="UTF-8")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo in sorted(Path(tmp).iterdir()):
                zf.write(arquivo, arquivo.name)
    return zip_path


def _gravar_gpkg(gdf: gpd.GeoDataFrame, destino: Path) -> None:
    """GeoPackage nacional. Uma camada só, com polígonos e pontos juntos."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    # O temporário mantém a extensão .gpkg: o GDAL confere a extensão e avisa
    # quando ela não corresponde ao driver.
    temporario = destino.with_name(destino.stem + ".tmp" + destino.suffix)
    if temporario.exists():
        temporario.unlink()
    try:
        gdf.to_file(temporario, driver="GPKG", layer=CAMADA_SETORES)
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def _gravar_parquet(gdf: gpd.GeoDataFrame, destino: Path) -> None:
    """GeoParquet nacional. Exige pyarrow (dependência de runtime)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".tmp")
    try:
        gdf.to_parquet(temporario, compression="zstd")
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def centroides_do_csv(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """lat/lon do centroide de cada setor, calculado em CRS métrico.

    O centroide sai do `CRS_METRICO` e volta para graus, e não direto de
    EPSG:4326, porque centroide de polígono em graus distorce com a latitude.
    Para `Point` o centroide é o próprio ponto. Em polígono muito concavo o
    centroide pode cair fora da área: o CSV é referência para localizar o
    setor num mapa, não substituto da geometria.
    """
    centro = gdf.geometry.to_crs(CRS_METRICO).centroid.to_crs(CRS_PUBLICACAO)
    return pd.DataFrame({
        "lat": centro.y.round(CASAS_CENTROIDE),
        "lon": centro.x.round(CASAS_CENTROIDE),
    }, index=gdf.index)


def _gravar_csv(gdf: gpd.GeoDataFrame, destino: Path) -> None:
    """CSV com os atributos e a lat/lon do centroide, sem geometria.

    Contagem de edificação, domicílio e pessoa sai como inteiro. `_tipar`
    força tudo em COLUNAS_NUMERICAS para real por causa do GeoJSON, e "12.0"
    numa planilha é defeito.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    atributos = pd.DataFrame(gdf.drop(columns="geometry"))
    for coluna in ("num_edif", "num_domi", "num_pess"):
        atributos[coluna] = atributos[coluna].astype("Int64")
    tabela = pd.concat([atributos, centroides_do_csv(gdf)], axis=1)
    temporario = destino.with_name(destino.name + ".tmp")
    try:
        tabela.to_csv(temporario, index=False, encoding="utf-8")
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def _gravar_pmtiles(entradas: list[Path], destino: Path) -> None:
    """Tiles vetoriais com o tippecanoe, a partir dos GeoJSON por UF já gravados.

    Falha alto se o tippecanoe não estiver instalado; quem não tem a
    ferramenta passa `--sem-pmtiles` de propósito (ver docs/funcionamento.md).

    Em zoom baixo o tippecanoe descarta feição para o tile caber
    (`--drop-densest-as-needed`). O PMTiles serve para desenhar mapa, não para
    contar setores: a contagem autoritativa é a do manifest e dos GeoJSON.
    """
    if shutil.which("tippecanoe") is None:
        raise ExportacaoError(
            "tippecanoe não encontrado no PATH e o PMTiles foi pedido. "
            "Instale (`sudo apt install tippecanoe`) ou rode com `--sem-pmtiles`."
        )
    if not entradas:
        raise ExportacaoError("nenhum GeoJSON de UF para gerar o PMTiles")
    destino.parent.mkdir(parents=True, exist_ok=True)
    # O temporário mantém a extensão .pmtiles: é por ela que o tippecanoe
    # escolhe o formato de saída.
    temporario = destino.with_name(destino.stem + ".tmp" + destino.suffix)
    comando = [
        "tippecanoe", "-o", str(temporario), "--force",
        "-l", PMTILES_CAMADA,
        # Sem -n e -N, o tippecanoe usa o nome do arquivo de saída, e aí o
        # caminho do temporário (com ".tmp") vai no metadata publicado.
        "-n", PMTILES_CAMADA,
        "-N", PMTILES_DESCRICAO,
        "-Z", str(PMTILES_ZOOM_MIN), "-z", str(PMTILES_ZOOM_MAX),
        "--drop-densest-as-needed",
        *[str(e) for e in entradas],
    ]
    try:
        # Sem shell. O executável é fixo e já foi resolvido por shutil.which,
        # e todos os argumentos são caminhos que nós mesmos geramos.
        resultado = subprocess.run(  # nosec B603
            comando, capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        raise ExportacaoError(f"falha ao executar o tippecanoe: {exc}") from exc
    try:
        if resultado.returncode != 0:
            raise ExportacaoError(
                f"tippecanoe saiu com {resultado.returncode}: {resultado.stderr.strip()[-2000:]}"
            )
        _conferir_pmtiles(temporario)
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def _conferir_pmtiles(caminho: Path) -> None:
    """Recusa arquivo que não seja PMTiles de verdade.

    O tippecanoe sai com 0 e grava MBTiles quando não reconhece a extensão
    como PMTiles. O arquivo fica com o nome certo, o tamanho plausível e
    conteúdo que nenhum leitor de PMTiles abre. Sem esta conferência, a
    publicação segue e o mapa web de quem consome simplesmente não carrega.
    """
    with caminho.open("rb") as fh:
        inicio = fh.read(len(PMTILES_ASSINATURA))
    if inicio != PMTILES_ASSINATURA:
        raise ExportacaoError(
            f"{caminho.name} não é PMTiles: começa com {inicio!r}, e não "
            f"{PMTILES_ASSINATURA!r}. O tippecanoe escolhe o formato pela extensão "
            "do arquivo de saída."
        )


def _descrever(caminho: Path, url_base: str) -> dict[str, Any]:
    return {
        "arquivo": caminho.name,
        "url": url_base + caminho.name,
        "bytes": caminho.stat().st_size,
        "sha256": _sha256_arquivo(caminho),
    }


def _resumo_fontes(
    fontes: list[Fonte], publicados: gpd.GeoDataFrame, data_dir: Path,
) -> list[dict[str, Any]]:
    contagem = publicados["bl_fonte"].value_counts().to_dict()
    resumo = []
    for fonte in fontes:
        item = fonte.resumo()
        prov = ler_proveniencia(fonte.id, data_dir) if fonte.ativa else {"particoes": {}}
        datas = [p["coletado_em"] for p in prov["particoes"].values() if p.get("coletado_em")]
        item["coletado_em"] = max(datas) if datas else None
        item["setores_publicados"] = int(contagem.get(fonte.id, 0))
        resumo.append(item)
    return resumo


def exportar(
    fontes: list[Fonte],
    data_dir: Path = DATA_DIR,
    saida_dir: Path = PUBLICACAO_DIR,
    malhas: gpd.GeoDataFrame | None = None,
    avisos_globais: list[str] | None = None,
    shapefiles: bool = True,
    agregados: bool = True,
    pmtiles: bool = True,
) -> dict[str, Any]:
    """Grava a publicação e devolve o manifest."""
    setores = marcar_sobreposicao(juntar_fontes(fontes, data_dir))
    publicaveis, relatorio = validar(setores, malhas)
    relatorio.globais.extend(avisos_globais or [])
    publicaveis = _tipar(publicaveis.sort_values("num_setor", kind="stable")[[*COLUNAS, "geometry"]])

    saida_dir.mkdir(parents=True, exist_ok=True)
    # Arquivo de UF que sumiu desta publicação não pode ficar para trás
    # apontando dado velho que o manifest não lista.
    for antigo in saida_dir.glob("setores_*.geojson"):
        antigo.unlink()
    if shapefiles and dir_shapefiles(data_dir).exists():
        for antigo in dir_shapefiles(data_dir).glob("setores_*.zip"):
            antigo.unlink()
    # Mesma higiene para os agregados, mas só para os que vão ser regerados:
    # apagar o que esta execução não produz destruiria o arquivo da coleta
    # anterior sem substituto. O que sai do diretório sai do ar junto, porque
    # o deploy não usa `keep_files` e remove do destino o que não está aqui.
    if pmtiles:
        caminho_pmtiles(saida_dir).unlink(missing_ok=True)
    if agregados:
        for antigo in (
            caminho_gpkg_nacional(data_dir),
            caminho_parquet_nacional(data_dir),
            caminho_csv_nacional(data_dir),
        ):
            antigo.unlink(missing_ok=True)

    ufs: dict[str, Any] = {}
    geojsons: list[Path] = []
    for uf, grupo in publicaveis.groupby("uf", sort=True):
        destino = caminho_setores_uf(str(uf), saida_dir)
        _gravar_geojson(grupo, destino)
        geojsons.append(destino)
        ufs[str(uf).lower()] = {
            "arquivo": destino.name,
            "setores": len(grupo),
            "bytes": destino.stat().st_size,
            "sha256": _sha256_arquivo(destino),
            "por_fonte": {str(k): int(v) for k, v in grupo["bl_fonte"].value_counts().sort_index().items()},
            "por_grau": {
                str(k): int(v)
                for k, v in grupo["grau_risco"].fillna("sem grau").value_counts().sort_index().items()
            },
        }
        if shapefiles:
            _gravar_shapefile(grupo, str(uf), data_dir)

    arquivos: dict[str, Any] = {}
    if pmtiles:
        destino_tiles = caminho_pmtiles(saida_dir)
        _gravar_pmtiles(geojsons, destino_tiles)
        arquivos["pmtiles"] = _descrever(destino_tiles, URL_PAGES)
    if agregados:
        for chave, caminho, escritor in (
            ("gpkg", caminho_gpkg_nacional(data_dir), _gravar_gpkg),
            ("parquet", caminho_parquet_nacional(data_dir), _gravar_parquet),
            ("csv", caminho_csv_nacional(data_dir), _gravar_csv),
        ):
            escritor(publicaveis, caminho)
            arquivos[chave] = _descrever(caminho, URL_RELEASE)
    if shapefiles:
        arquivos["shapefile"] = {
            "por_uf": {
                uf: _descrever(caminho_shapefile_uf(uf, data_dir), URL_RELEASE)
                for uf in ufs
            },
        }

    manifesto = {
        "contrato": VERSAO_CONTRATO,
        "versao_esquema": VERSAO_ESQUEMA,
        "beluga_versao": __version__,
        "gerado_em": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "crs": CRS_PUBLICACAO,
        "total_setores": len(publicaveis),
        "colunas": COLUNAS,
        "ufs": ufs,
        "arquivos": arquivos,
        "fontes": _resumo_fontes(fontes, publicaveis, data_dir),
    }
    _gravar_atomico(
        json.dumps(relatorio.como_dict() | {"gerado_em": manifesto["gerado_em"]},
                   ensure_ascii=False, indent=2),
        caminho_relatorio(saida_dir),
    )
    # O manifest por último: quem lê o manifest encontra os arquivos já no lugar.
    _gravar_atomico(json.dumps(manifesto, ensure_ascii=False, indent=2), caminho_manifesto(saida_dir))
    logger.info(
        "Publicados %d setores em %d UF(s) em %s; agregados em %s",
        len(publicaveis), len(ufs), saida_dir, dir_release(data_dir),
    )
    return manifesto
