"""Malha municipal do IBGE para o teste "setor dentro do município declarado".

Uma consulta por UF à API de malhas v3 (todos os municípios da UF de uma
vez), guardada em `data/cache/malhas/`. Sem a malha a validação só pula esse
teste: a falta de um insumo de conferência não pode bloquear a publicação.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.coleta.http import Cliente, ColetaError
from src.config import dir_cache

logger = logging.getLogger(__name__)

URL_MALHA_UF = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
PARAMETROS = {
    "formato": "application/vnd.geo+json",
    "qualidade": "intermediaria",
    "intrarregiao": "municipio",
}


def _ler_uf(cliente: Cliente, uf: str, cache: Path) -> gpd.GeoDataFrame:
    arquivo = cache / f"{uf.lower()}.geojson"
    if not arquivo.exists():
        dados = cliente.get_json(URL_MALHA_UF.format(uf=uf), dict(PARAMETROS))
        if not dados.get("features"):
            raise ColetaError(f"malha de {uf} voltou vazia")
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(dados))
    gdf = gpd.read_file(arquivo)
    gdf["cd_ibge"] = gdf["codarea"].astype(str)
    return gdf[["cd_ibge", "geometry"]]


def obter_malhas(
    ufs: list[str], cliente: Cliente | None = None, data_dir: Path | None = None,
) -> tuple[gpd.GeoDataFrame | None, list[str]]:
    """`(malhas, ufs_sem_malha)`. `malhas` é None se nenhuma UF deu certo."""
    # A API do IBGE é pública e documentada para consumo automatizado, e o
    # robots.txt dela não responde: sem a exceção a malha nunca seria lida.
    cliente = cliente or Cliente(max_tentativas=3, backoff=2.0, robots_inacessivel_bloqueia=False)
    cache = (dir_cache(data_dir) if data_dir else dir_cache()) / "malhas"
    partes, falhas = [], []
    for uf in sorted(set(ufs)):
        try:
            partes.append(_ler_uf(cliente, uf, cache))
        except (ColetaError, ValueError, OSError) as exc:
            logger.warning("Malha do IBGE de %s indisponível: %s", uf, exc)
            falhas.append(uf)
    if not partes:
        return None, falhas
    malhas = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=partes[0].crs)
    return malhas, falhas
