"""Gera catalogo/municipios_ibge.json: código IBGE, UF e nome de todos os municípios.

Uso (só quando o IBGE criar ou renomear município; o arquivo vai no git):

    .venv/bin/python scripts/gerar_municipios_ibge.py

Serve para três coisas: conferir o `cd_ibge` declarado no catálogo, achar o
código dos setores da CPRM (a SGB tirou o `cd_geocmu` da camada em 2026-11) e
dar nome canônico ao município. Arquivo estático de propósito: a coleta não
passa a depender da API do IBGE no ar.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import MUNICIPIOS_IBGE, USER_AGENT

URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
TIMEOUT = 180


def _uf(municipio: dict) -> str:
    # Município criado depois de 2017 pode vir sem microrregião.
    micro = municipio.get("microrregiao")
    if micro:
        return str(micro["mesorregiao"]["UF"]["sigla"])
    return str(municipio["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"])


def main() -> None:
    resp = requests.get(URL, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    municipios = sorted(
        [[str(m["id"]), _uf(m), m["nome"]] for m in resp.json()],
        key=lambda linha: linha[0],
    )
    if len(municipios) < 5000:
        raise SystemExit(f"IBGE devolveu só {len(municipios)} municípios; arquivo não gravado.")
    saida = {
        "gerado_em": datetime.now(UTC).date().isoformat(),
        "fonte": "IBGE, API de localidades v1",
        "campos": ["cd_ibge", "uf", "nome"],
        "municipios": municipios,
    }
    MUNICIPIOS_IBGE.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(municipios)} municípios gravados em {MUNICIPIOS_IBGE}")


if __name__ == "__main__":
    main()
