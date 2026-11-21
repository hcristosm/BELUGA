"""Conversão de uma fonte para o esquema normalizado, guiada pelo `mapeamento` do YAML.

Chaves aceitas em `mapeamento` (ver docs/catalogo.md):

- `id_original`: nome da coluna, ou `{gerar_de: [colunas]}` quando a fonte
  não tem identificador (hash estável dos valores).
- `num_setor`: `{campo: X}` para manter o código da fonte (CPRM). Sem ele, o
  código é `{UF}_{SIGLA}_{id_original}_BELUGA`.
- `uf`, `municipio`: `{campo: X}`; `municipio` aceita `remover_sufixo_uf`.
  Sem eles, valem a UF e o único município da abrangência.
- `grau`: `{campo: X, valores: {original: grau}}`. Sem `valores`, o texto é
  comparado com o vocabulário sem diferenciar maiúsculas.
- `tipologia`: `{campo: X, valores: {original: [[geral, específica], ...]}}`,
  ou `{copiar_colunas_cprm: true}` para copiar tipolo_*/cobrade_*.
- `data_setor`: `{campo: X}`.
- `campos`: `{coluna_destino: coluna_origem | "modelo com {COLUNA}"}`.
- `copiar`: colunas com o mesmo nome na fonte e no esquema.

Valor que o mapeamento não conhece vira nulo e entra em `avisos`; o original
fica em `bl_grau_or`/`bl_tipo_or`. Nada é inventado.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry.base import BaseGeometry

from src.catalogo import Fonte, aliases_municipios, municipios_ibge, vocabulario
from src.config import CRS_PUBLICACAO
from src.normalizacao.esquema import COLUNAS, COLUNAS_NUMERICAS


@dataclass
class Proveniencia:
    coletado_em: str
    sha256: str
    crs_origem: str | None = None


@dataclass
class ResultadoNormalizacao:
    setores: gpd.GeoDataFrame
    avisos: Counter = field(default_factory=Counter)
    # Feições recebidas da fonte, antes de unir partes do mesmo setor. É o
    # número que a guarda de queda compara entre coletas.
    feicoes_fonte: int = 0


def _limpar(valor: Any) -> Any:
    """Texto aparado; texto vazio ou só espaço vira nulo (a CPRM usa ' ' como vazio)."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


def _valores(bruto: pd.DataFrame, campo: str) -> pd.Series:
    """Coluna limpa como `object`. O pandas 3 infere `str` e troca None por NaN,
    que é verdadeiro em `if valor:`; aqui nulo é sempre None."""
    return pd.Series([_limpar(v) for v in bruto[campo].tolist()], index=bruto.index, dtype=object)


def _mapear(serie: pd.Series, funcao: Any) -> pd.Series:
    """`Series.map` que mantém `object` (e None como None)."""
    return pd.Series([funcao(v) for v in serie.tolist()], index=serie.index, dtype=object)


def _texto_id(valor: Any) -> str | None:
    valor = _limpar(valor)
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor)


def chave_nome(nome: str) -> str:
    """Nome de município comparável: sem acento, maiúsculo, só letras e números."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", sem_acento.upper()).strip()


def indice_municipios() -> dict[tuple[str, str], tuple[str, str]]:
    """`{(uf, chave_nome): (cd_ibge, nome)}`, mais as grafias alternativas de
    `catalogo/aliases_municipios.yaml` (nome da fonte diferente do IBGE)."""
    tabela = municipios_ibge()
    indice = {(uf, chave_nome(nome)): (cd, nome) for cd, (uf, nome) in tabela.items()}
    for uf, apelidos in aliases_municipios().items():
        for apelido, cd in apelidos.items():
            indice[(uf, chave_nome(apelido))] = (str(cd), tabela[str(cd)][1])
    return indice


def _data_iso(valor: Any) -> str | None:
    valor = _limpar(valor)
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        data = pd.to_datetime(valor, unit="ms", errors="coerce")  # ArcGIS: ms desde 1970
    else:
        data = pd.to_datetime(str(valor), errors="coerce", dayfirst=False)
    return None if pd.isna(data) else data.strftime("%Y-%m-%d")


def tipologias_por_palavra_chave(
    texto: str, regras: list[tuple[re.Pattern[str], list[str | None]]],
) -> list[list[str | None]]:
    """Pares [geral, específica] das regras que casam com `texto`, na ordem das
    regras (a primeira é a principal). Uma geral só entra uma vez; no máximo 5,
    como tipolo_g1..g5. Acento é ignorado: 'eros' casa 'Erosão'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    pares: list[list[str | None]] = []
    vistos: set[str | None] = set()
    for padrao, (geral, especifica) in regras:
        if geral in vistos or not padrao.search(sem_acento):
            continue
        vistos.add(geral)
        pares.append([geral, especifica])
        if len(pares) == 5:
            break
    return pares


def _aplicar_modelo(modelo: str, linha: pd.Series) -> str | None:
    if "{" not in modelo:
        return _limpar(linha.get(modelo))
    valores = {k: ("" if _limpar(v) is None else str(_limpar(v))) for k, v in linha.items()}
    try:
        texto = modelo.format_map(valores)
    except KeyError as exc:
        raise KeyError(f"modelo {modelo!r} usa coluna inexistente {exc}") from exc
    # Modelo com todas as colunas vazias ("Setor . Origem: ") não informa nada.
    sobra = re.sub(r"\{[^}]*\}", "", modelo)
    return None if texto.strip() == sobra.strip() else texto.strip(" ,.")


def _geometria(geom: BaseGeometry | None) -> BaseGeometry | None:
    if geom is None or geom.is_empty:
        return geom
    return geom if geom.is_valid else make_valid(geom)


def _sanear_id(texto: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", texto).strip("-")


def normalizar(bruto: gpd.GeoDataFrame, fonte: Fonte, prov: Proveniencia) -> ResultadoNormalizacao:
    """Converte o GeoDataFrame lido da fonte para `COLUNAS` + geometria em EPSG:4326."""
    mapa = fonte.mapeamento
    voc = vocabulario()
    avisos: Counter = Counter()
    if bruto.crs is None or bruto.crs.to_string() != CRS_PUBLICACAO:
        bruto = bruto.to_crs(CRS_PUBLICACAO)
    n = len(bruto)
    saida = pd.DataFrame({c: [None] * n for c in COLUNAS}, index=bruto.index, dtype=object)

    # Identificador original
    regra_id = mapa.get("id_original")
    if isinstance(regra_id, dict) and "gerar_de" in regra_id:
        colunas = regra_id["gerar_de"]
        saida["bl_id_orig"] = [
            hashlib.sha1(
                "|".join(str(_limpar(linha.get(c)) or "") for c in colunas).encode(),
                usedforsecurity=False,
            ).hexdigest()[:12]
            for _, linha in bruto.iterrows()
        ]
    elif isinstance(regra_id, str):
        saida["bl_id_orig"] = pd.Series([_texto_id(v) for v in bruto[regra_id].tolist()], index=bruto.index, dtype=object)
    else:
        raise ValueError(f"{fonte.id}: mapeamento.id_original ausente ou inválido")

    # UF e município
    if "uf" in mapa:
        saida["uf"] = _mapear(_valores(bruto, mapa["uf"]["campo"]), lambda u: u and u.upper())
    else:
        saida["uf"] = fonte.uf
    if "municipio" in mapa:
        regra = mapa["municipio"]
        nomes = _valores(bruto, regra["campo"])
        if regra.get("remover_sufixo_uf"):
            nomes = _mapear(nomes, lambda t: t and re.sub(r"\s*\([A-Z]{2}\)\s*$", "", t))
        indice = indice_municipios()
        codigos = []
        for uf, nome in zip(saida["uf"], nomes):
            achado = indice.get((uf, chave_nome(nome))) if (uf and nome) else None
            if achado is None and nome:
                avisos[f"município sem código IBGE: {nome} ({uf})"] += 1
            codigos.append(achado[0] if achado else None)
        saida["munic"] = _mapear(nomes, lambda t: t and t.upper())
        saida["cd_geocmu"] = codigos
    else:
        unico = fonte.municipios[0]
        saida["munic"] = unico["nome"].upper()
        saida["cd_geocmu"] = unico["cd_ibge"]

    # Código do setor
    if "num_setor" in mapa:
        saida["num_setor"] = _valores(bruto, mapa["num_setor"]["campo"])
    else:
        saida["num_setor"] = [
            f"{uf}_{fonte.sigla}_{_sanear_id(i)}_BELUGA" if (uf and i) else None
            for uf, i in zip(saida["uf"], saida["bl_id_orig"])
        ]

    # Grau
    if "grau" in mapa:
        regra = mapa["grau"]
        originais = _valores(bruto, regra["campo"])
        saida["bl_grau_or"] = _mapear(originais, lambda v: None if v is None else str(v))
        # Valor listado com destino nulo é conhecido e não tem grau (ex.: "Não
        # Informado"); só valor fora da tabela vira aviso.
        tabela = regra.get("valores") or {g: g for g in voc["graus"]}
        por_chave = {str(k).strip().casefold(): v for k, v in tabela.items()}
        graus = []
        for original in saida["bl_grau_or"]:
            chave = original.casefold() if original else None
            if chave is not None and chave not in por_chave:
                avisos[f"grau sem correspondência: {original!r}"] += 1
            graus.append(por_chave.get(chave) if chave is not None else None)
        saida["grau_risco"] = graus

    # Tipologia
    regra_tip = mapa.get("tipologia") or {}
    if regra_tip.get("copiar_colunas_cprm"):
        for i in range(1, 6):
            for coluna in (f"tipolo_g{i}", f"tipolo_e{i}", f"cobrade_0{i}"):
                if coluna in bruto.columns:
                    saida[coluna] = _valores(bruto, coluna)
    elif regra_tip:
        originais = _valores(bruto, regra_tip["campo"])
        saida["bl_tipo_or"] = originais
        tabela_tip = regra_tip.get("valores") or {}
        regras = [
            (re.compile(r["padrao"], re.IGNORECASE), r["tipologia"])
            for r in regra_tip.get("palavras_chave") or []
        ]
        for idx, original in originais.items():
            if not original:
                continue
            if original in tabela_tip:
                pares = tabela_tip[original]
            elif regras:
                pares = tipologias_por_palavra_chave(original, regras)
                if not pares:
                    avisos["tipologia sem palavra-chave reconhecida"] += 1
            else:
                pares = []
                avisos[f"tipologia sem correspondência: {original!r}"] += 1
            for i, (geral, especifica) in enumerate(pares, start=1):
                saida.at[idx, f"tipolo_g{i}"] = geral
                saida.at[idx, f"tipolo_e{i}"] = especifica

    if "data_setor" in mapa:
        saida["data_setor"] = pd.Series([_data_iso(v) for v in bruto[mapa["data_setor"]["campo"]].tolist()], index=bruto.index, dtype=object)

    for destino, origem in (mapa.get("campos") or {}).items():
        saida[destino] = [_aplicar_modelo(origem, linha) for _, linha in bruto.iterrows()]
    for coluna in mapa.get("copiar") or []:
        if coluna in bruto.columns:
            saida[coluna] = _valores(bruto, coluna)
        else:
            avisos[f"coluna ausente na fonte: {coluna}"] += 1

    if saida["orgao_exec"].isna().all():
        saida["orgao_exec"] = fonte.orgao
    for coluna in COLUNAS:
        if coluna in COLUNAS_NUMERICAS:
            saida[coluna] = pd.to_numeric(saida[coluna], errors="coerce")
        else:
            # Atribuir lista a coluna também faz o pandas inferir `str` com NaN.
            saida[coluna] = _mapear(saida[coluna], _limpar)

    saida["bl_fonte"] = fonte.id
    saida["bl_coleta"] = prov.coletado_em
    saida["bl_sha256"] = prov.sha256
    saida["bl_produto"] = fonte.produto
    saida["bl_licenca"] = fonte.licenca
    saida["bl_crs_or"] = prov.crs_origem or fonte.acesso.get("crs_origem")
    saida["bl_geom_or"] = bruto.geometry.geom_type.values

    setores = gpd.GeoDataFrame(
        saida, geometry=bruto.geometry.map(_geometria).values, crs=CRS_PUBLICACAO,
    )
    setores["bl_num_or"] = setores["num_setor"]
    setores = resolver_codigos_repetidos(setores.reset_index(drop=True), avisos)
    return ResultadoNormalizacao(setores[[*COLUNAS, "geometry"]].reset_index(drop=True), avisos, n)


# Colunas que não entram na assinatura de "mesmo setor": identificam a feição,
# não o setor.
_FORA_DA_ASSINATURA = {"bl_id_orig", "bl_geom_or", "bl_num_or"}


def _texto_assinatura(valor: Any) -> str:
    return "" if _limpar(valor) is None else str(valor)


def resolver_codigos_repetidos(setores: gpd.GeoDataFrame, avisos: Counter) -> gpd.GeoDataFrame:
    """Deixa `num_setor` único sem perder setor.

    1. Feições com o mesmo código e os mesmos atributos são partes do mesmo
       setor (a CPRM divide setor multiparte em várias feições; o Recife repete
       linhas idênticas): viram uma geometria só, e `bl_id_orig` junta os ids.
    2. O que continuar repetido tem atributos diferentes, então são setores
       diferentes com o mesmo código (sigla de município que colide, como
       AL_CA_SR_01_CPRM em Campestre e em Cajueiro): o código ganha o id da
       fonte como sufixo. O código original fica sempre em `bl_num_or`.
    """
    repetidos = setores["num_setor"].duplicated(keep=False) & setores["num_setor"].notna()
    if not repetidos.any():
        return setores
    unicos = setores[~repetidos]
    colunas_assinatura = [c for c in COLUNAS if c not in _FORA_DA_ASSINATURA]
    grupo = setores[repetidos].copy()
    grupo["_assinatura"] = grupo[colunas_assinatura].apply(
        lambda linha: "|".join(_texto_assinatura(v) for v in linha), axis=1,
    )
    juntados = []
    for _, partes in grupo.groupby("_assinatura", sort=False):
        linha = partes.iloc[0].copy()
        if len(partes) > 1:
            linha["geometry"] = make_valid(partes.geometry.union_all())
            linha["bl_id_orig"] = ",".join(sorted({str(i) for i in partes["bl_id_orig"]}))
            avisos["feições com o mesmo código e atributos unidas num setor"] += len(partes) - 1
        juntados.append(linha)
    juntos = gpd.GeoDataFrame(juntados, geometry="geometry", crs=setores.crs).drop(columns="_assinatura")

    ainda = juntos["num_setor"].duplicated(keep=False)
    if ainda.any():
        juntos.loc[ainda, "num_setor"] = [
            f"{num}_{_sanear_id(str(i))}" for num, i in zip(juntos.loc[ainda, "num_setor"], juntos.loc[ainda, "bl_id_orig"])
        ]
        avisos["código repetido com atributos diferentes; sufixo com o id da fonte"] += int(ainda.sum())
    return gpd.GeoDataFrame(pd.concat([unicos, juntos], ignore_index=True), crs=setores.crs)
