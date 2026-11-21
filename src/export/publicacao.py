"""Monta a saída publicada (contrato v1, ver docs/contrato-dados.md).

Lê o normalizado de cada fonte publicável, marca a sobreposição com a CPRM,
valida e grava em `saida_dir`:

- `setores_<uf>.geojson`: todos os setores da UF, de todas as fontes,
  ordenados por `num_setor` (diff estável entre execuções);
- `manifest.json`: índice com contagem, sha256 e bytes de cada arquivo, as
  fontes do catálogo (inclusive as não coletadas) e a versão do esquema;
- `relatorio_validacao.json`: erros e avisos por fonte.

E, em `dir_shapefiles`, um `setores_<uf>.zip` por UF com o mesmo conteúdo em
Shapefile (um .shp para polígonos e outro para pontos, porque o formato não
mistura os dois). O Shapefile vai para as Releases, não para o Pages.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
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
    CRS_PUBLICACAO,
    DATA_DIR,
    PUBLICACAO_DIR,
    VERSAO_CONTRATO,
    VERSAO_ESQUEMA,
    caminho_manifesto,
    caminho_relatorio,
    caminho_setores_uf,
    dir_shapefiles,
)
from src.cprm.sobreposicao import marcar_sobreposicao
from src.normalizacao.esquema import COLUNAS, COLUNAS_NUMERICAS
from src.pipeline import ler_normalizado, ler_proveniencia
from src.validacao import validar

logger = logging.getLogger(__name__)

PRECISAO_COORDENADAS = 7  # ~1 cm; basta para setor de risco e encolhe o arquivo


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
    temporario.write_text(texto)
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
    gdf.to_file(
        temporario, driver="GeoJSON", layer_options={
            "COORDINATE_PRECISION": PRECISAO_COORDENADAS, "RFC7946": "YES", "WRITE_BBOX": "NO",
        },
    )
    os.replace(temporario, destino)


def _gravar_shapefile(gdf: gpd.GeoDataFrame, uf: str, destino_dir: Path) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    zip_path = destino_dir / f"setores_{uf.lower()}.zip"
    shp = gdf.copy()
    # DBF não tem booleano: 1 = sobrepõe, 0 = não sobrepõe, vazio = não se aplica.
    shp["bl_sob_cp"] = shp["bl_sob_cp"].map({True: 1, False: 0}).astype("Int64")
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

    ufs: dict[str, Any] = {}
    for uf, grupo in publicaveis.groupby("uf", sort=True):
        destino = caminho_setores_uf(str(uf), saida_dir)
        _gravar_geojson(grupo, destino)
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
            _gravar_shapefile(grupo, str(uf), dir_shapefiles(data_dir))

    manifesto = {
        "contrato": VERSAO_CONTRATO,
        "versao_esquema": VERSAO_ESQUEMA,
        "beluga_versao": __version__,
        "gerado_em": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "crs": CRS_PUBLICACAO,
        "total_setores": len(publicaveis),
        "colunas": COLUNAS,
        "ufs": ufs,
        "fontes": _resumo_fontes(fontes, publicaveis, data_dir),
    }
    _gravar_atomico(
        json.dumps(relatorio.como_dict() | {"gerado_em": manifesto["gerado_em"]},
                   ensure_ascii=False, indent=2),
        caminho_relatorio(saida_dir),
    )
    # O manifest por último: quem lê o manifest encontra os arquivos já no lugar.
    _gravar_atomico(json.dumps(manifesto, ensure_ascii=False, indent=2), caminho_manifesto(saida_dir))
    logger.info("Publicados %d setores em %d UF(s) em %s", len(publicaveis), len(ufs), saida_dir)
    return manifesto
