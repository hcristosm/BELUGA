"""Marca os setores de outras fontes que se sobrepõem a setores da CPRM/SGB.

Só marca, nunca descarta: quem decide como exibir é o ORCA. Para cada setor
que não é da CPRM:

- `bl_sob_cp`: True se a CPRM cobre ao menos `FRACAO_MINIMA` da área do
  setor (ou, para ponto, se o ponto está dentro de um setor da CPRM);
- `bl_cp_set`: `num_setor` dos setores da CPRM tocados, em ordem, separados
  por vírgula;
- `bl_cp_frac`: fração da área do setor coberta pela união dos setores da
  CPRM tocados (nula para pontos).

Nos setores da própria CPRM as três colunas ficam nulas: "não se aplica".
As áreas são calculadas em `CRS_METRICO` (SIRGAS 2000 / Brasil Policônica).
"""

from __future__ import annotations

import geopandas as gpd
from shapely import union_all

from src.catalogo import ID_FONTE_CPRM
from src.config import CRS_METRICO

# Encostar borda com borda (polígonos vizinhos digitalizados separadamente)
# gera interseções minúsculas que não são sobreposição real. Em Juiz de Fora
# (2026-11-21), 47 dos 202 setores que tocavam a CPRM tinham menos de 1% da
# área coberta: faixas de borda. Abaixo disso a fração fica registrada em
# `bl_cp_frac`, mas o setor não conta como sobreposto.
AREA_MINIMA_M2 = 1.0
FRACAO_MINIMA = 0.01


def marcar_sobreposicao(setores: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    resultado = setores.copy()
    for coluna in ("bl_sob_cp", "bl_cp_set", "bl_cp_frac"):
        resultado[coluna] = None
    resultado["bl_sob_cp"] = resultado["bl_sob_cp"].astype(object)

    e_cprm = resultado["bl_fonte"] == ID_FONTE_CPRM
    externos = resultado[~e_cprm]
    if externos.empty:
        return resultado
    cprm = resultado[e_cprm]
    resultado.loc[externos.index, "bl_sob_cp"] = False
    if cprm.empty:
        return resultado

    cprm_m = cprm.to_crs(CRS_METRICO)
    externos_m = externos.to_crs(CRS_METRICO)
    pares = cprm_m.sindex.query(externos_m.geometry, predicate="intersects")
    tocados: dict[int, list[int]] = {}
    for pos_externo, pos_cprm in zip(*pares):
        tocados.setdefault(int(pos_externo), []).append(int(pos_cprm))

    for pos_externo, posicoes in tocados.items():
        idx = externos_m.index[pos_externo]
        geom = externos_m.geometry.iloc[pos_externo]
        candidatos = cprm_m.iloc[posicoes]
        if geom.geom_type in ("Point", "MultiPoint"):
            reais = candidatos[candidatos.geometry.intersects(geom)]
            fracao = None
        else:
            areas = candidatos.geometry.intersection(geom).area
            reais = candidatos[areas > AREA_MINIMA_M2]
            if reais.empty:
                continue
            coberta = union_all(reais.geometry.values).intersection(geom).area
            fracao = round(min(coberta / geom.area, 1.0), 4) if geom.area > 0 else None
            if fracao is not None and fracao < FRACAO_MINIMA:
                resultado.at[idx, "bl_cp_frac"] = fracao
                continue
        if reais.empty:
            continue
        resultado.at[idx, "bl_sob_cp"] = True
        resultado.at[idx, "bl_cp_set"] = ",".join(sorted(str(s) for s in reais["num_setor"]))
        resultado.at[idx, "bl_cp_frac"] = fracao
    return resultado
