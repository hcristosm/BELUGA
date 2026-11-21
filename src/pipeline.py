"""Coleta de uma fonte: baixa, guarda o bruto, normaliza e grava o normalizado.

Para cada partição da fonte (a UF, na CPRM; a fonte inteira, nas demais):

1. baixa o payload com o coletor do tipo da fonte;
2. grava o bruto sem alteração, com sha256 e metadados da requisição;
3. lê e normaliza;
4. confere contra a coleta anterior e só então substitui o normalizado.

A conferência do passo 4 é a mesma ideia da poda do ORCA: perder mais de
`QUEDA_MAX_FRACAO` dos setores de uma partição de uma vez é tratado como
fonte quebrada (resposta truncada, filtro mudado), e a partição fica com o
dado anterior. Uma remoção grande e real pede `--aceitar-queda`.

Falha de uma partição não derruba as outras; `coletar_fonte` devolve o
resultado de cada uma e a CLI sai com 1 se alguma falhou.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from src.catalogo import Fonte
from src.coleta import arcgis_rest, arquivo
from src.coleta.http import Cliente, ColetaError
from src.config import (
    CAMADA_SETORES,
    CRS_PUBLICACAO,
    DATA_DIR,
    UFS_VALIDAS,
    caminho_normalizado,
    caminho_proveniencia,
    dir_bruto,
)
from src.normalizacao.esquema import COLUNAS
from src.normalizacao.leitura import LeituraError, ler_bruto
from src.normalizacao.mapeamento import Proveniencia, normalizar

logger = logging.getLogger(__name__)

QUEDA_MAX_FRACAO = 0.10
QUEDA_MAX_PISO = 5
PARTICAO_UNICA = "completo"


@dataclass
class ResultadoParticao:
    particao: str
    ok: bool
    setores: int = 0
    mensagem: str = ""
    avisos: dict[str, int] = field(default_factory=dict)


def _agora() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


class EsquemaAntigo(ValueError):
    """O normalizado salvo é de uma versão anterior do esquema."""


def ler_normalizado(fonte_id: str, data_dir: Path = DATA_DIR) -> gpd.GeoDataFrame | None:
    caminho = caminho_normalizado(fonte_id, data_dir)
    if not caminho.exists():
        return None
    gdf = gpd.read_file(caminho, layer=CAMADA_SETORES)
    faltando = [c for c in COLUNAS if c not in gdf.columns]
    if faltando:
        raise EsquemaAntigo(
            f"{caminho} não tem {faltando}: é de um esquema anterior. "
            "Renormalize a fonte inteira com `coletar --do-bruto` (sem --ufs)."
        )
    return gdf[[*COLUNAS, "geometry"]]


def ler_proveniencia(fonte_id: str, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    caminho = caminho_proveniencia(fonte_id, data_dir)
    if not caminho.exists():
        return {"particoes": {}}
    try:
        dados = json.loads(caminho.read_text())
    except json.JSONDecodeError:
        logger.warning("Proveniência ilegível em %s; tratando como inexistente.", caminho)
        return {"particoes": {}}
    return dados if isinstance(dados, dict) and "particoes" in dados else {"particoes": {}}


def _baixar(fonte: Fonte, cliente: Cliente, particao: str) -> tuple[bytes, dict[str, Any]]:
    acesso = fonte.acesso
    intervalo = max(fonte.intervalo_minimo_s, fonte.crawl_delay_s or 0.0)
    if fonte.coletor == "arcgis_rest":
        parametros = acesso.get("parametros") or {}
        where = "1=1"
        if particao != PARTICAO_UNICA:
            where = f"{parametros.get('campo_uf', 'uf')}='{particao}'"
        colecao, meta = arcgis_rest.coletar_camada(cliente, acesso["url"], where, intervalo)
        conteudo = json.dumps(colecao, ensure_ascii=False).encode()
        return conteudo, {"where": where, "crs_origem": arcgis_rest.crs_da_camada(meta)}
    if fonte.coletor == "arquivo":
        conteudo = arquivo.baixar(
            cliente, acesso["url"], acesso.get("formato"), acesso.get("parametros"), intervalo,
        )
        return conteudo, {"crs_origem": acesso.get("crs_origem")}
    raise ColetaError(f"{fonte.id}: coletor não implementado: {fonte.coletor!r}")


def _ler_bruto_salvo(fonte: Fonte, particao: str, data_dir: Path) -> tuple[bytes, dict[str, Any], str, str]:
    """Bruto da última coleta, para renormalizar sem tocar no servidor."""
    destino = dir_bruto(fonte.id, data_dir)
    nome = particao.lower()
    arquivo, meta_path = destino / f"{nome}.{_extensao(fonte)}", destino / f"{nome}.json"
    if not arquivo.exists() or not meta_path.exists():
        raise ColetaError(f"sem bruto salvo em {arquivo}; rode a coleta sem --do-bruto")
    meta = json.loads(meta_path.read_text())
    conteudo = arquivo.read_bytes()
    if _sha256(conteudo) != meta.get("sha256"):
        raise ColetaError(f"{arquivo} não bate com o sha256 registrado na coleta")
    return conteudo, {"crs_origem": meta.get("crs_origem")}, meta["sha256"], meta["coletado_em"]


def _extensao(fonte: Fonte) -> str:
    formato = fonte.acesso.get("formato") or "bin"
    return {"geojson": "geojson", "csv_wkt": "csv", "csv_xy": "csv"}.get(formato, formato)


def _gravar_bruto(
    fonte: Fonte, particao: str, conteudo: bytes, extra: dict[str, Any], data_dir: Path,
    coletado_em: str,
) -> str:
    destino = dir_bruto(fonte.id, data_dir)
    destino.mkdir(parents=True, exist_ok=True)
    sha = _sha256(conteudo)
    nome = particao.lower()
    (destino / f"{nome}.{_extensao(fonte)}").write_bytes(conteudo)
    (destino / f"{nome}.json").write_text(json.dumps({
        "fonte": fonte.id, "particao": particao, "url": fonte.acesso["url"],
        "coletado_em": coletado_em, "sha256": sha, "bytes": len(conteudo), **extra,
    }, ensure_ascii=False, indent=2))
    return sha


def _conferir_queda(novos: int, anteriores: int | None, aceitar_queda: bool) -> str | None:
    if anteriores is None or aceitar_queda:
        return None
    perda = anteriores - novos
    limite = max(QUEDA_MAX_FRACAO * anteriores, QUEDA_MAX_PISO)
    if perda > limite:
        return (
            f"recusado: {novos} feições contra {anteriores} da coleta anterior "
            f"(perda de {perda}, limite {int(limite)}). Fonte provavelmente truncada; "
            "se a remoção for real, rode de novo com --aceitar-queda."
        )
    return None


def particoes(fonte: Fonte, ufs: list[str] | None) -> list[str]:
    if fonte.particionada:
        return sorted(ufs) if ufs else sorted(UFS_VALIDAS)
    if ufs and fonte.uf not in ufs:
        return []
    return [PARTICAO_UNICA]


def coletar_fonte(
    fonte: Fonte,
    cliente: Cliente,
    data_dir: Path = DATA_DIR,
    ufs: list[str] | None = None,
    aceitar_queda: bool = False,
    do_bruto: bool = False,
) -> list[ResultadoParticao]:
    """`do_bruto=True` renormaliza a partir do bruto salvo, sem rede (útil
    depois de mudar o mapeamento no catálogo)."""
    prov = ler_proveniencia(fonte.id, data_dir)
    try:
        existente = ler_normalizado(fonte.id, data_dir)
    except EsquemaAntigo:
        # Só dá para descartar o normalizado antigo quando a fonte inteira vai
        # ser refeita agora; senão as partições não coletadas sumiriam.
        if ufs is not None and fonte.particionada:
            raise
        existente = None
    resultados: list[ResultadoParticao] = []
    novas_partes: dict[str, gpd.GeoDataFrame] = {}

    for particao in particoes(fonte, ufs):
        registro = prov["particoes"].get(particao, {})
        # Proveniência anterior a `feicoes` só tinha `setores`, que então era
        # a mesma contagem (antes de unir partes de setores multipartes).
        anterior = registro.get("feicoes", registro.get("setores"))
        try:
            if do_bruto:
                conteudo, extra, sha, coletado_em = _ler_bruto_salvo(fonte, particao, data_dir)
            else:
                coletado_em = _agora()
                conteudo, extra = _baixar(fonte, cliente, particao)
                sha = _gravar_bruto(fonte, particao, conteudo, extra, data_dir, coletado_em)
            bruto = ler_bruto(
                conteudo, fonte.acesso.get("formato"), fonte.acesso.get("parametros"),
                fonte.acesso.get("crs_origem"),
            )
            normal = normalizar(bruto, fonte, Proveniencia(coletado_em, sha, extra.get("crs_origem")))
        except (ColetaError, LeituraError, KeyError, ValueError) as exc:
            logger.error("%s [%s]: %s", fonte.id, particao, exc)
            resultados.append(ResultadoParticao(particao, False, mensagem=str(exc)))
            continue

        recusa = _conferir_queda(normal.feicoes_fonte, anterior, aceitar_queda)
        if recusa:
            logger.error("%s [%s]: %s", fonte.id, particao, recusa)
            resultados.append(ResultadoParticao(particao, False, len(normal.setores), recusa))
            continue
        novas_partes[particao] = normal.setores
        prov["particoes"][particao] = {
            "coletado_em": coletado_em, "sha256": sha, "setores": len(normal.setores),
            "feicoes": normal.feicoes_fonte,
            "avisos": dict(normal.avisos),
        }
        resultados.append(ResultadoParticao(
            particao, True, len(normal.setores), "ok", dict(normal.avisos),
        ))
        for aviso, n in normal.avisos.most_common():
            logger.warning("%s [%s]: %s (%d)", fonte.id, particao, aviso, n)

    if novas_partes:
        _gravar_normalizado(fonte, existente, novas_partes, prov, data_dir)
    return resultados


def _gravar_normalizado(
    fonte: Fonte,
    existente: gpd.GeoDataFrame | None,
    novas_partes: dict[str, gpd.GeoDataFrame],
    prov: dict[str, Any],
    data_dir: Path,
) -> None:
    partes = list(novas_partes.values())
    if existente is not None and not existente.empty:
        if PARTICAO_UNICA in novas_partes:
            pass  # fonte não particionada: a coleta nova é a fonte inteira
        else:
            # Fonte por UF: mantém as UFs que não foram coletadas agora (ou falharam).
            partes.insert(0, existente[~existente["uf"].isin(list(novas_partes))])
    gdf = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=CRS_PUBLICACAO)
    gdf = gdf.sort_values("num_setor", kind="stable").reset_index(drop=True)

    caminho = caminho_normalizado(fonte.id, data_dir)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.stem + ".tmp.gpkg")
    if temporario.exists():
        temporario.unlink()
    gdf.to_file(temporario, layer=CAMADA_SETORES, driver="GPKG")
    temporario.replace(caminho)
    prov["fonte"] = fonte.id
    prov["setores"] = len(gdf)
    caminho_proveniencia(fonte.id, data_dir).write_text(
        json.dumps(prov, ensure_ascii=False, indent=2, sort_keys=True)
    )
    logger.info("%s: %d setores normalizados em %s", fonte.id, len(gdf), caminho)
