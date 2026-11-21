"""Coletor de arquivo para download direto (recurso CKAN, GeoJSON, CSV).

Serve para portais de dados abertos (PBH, Recife) que publicam o recurso
como arquivo. Usa a URL de download do recurso, não a API do CKAN: o
robots.txt do Recife proíbe `/api/`.

Conferências antes de aceitar o arquivo, porque portal fora do ar costuma
responder HTTP 200 com uma página HTML:
- corpo não vazio;
- não é HTML;
- GeoJSON precisa ser JSON com `features`; CSV precisa ter o separador
  declarado na primeira linha.
"""

from __future__ import annotations

import json
from typing import Any

from src.coleta.http import Cliente, ColetaError


def _parece_html(conteudo: bytes) -> bool:
    inicio = conteudo[:512].lstrip().lower()
    return inicio.startswith((b"<!doctype html", b"<html"))


def conferir_conteudo(conteudo: bytes, formato: str | None, parametros: dict[str, Any]) -> None:
    if not conteudo.strip():
        raise ColetaError("arquivo vazio")
    if _parece_html(conteudo):
        raise ColetaError("o servidor devolveu uma página HTML no lugar do arquivo")
    if formato == "geojson":
        try:
            dados = json.loads(conteudo)
        except ValueError as exc:
            raise ColetaError(f"GeoJSON ilegível: {exc}") from exc
        if not isinstance(dados, dict) or not dados.get("features"):
            raise ColetaError("GeoJSON sem feições")
    elif formato in ("csv_wkt", "csv_xy"):
        separador = str(parametros.get("separador", ","))
        primeira = conteudo.decode("utf-8-sig", errors="replace").splitlines()[0]
        if separador not in primeira:
            raise ColetaError(f"CSV sem o separador {separador!r} no cabeçalho: {primeira[:120]!r}")


def baixar(
    cliente: Cliente, url: str, formato: str | None, parametros: dict[str, Any] | None = None,
    intervalo_minimo: float = 1.0,
) -> bytes:
    resp = cliente.get(url, intervalo_minimo=intervalo_minimo)
    conteudo = resp.content
    conferir_conteudo(conteudo, formato, parametros or {})
    return conteudo
