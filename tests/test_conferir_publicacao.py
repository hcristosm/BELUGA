"""Testes da guarda anti-regressão compartilhada (scripts/conferir_publicacao.py).

O que estes testes protegem não é o cálculo (trivial), e sim as duas
propriedades que os runs #23 e #29 ensinaram: toda recusa grava
`publicar=false` ANTES de sinalizar falha, e toda recusa sinaliza falha.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.conferir_publicacao import contar_json, contar_manifesto, main


@pytest.fixture
def saida(tmp_path, monkeypatch) -> Path:
    caminho = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(caminho))
    return caminho


def _publicar(saida: Path) -> str | None:
    if not saida.exists():
        return None
    for linha in saida.read_text().splitlines():
        if linha.startswith("publicar="):
            return linha.split("=", 1)[1]
    return None


def test_aprova_quando_atual_maior_ou_igual(saida):
    assert main(["--atual", "27", "--anterior", "27"]) == 0
    assert _publicar(saida) == "true"


def test_aprova_publicacao_parcial_acima_do_anterior(saida):
    assert main(["--atual", "20", "--anterior", "18"]) == 0
    assert _publicar(saida) == "true"


def test_recusa_regressao(saida):
    assert main(["--atual", "1", "--anterior", "27"]) == 1
    assert _publicar(saida) == "false"


def test_recusa_conjunto_vazio(saida):
    assert main(["--atual", "0", "--anterior", "0"]) == 1
    assert _publicar(saida) == "false"


def test_recusa_quando_anterior_indisponivel(saida):
    assert main(["--atual", "27", "--anterior", ""]) == 1
    assert _publicar(saida) == "false"


def test_recusa_quando_anterior_nao_e_inteiro(saida):
    assert main(["--atual", "27", "--anterior", "vinte"]) == 1
    assert _publicar(saida) == "false"


def test_recusa_quando_atual_indisponivel(saida):
    assert main(["--atual", "", "--anterior", "27"]) == 1
    assert _publicar(saida) == "false"


def test_conta_listas_json(tmp_path, saida):
    atual = tmp_path / "atual.json"
    atual.write_text(json.dumps(["sp", "rj", "mg"]))
    anterior = tmp_path / "anterior.json"
    anterior.write_text(json.dumps(["sp", "rj"]))
    assert main(["--atual-json", str(atual), "--anterior-json", str(anterior)]) == 0
    assert _publicar(saida) == "true"


def test_json_ausente_recusa_em_vez_de_contar_zero(tmp_path, saida):
    """Ausente é indeterminado, não zero: zero autorizaria sobrescrever no escuro."""
    assert contar_json(tmp_path / "nao_existe.json") is None
    assert main(["--atual", "1", "--anterior-json", str(tmp_path / "nao_existe.json")]) == 1
    assert _publicar(saida) == "false"


def test_json_ilegivel_recusa(tmp_path, saida):
    quebrado = tmp_path / "quebrado.json"
    quebrado.write_text("{isto não é json")
    assert contar_json(quebrado) is None
    assert main(["--atual-json", str(quebrado), "--anterior", "5"]) == 1
    assert _publicar(saida) == "false"


def test_json_que_nao_e_lista_recusa(tmp_path, saida):
    objeto = tmp_path / "objeto.json"
    objeto.write_text(json.dumps({"sp": 1}))
    assert contar_json(objeto) is None
    assert main(["--atual-json", str(objeto), "--anterior", "5"]) == 1
    assert _publicar(saida) == "false"


def test_recusa_grava_saida_antes_de_falhar(saida):
    """A ordem é o ponto: é o output que pula a publicação, não o exit code."""
    codigo = main(["--atual", "1", "--anterior", "27"])
    assert _publicar(saida) == "false", "output precisa existir mesmo com a recusa"
    assert codigo == 1, "a recusa precisa ser visível como falha do run"


def test_sem_github_output_nao_quebra(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert main(["--atual", "27", "--anterior", "27"]) == 0


def _manifesto(tmp_path: Path, nome: str, por_uf: dict[str, int], total: int | None = None) -> Path:
    caminho = tmp_path / nome
    caminho.write_text(json.dumps({
        "total_setores": sum(por_uf.values()) if total is None else total,
        "ufs": {uf: {"setores": n} for uf, n in por_uf.items()},
    }))
    return caminho


def test_manifesto_conta_setores(tmp_path, saida):
    atual = _manifesto(tmp_path, "atual.json", {"mg": 4700, "pe": 1510})
    anterior = _manifesto(tmp_path, "anterior.json", {"mg": 4700, "pe": 1500})
    assert main(["--atual-manifesto", str(atual), "--anterior-manifesto", str(anterior)]) == 0
    assert _publicar(saida) == "true"


def test_manifesto_com_menos_setores_e_recusado(tmp_path, saida):
    atual = _manifesto(tmp_path, "atual.json", {"mg": 4700})
    anterior = _manifesto(tmp_path, "anterior.json", {"mg": 4700, "pe": 1500})
    assert main(["--atual-manifesto", str(atual), "--anterior-manifesto", str(anterior)]) == 1
    assert _publicar(saida) == "false"


def test_manifesto_com_total_que_nao_bate_e_indeterminado(tmp_path):
    assert contar_manifesto(_manifesto(tmp_path, "m.json", {"mg": 10}, total=99)) is None
    assert contar_manifesto(tmp_path / "nao_existe.json") is None


def test_primeira_publicacao_usa_anterior_zero(tmp_path, saida):
    """Sem nada no ar o workflow passa --anterior 0 explícito, nunca ausência."""
    atual = _manifesto(tmp_path, "atual.json", {"mg": 10})
    assert main(["--atual-manifesto", str(atual), "--anterior", "0"]) == 0
