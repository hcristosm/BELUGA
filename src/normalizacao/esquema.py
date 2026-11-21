"""Esquema normalizado dos setores (contrato v1, ver docs/esquema-setores.md).

As colunas da CPRM têm o mesmo nome e domínio do GeoPackage que o ORCA guarda
na branch `dados-base`, para o ORCA ler o BELUGA sem adaptação. As colunas
próprias do BELUGA usam o prefixo `bl_`. Todo nome tem no máximo 10
caracteres, o limite do DBF: o mesmo esquema sai em Shapefile sem truncar.
"""

from __future__ import annotations

COLUNAS_CPRM = [
    "num_setor", "uf", "munic", "cd_geocmu", "data_setor", "local",
    *[f"tipolo_{t}{i}" for i in range(1, 6) for t in ("g", "e")],
    *[f"cobrade_0{i}" for i in range(1, 6)],
    "descricao", "obs_ocup", "grau_vulne", "grau_risco",
    "num_edif", "num_domi", "num_pess", "sug_interv", "orgao_exec",
]

COLUNAS_BELUGA = [
    "bl_fonte",    # id da fonte no catálogo
    "bl_id_orig",  # identificador do registro na fonte (vários, separados por vírgula, se unidos)
    "bl_num_or",   # código do setor na fonte; difere de num_setor só quando houve desambiguação
    "bl_coleta",   # instante da coleta (ISO 8601, UTC)
    "bl_sha256",   # sha256 do payload bruto de onde o registro saiu
    "bl_produto",  # setorizacao_risco | area_risco_sem_grau | ponto_risco
    "bl_licenca",  # licença declarada pela fonte
    "bl_grau_or",  # grau como a fonte escreve (ex.: R3)
    "bl_tipo_or",  # tipologia como a fonte escreve
    "bl_geom_or",  # tipo da geometria na fonte
    "bl_crs_or",   # CRS da fonte
    "bl_sob_cp",   # sobrepõe setor da CPRM? (nulo nos próprios setores da CPRM)
    "bl_cp_set",   # num_setor dos setores da CPRM sobrepostos, separados por vírgula
    "bl_cp_frac",  # fração da área do setor coberta pela CPRM (0 a 1)
]

COLUNAS = COLUNAS_CPRM + COLUNAS_BELUGA
COLUNAS_NUMERICAS = ["num_edif", "num_domi", "num_pess", "bl_cp_frac"]
GEOMETRIAS_ACEITAS = {"Polygon", "MultiPolygon", "Point", "MultiPoint"}

if any(len(c) > 10 for c in COLUNAS):
    raise RuntimeError("nome de coluna acima do limite de 10 caracteres do DBF")
