"""Constantes e convenções de caminho. Nenhum caminho de `data/` é montado fora daqui."""

from __future__ import annotations

from pathlib import Path

from src import __version__

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ_PROJETO / "data"
CATALOGO_DIR = RAIZ_PROJETO / "catalogo"
FONTES_DIR = CATALOGO_DIR / "fontes"
ESQUEMA_FONTE = CATALOGO_DIR / "esquema_fonte.json"
VOCABULARIO = CATALOGO_DIR / "vocabulario.yaml"
MUNICIPIOS_IBGE = CATALOGO_DIR / "municipios_ibge.json"
ALIASES_MUNICIPIOS = CATALOGO_DIR / "aliases_municipios.yaml"
VISUALIZADOR_DIR = RAIZ_PROJETO / "docs" / "visualizador"

# Versão MAIOR do contrato de dados com o ORCA. Vai no caminho publicado
# (`/v1/`); mudança incompatível sobe para `/v2/` (ver docs/contrato-dados.md).
VERSAO_CONTRATO = "v1"
VERSAO_ESQUEMA = "1.0.0"
PUBLICACAO_DIR = VISUALIZADOR_DIR / VERSAO_CONTRATO

USER_AGENT = f"BELUGA/{__version__} (+https://github.com/hcristosm/BELUGA)"

UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

CAMADA_SETORES = "setores_risco"
CRS_PUBLICACAO = "EPSG:4326"
# SIRGAS 2000 / Brasil Policônica: áreas e distâncias em metros no país todo
# (mesmo CRS métrico do ORCA).
CRS_METRICO = "EPSG:5880"


def validar_uf(uf: str) -> str:
    uf_norm = uf.strip().upper()
    if uf_norm not in UFS_VALIDAS:
        raise ValueError(f"UF inválida: {uf!r}. Use uma sigla de 2 letras, ex.: MG.")
    return uf_norm


def dir_bruto(fonte_id: str, data_dir: Path = DATA_DIR) -> Path:
    """Payload original da última coleta da fonte, sem nenhuma alteração."""
    return data_dir / "bruto" / fonte_id


def caminho_normalizado(fonte_id: str, data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "normalizado" / f"{fonte_id}.gpkg"


def caminho_proveniencia(fonte_id: str, data_dir: Path = DATA_DIR) -> Path:
    """Metadados da última coleta bem-sucedida (data, sha256, contagem)."""
    return data_dir / "normalizado" / f"{fonte_id}.json"


def dir_cache(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "cache"


def dir_shapefiles(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "release" / "shp"


def caminho_setores_uf(uf: str, saida_dir: Path = PUBLICACAO_DIR) -> Path:
    return saida_dir / f"setores_{uf.lower()}.geojson"


def caminho_manifesto(saida_dir: Path = PUBLICACAO_DIR) -> Path:
    return saida_dir / "manifest.json"


def caminho_relatorio(saida_dir: Path = PUBLICACAO_DIR) -> Path:
    return saida_dir / "relatorio_validacao.json"
