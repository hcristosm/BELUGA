"""O empacotamento da Release de dados (scripts/empacotar_release.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.empacotar_release import (
    EmpacotamentoError,
    assets_do_manifesto,
    empacotar,
    main,
    reescrever_urls,
)

PAGES = "https://hcristosm.github.io/BELUGA/v1/"
RELEASE = "https://github.com/hcristosm/BELUGA/releases/latest/download/"


def _manifesto() -> dict:
    return {
        "contrato": "v1",
        "arquivos": {
            "pmtiles": {"arquivo": "setores.pmtiles", "url": PAGES + "setores.pmtiles"},
            "gpkg": {"arquivo": "setores.gpkg", "url": RELEASE + "setores.gpkg"},
            "parquet": {"arquivo": "setores.parquet", "url": RELEASE + "setores.parquet"},
            "csv": {"arquivo": "setores.csv", "url": RELEASE + "setores.csv"},
            "shapefile": {"por_uf": {
                "mg": {"arquivo": "setores_mg.zip", "url": RELEASE + "setores_mg.zip"},
                "pe": {"arquivo": "setores_pe.zip", "url": RELEASE + "setores_pe.zip"},
            }},
        },
    }


def _montar(tmp_path: Path, faltando: tuple[str, ...] = ()) -> tuple[Path, Path, Path]:
    manifesto = tmp_path / "manifest.json"
    manifesto.write_text(json.dumps(_manifesto()), encoding="utf-8")
    origem = tmp_path / "data" / "release"
    (origem / "shp").mkdir(parents=True)
    for nome in ("setores.gpkg", "setores.parquet", "setores.csv"):
        if nome not in faltando:
            (origem / nome).write_bytes(b"conteudo de " + nome.encode())
    for nome in ("setores_mg.zip", "setores_pe.zip"):
        if nome not in faltando:
            (origem / "shp" / nome).write_bytes(b"zip de " + nome.encode())
    return manifesto, origem, tmp_path / "release"


def test_o_pmtiles_nao_e_asset_de_release():
    """Ele é servido pelo Pages: pedir à Release faria o empacotamento reprovar."""
    assert "setores.pmtiles" not in assets_do_manifesto(_manifesto())
    assert sorted(assets_do_manifesto(_manifesto())) == [
        "setores.csv", "setores.gpkg", "setores.parquet",
        "setores_mg.zip", "setores_pe.zip",
    ]


def test_copia_tudo_que_o_manifest_lista(tmp_path):
    manifesto, origem, destino = _montar(tmp_path)
    copiados = empacotar(manifesto, origem, destino, "dados-2026-11-26-99")
    assert sorted(copiados) == sorted(assets_do_manifesto(_manifesto()))
    # Inclusive os que estavam num subdiretório (shp/).
    assert (destino / "setores_mg.zip").read_bytes() == b"zip de setores_mg.zip"
    assert (destino / "setores.gpkg").exists()


def test_arquivo_que_o_manifest_promete_e_nao_existe_reprova(tmp_path):
    """Release incompleta que vira `latest` deixa as URLs documentadas em 404.

    Nenhuma guarda pega isso depois: a guarda anti-regressão conta setores do
    manifest publicado e não olha o conteúdo da Release.
    """
    manifesto, origem, destino = _montar(tmp_path, faltando=("setores.gpkg",))
    with pytest.raises(EmpacotamentoError, match="setores.gpkg"):
        empacotar(manifesto, origem, destino, "dados-2026-11-26-99")


def test_reprova_listando_todos_os_que_faltam(tmp_path):
    manifesto, origem, destino = _montar(tmp_path, faltando=("setores.csv", "setores_pe.zip"))
    with pytest.raises(EmpacotamentoError) as exc:
        empacotar(manifesto, origem, destino, "dados-2026-11-26-99")
    assert "setores.csv" in str(exc.value) and "setores_pe.zip" in str(exc.value)


def test_o_manifest_da_release_aponta_para_a_tag_nao_para_latest(tmp_path):
    """Release é imutável: URL móvel dentro dela entregaria sha256 que não bate."""
    manifesto, origem, destino = _montar(tmp_path)
    empacotar(manifesto, origem, destino, "dados-2026-11-26-99")

    saida = json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
    assert saida["arquivos"]["gpkg"]["url"] == (
        "https://github.com/hcristosm/BELUGA/releases/download/dados-2026-11-26-99/setores.gpkg"
    )
    assert saida["arquivos"]["shapefile"]["por_uf"]["pe"]["url"].endswith(
        "/releases/download/dados-2026-11-26-99/setores_pe.zip"
    )
    # Nenhuma URL móvel sobra em lugar nenhum do manifest da Release.
    assert "releases/latest/download" not in json.dumps(saida)
    # E a URL do Pages, que não é de Release, fica intacta.
    assert saida["arquivos"]["pmtiles"]["url"] == PAGES + "setores.pmtiles"


def test_o_resto_do_manifest_nao_e_alterado(tmp_path):
    manifesto, origem, destino = _montar(tmp_path)
    empacotar(manifesto, origem, destino, "dados-2026-11-26-99")
    saida = json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
    assert saida["contrato"] == "v1"
    assert set(saida["arquivos"]) == set(_manifesto()["arquivos"])


def test_reescrever_urls_nao_mexe_em_outros_campos():
    entrada = {"url": RELEASE + "a.gpkg", "sha256": "abc", "fundo": [{"url": RELEASE + "b.csv"}]}
    saida = reescrever_urls(entrada, "t1")
    assert saida["sha256"] == "abc"
    assert saida["url"].endswith("/releases/download/t1/a.gpkg")
    assert saida["fundo"][0]["url"].endswith("/releases/download/t1/b.csv")


def test_main_devolve_1_e_imprime_erro_quando_falta_arquivo(tmp_path, capsys):
    manifesto, origem, destino = _montar(tmp_path, faltando=("setores.parquet",))
    codigo = main([
        "--manifesto", str(manifesto), "--origem", str(origem),
        "--destino", str(destino), "--tag", "dados-x",
    ])
    assert codigo == 1
    assert "::error::" in capsys.readouterr().err


def test_main_devolve_0_no_caminho_bom(tmp_path, capsys):
    manifesto, origem, destino = _montar(tmp_path)
    codigo = main([
        "--manifesto", str(manifesto), "--origem", str(origem),
        "--destino", str(destino), "--tag", "dados-x",
    ])
    assert codigo == 0
    assert "5 asset(s)" in capsys.readouterr().out
