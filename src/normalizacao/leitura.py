"""Leitura do payload bruto de cada formato para um GeoDataFrame em EPSG:4326."""

from __future__ import annotations

import io
import json
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely import wkt

from src.config import CRS_PUBLICACAO


class LeituraError(ValueError):
    """O payload bruto não tem o formato declarado no catálogo."""


def _geojson(conteudo: bytes) -> gpd.GeoDataFrame:
    dados = json.loads(conteudo)
    features = dados.get("features") or []
    if not features:
        raise LeituraError("GeoJSON sem feições")
    # GeoJSON (RFC 7946) é sempre WGS84; o ArcGIS já entrega reprojetado.
    return gpd.GeoDataFrame.from_features(features, crs=CRS_PUBLICACAO)


def _csv(conteudo: bytes, parametros: dict[str, Any]) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(conteudo), sep=parametros.get("separador", ","), dtype=str,
        encoding=parametros.get("codificacao", "utf-8-sig"), keep_default_na=False,
    )


def _csv_wkt(conteudo: bytes, parametros: dict[str, Any], crs: str | None) -> gpd.GeoDataFrame:
    if not crs:
        raise LeituraError("csv_wkt precisa de acesso.crs_origem")
    tabela = _csv(conteudo, parametros)
    coluna = parametros.get("coluna_geometria", "WKT")
    if coluna not in tabela.columns:
        raise LeituraError(f"coluna de geometria {coluna!r} ausente; colunas: {list(tabela.columns)}")
    geometrias = tabela.pop(coluna).map(lambda t: wkt.loads(t) if t else None)
    return gpd.GeoDataFrame(tabela, geometry=geometrias, crs=crs).to_crs(CRS_PUBLICACAO)


def _csv_xy(conteudo: bytes, parametros: dict[str, Any], crs: str | None) -> gpd.GeoDataFrame:
    tabela = _csv(conteudo, parametros)
    x, y = parametros.get("coluna_x", "longitude"), parametros.get("coluna_y", "latitude")
    xs = pd.to_numeric(tabela[x].str.strip(), errors="coerce")
    ys = pd.to_numeric(tabela[y].str.strip(), errors="coerce")
    return gpd.GeoDataFrame(
        tabela, geometry=gpd.points_from_xy(xs, ys), crs=crs or CRS_PUBLICACAO,
    ).to_crs(CRS_PUBLICACAO)


def ler_bruto(
    conteudo: bytes, formato: str | None, parametros: dict[str, Any] | None = None,
    crs_origem: str | None = None,
) -> gpd.GeoDataFrame:
    parametros = parametros or {}
    try:
        if formato == "geojson":
            gdf = _geojson(conteudo)
        elif formato == "csv_wkt":
            gdf = _csv_wkt(conteudo, parametros, crs_origem)
        elif formato == "csv_xy":
            gdf = _csv_xy(conteudo, parametros, crs_origem)
        else:
            raise LeituraError(f"formato sem leitor: {formato!r}")
    except LeituraError:
        raise
    except (ValueError, KeyError, UnicodeDecodeError) as exc:
        raise LeituraError(f"payload ilegível como {formato}: {exc}") from exc
    if gdf.empty:
        raise LeituraError("nenhum registro no payload")
    return gdf
