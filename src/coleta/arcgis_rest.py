"""Coletor de camadas ArcGIS REST (FeatureServer ou MapServer com `Query`).

Serve para qualquer fonte publicada em ArcGIS: CPRM/SGB, Juiz de Fora,
Contagem. A geometria vem em GeoJSON reprojetada para EPSG:4326 pelo próprio
servidor; o CRS de origem fica registrado na proveniência.

Proteções que vieram dos incidentes do ORCA com a SGB:
- paginação com `orderByFields` fixo (sem ordem o ArcGIS não garante páginas
  estáveis e a carga duplica ou pula registros);
- contagem prévia com `returnCountOnly` e conferência no fim: página cortada
  pelo servidor vira erro, não um conjunto menor publicado em silêncio;
- resultado vazio é erro: toda fonte ativa tem setores.
"""

from __future__ import annotations

import logging
from typing import Any

from src.coleta.http import Cliente, ColetaError

logger = logging.getLogger(__name__)

PAGINA_MAXIMA = 2000


def metadados_camada(cliente: Cliente, url_camada: str, intervalo_minimo: float = 1.0) -> dict:
    return cliente.get_json(url_camada, {"f": "json"}, intervalo_minimo=intervalo_minimo)


def _campo_oid(meta: dict) -> str:
    if meta.get("objectIdField"):
        return str(meta["objectIdField"])
    for campo in meta.get("fields") or []:
        if campo.get("type") == "esriFieldTypeOID":
            return str(campo["name"])
    raise ColetaError("camada sem campo de objectid; não dá para paginar com ordem estável")


def crs_da_camada(meta: dict) -> str | None:
    ref = (meta.get("extent") or {}).get("spatialReference") or meta.get("sourceSpatialReference") or {}
    wkid = ref.get("latestWkid") or ref.get("wkid")
    return f"EPSG:{wkid}" if wkid else None


def coletar_camada(
    cliente: Cliente,
    url_camada: str,
    where: str = "1=1",
    intervalo_minimo: float = 1.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Baixa todas as feições de `url_camada` que satisfazem `where`.

    Devolve `(colecao, meta)`: a FeatureCollection GeoJSON montada com as
    páginas, como o servidor as entregou, e os metadados da camada.
    """
    url_camada = url_camada.rstrip("/")
    url_query = f"{url_camada}/query"
    meta = metadados_camada(cliente, url_camada, intervalo_minimo)
    if "Query" not in str(meta.get("capabilities", "Query")):
        raise ColetaError(f"{url_camada} não aceita Query")
    oid = _campo_oid(meta)
    pagina = min(int(meta.get("maxRecordCount") or 1000), PAGINA_MAXIMA)

    contagem = cliente.get_json(
        url_query, {"where": where, "returnCountOnly": "true", "f": "json"},
        intervalo_minimo=intervalo_minimo,
    )
    total = contagem.get("count")
    if not isinstance(total, int):
        raise ColetaError(f"{url_camada}: contagem ilegível: {contagem!r}")
    if total == 0:
        raise ColetaError(f"{url_camada} ({where}) voltou vazia")

    features: list[dict] = []
    ids: set[Any] = set()
    offset = 0
    while len(features) < total:
        payload = cliente.get_json(
            url_query,
            {
                "where": where, "outFields": "*", "outSR": "4326", "f": "geojson",
                "orderByFields": oid, "resultOffset": offset, "resultRecordCount": pagina,
            },
            intervalo_minimo=intervalo_minimo,
        )
        pagina_features = payload.get("features") or []
        if not pagina_features:
            break
        for feicao in pagina_features:
            chave = feicao.get("id", (feicao.get("properties") or {}).get(oid))
            if chave is not None and chave in ids:
                raise ColetaError(f"{url_camada}: objectid {chave} repetido entre páginas")
            ids.add(chave)
        features.extend(pagina_features)
        offset += len(pagina_features)
        logger.info("%s: %d de %d feições", url_camada, len(features), total)

    if len(features) != total:
        raise ColetaError(
            f"{url_camada} ({where}): {len(features)} feições baixadas, contagem diz {total}. "
            "Paginação truncada pelo servidor; nada foi gravado."
        )
    return {"type": "FeatureCollection", "features": features}, meta
