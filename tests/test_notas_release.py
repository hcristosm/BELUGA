"""A extração das notas de Release a partir do CHANGELOG."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.notas_release import NotasError, extrair, main

CHANGELOG = """# Changelog

Preâmbulo que não entra em nenhuma Release.

## [Unreleased]

## [1.1.0] - 2026-12-01

### FEATURES
- feat(x): coisa nova

## [1.0.0] - 2026-11-27

Linha de resumo da versão.

### FIXES
- fix(y): conserto

## [0.1.0] - 2026-11-21

### FEATURES
- feat(z): primeira
"""


def test_extrai_a_secao_da_versao_e_para_na_seguinte():
    corpo = extrair(CHANGELOG, "1.0.0")
    assert corpo.startswith("Linha de resumo da versão.")
    assert "fix(y): conserto" in corpo
    assert "feat(z): primeira" not in corpo
    assert "feat(x): coisa nova" not in corpo
    assert "## [" not in corpo


def test_aceita_a_versao_com_o_v_da_tag():
    assert extrair(CHANGELOG, "v1.0.0") == extrair(CHANGELOG, "1.0.0")


def test_a_ultima_secao_vai_ate_o_fim():
    corpo = extrair(CHANGELOG, "0.1.0")
    assert "feat(z): primeira" in corpo
    assert corpo.endswith("primeira")


def test_nao_pega_o_preambulo():
    assert "Preâmbulo" not in extrair(CHANGELOG, "1.1.0")


def test_versao_que_nao_existe_falha():
    """Release com corpo vazio é pior que Release que não sai."""
    with pytest.raises(NotasError, match="2.0.0"):
        extrair(CHANGELOG, "2.0.0")


def test_secao_vazia_falha():
    with pytest.raises(NotasError, match="vazia"):
        extrair(CHANGELOG, "Unreleased")


def test_versao_parecida_nao_casa():
    """`1.0` não pode casar com `1.0.0`, nem `1.0.0` com `11.0.0`."""
    with pytest.raises(NotasError):
        extrair(CHANGELOG, "1.0")


def test_main_grava_o_arquivo(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    saida = tmp_path / "notas.md"
    assert main(["--versao", "v1.0.0", "--changelog", str(changelog), "--saida", str(saida)]) == 0
    assert "fix(y): conserto" in saida.read_text(encoding="utf-8")


def test_main_devolve_1_e_imprime_erro(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert main(["--versao", "v9.9.9", "--changelog", str(changelog)]) == 1
    assert "::error::" in capsys.readouterr().err


def test_o_changelog_de_verdade_tem_a_versao_do_pyproject():
    """Bump no pyproject sem entrada no CHANGELOG quebraria a Release."""
    raiz = Path(__file__).resolve().parent.parent
    pyproject = (raiz / "pyproject.toml").read_text(encoding="utf-8")
    versao = next(
        l.split("=")[1].strip().strip('"')
        for l in pyproject.splitlines()
        if l.startswith("version =")
    )
    corpo = extrair((raiz / "CHANGELOG.md").read_text(encoding="utf-8"), versao)
    assert corpo
