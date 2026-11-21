"""Validação dos setores normalizados antes da publicação.

Dois níveis:

- **erro**: o setor sai da publicação e entra no relatório. Geometria nula,
  vazia, inválida mesmo depois do `make_valid`, de tipo não aceito ou fora
  do Brasil; `num_setor` nulo ou repetido; UF inválida; grau fora do
  vocabulário; `cd_geocmu` fora do formato.
- **aviso**: o setor é publicado e o problema vai para o relatório. Sem
  código IBGE, ou com o ponto representativo fora do município declarado.

O CRS errado no conjunto inteiro é erro de programação e levanta exceção.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import MultiPoint, MultiPolygon
from shapely.geometry.base import BaseGeometry

from src.catalogo import vocabulario
from src.config import CRS_METRICO, CRS_PUBLICACAO, UFS_VALIDAS
from src.normalizacao.esquema import COLUNAS, GEOMETRIAS_ACEITAS

# Caixa do Brasil com folga (inclui ilhas oceânicas).
LIMITES_BRASIL = (-74.5, -34.5, -28.0, 6.0)
# Tolerância para o teste "dentro do município": a malha do IBGE é
# generalizada e setor de borda pode cruzar a divisa por alguns metros.
TOLERANCIA_MUNICIPIO_M = 500.0
EXEMPLOS_POR_MOTIVO = 20


@dataclass
class Relatorio:
    entrada: Counter = field(default_factory=Counter)
    publicados: Counter = field(default_factory=Counter)
    erros: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    avisos: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    exemplos: dict[str, dict[str, list[str]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )
    globais: list[str] = field(default_factory=list)

    def anotar(self, tipo: str, fonte: str, motivo: str, setor: Any) -> None:
        (self.erros if tipo == "erro" else self.avisos)[fonte][motivo] += 1
        lista = self.exemplos[fonte][motivo]
        if len(lista) < EXEMPLOS_POR_MOTIVO:
            lista.append(str(setor))

    def como_dict(self) -> dict[str, Any]:
        fontes = sorted(set(self.entrada) | set(self.erros) | set(self.avisos))
        return {
            "total_entrada": sum(self.entrada.values()),
            "total_publicado": sum(self.publicados.values()),
            "avisos_globais": self.globais,
            "por_fonte": {
                f: {
                    "entrada": self.entrada[f],
                    "publicados": self.publicados[f],
                    "erros": dict(self.erros[f]),
                    "avisos": dict(self.avisos[f]),
                    "exemplos": {m: v for m, v in self.exemplos[f].items()},
                }
                for f in fontes
            },
        }


def _nulo(valor: Any) -> bool:
    return valor is None or (not isinstance(valor, str) and bool(pd.isna(valor)))


def _so_area_ou_ponto(geom: BaseGeometry) -> BaseGeometry:
    """`make_valid` pode devolver coleção (polígono + linha solta); fica a parte útil."""
    if geom.geom_type != "GeometryCollection":
        return geom
    poligonos = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
    if poligonos:
        partes = [p for g in poligonos for p in getattr(g, "geoms", [g])]
        return partes[0] if len(partes) == 1 else MultiPolygon(partes)
    pontos = [g for g in geom.geoms if g.geom_type == "Point"]
    if pontos:
        return pontos[0] if len(pontos) == 1 else MultiPoint(pontos)
    return geom


def _motivo_geometria(geom: BaseGeometry | None) -> str | None:
    if geom is None:
        return "geometria nula"
    if geom.is_empty:
        return "geometria vazia"
    if not geom.is_valid:
        return "geometria inválida"
    if geom.geom_type not in GEOMETRIAS_ACEITAS:
        return f"tipo de geometria não aceito: {geom.geom_type}"
    oeste, sul, leste, norte = geom.bounds
    o, s, l, n = LIMITES_BRASIL
    if oeste < o or sul < s or leste > l or norte > n:
        return "geometria fora do Brasil"
    return None


def validar(
    setores: gpd.GeoDataFrame, malhas: gpd.GeoDataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, Relatorio]:
    """Devolve `(publicaveis, relatorio)`. `malhas`: polígonos dos municípios com
    a coluna `cd_ibge`, em qualquer CRS; sem elas o teste de município é pulado."""
    if setores.crs is None or setores.crs.to_string() != CRS_PUBLICACAO:
        raise ValueError(f"setores precisam estar em {CRS_PUBLICACAO}, vieram em {setores.crs}")
    faltando = [c for c in COLUNAS if c not in setores.columns]
    if faltando:
        raise ValueError(f"colunas ausentes no esquema: {faltando}")

    relatorio = Relatorio()
    voc_graus = set(vocabulario()["graus"])
    setores = setores.copy()
    setores["geometry"] = setores.geometry.map(
        lambda g: g if g is None or g.is_empty or g.is_valid else _so_area_ou_ponto(make_valid(g))
    )
    relatorio.entrada.update(setores["bl_fonte"])

    manter = pd.Series(True, index=setores.index)
    vistos: set[str] = set()
    for idx, linha in setores.iterrows():
        fonte, setor = linha["bl_fonte"], linha["num_setor"]
        motivos = []
        motivo_geom = _motivo_geometria(linha.geometry)
        if motivo_geom:
            motivos.append(motivo_geom)
        if _nulo(setor) or not str(setor).strip():
            setor = None
            motivos.append("num_setor nulo")
        elif setor in vistos:
            motivos.append("num_setor repetido")
        if linha["uf"] not in UFS_VALIDAS:
            motivos.append("UF inválida")
        if not _nulo(linha["grau_risco"]) and linha["grau_risco"] not in voc_graus:
            motivos.append("grau fora do vocabulário")
        cd = None if _nulo(linha["cd_geocmu"]) else linha["cd_geocmu"]
        if cd is not None and not re.fullmatch(r"[0-9]{7}", str(cd)):
            motivos.append("cd_geocmu fora do formato")
        for motivo in motivos:
            relatorio.anotar("erro", fonte, motivo, setor)
        if motivos:
            manter.at[idx] = False
        elif setor:
            vistos.add(setor)
        if cd is None:
            relatorio.anotar("aviso", fonte, "sem código IBGE do município", setor)

    publicaveis = setores[manter].copy()
    if malhas is None:
        relatorio.globais.append("malha municipal do IBGE indisponível; teste de município pulado")
    else:
        _conferir_municipio(publicaveis, malhas, relatorio)
    relatorio.publicados.update(publicaveis["bl_fonte"])
    return publicaveis, relatorio


def _conferir_municipio(
    setores: gpd.GeoDataFrame, malhas: gpd.GeoDataFrame, relatorio: Relatorio,
) -> None:
    com_codigo = setores[setores["cd_geocmu"].notna()]
    if com_codigo.empty:
        return
    malhas_m = malhas.to_crs(CRS_METRICO).set_index("cd_ibge")
    pontos = com_codigo.to_crs(CRS_METRICO).geometry.representative_point()
    for idx, ponto in pontos.items():
        cd = str(com_codigo.at[idx, "cd_geocmu"])
        fonte, setor = com_codigo.at[idx, "bl_fonte"], com_codigo.at[idx, "num_setor"]
        if cd not in malhas_m.index:
            relatorio.anotar("aviso", fonte, "município sem malha do IBGE", setor)
            continue
        if malhas_m.geometry.loc[cd].distance(ponto) > TOLERANCIA_MUNICIPIO_M:
            relatorio.anotar("aviso", fonte, "fora do município declarado", setor)
