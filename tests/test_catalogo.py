from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from src.catalogo import CatalogoInvalido, carregar_catalogo, selecionar
from src.config import FONTES_DIR


def test_catalogo_do_repositorio_e_valido():
    fontes = carregar_catalogo()
    ids = {f.id for f in fontes}
    assert "br-sgb-setorizacao" in ids
    # Fonte sem acesso confirmado nunca pode ir para a publicação.
    for f in fontes:
        if f.status != "ativa":
            assert not f.publicar


def _catalogo_minimo(tmp_path: Path) -> Path:
    destino = tmp_path / "fontes"
    (destino / "br").mkdir(parents=True)
    (destino / "mg").mkdir()
    shutil.copy(FONTES_DIR / "br" / "br-sgb-setorizacao.yaml", destino / "br")
    shutil.copy(FONTES_DIR / "mg" / "mg-juiz-de-fora-sspdc.yaml", destino / "mg")
    return destino


def _editar(arquivo: Path, **mudancas) -> None:
    dados = yaml.safe_load(arquivo.read_text())
    dados.update(mudancas)
    arquivo.write_text(yaml.safe_dump(dados, allow_unicode=True))


def test_catalogo_minimo_carrega(tmp_path):
    assert len(carregar_catalogo(_catalogo_minimo(tmp_path))) == 2


def test_id_diferente_do_arquivo(tmp_path):
    destino = _catalogo_minimo(tmp_path)
    _editar(destino / "mg" / "mg-juiz-de-fora-sspdc.yaml", id="mg-outro-nome")
    with pytest.raises(CatalogoInvalido, match="diferente do nome do arquivo"):
        carregar_catalogo(destino)


def test_sigla_repetida(tmp_path):
    destino = _catalogo_minimo(tmp_path)
    _editar(destino / "mg" / "mg-juiz-de-fora-sspdc.yaml", sigla="CPRM")
    with pytest.raises(CatalogoInvalido, match="sigla CPRM repetida"):
        carregar_catalogo(destino)


def test_codigo_ibge_de_outra_uf(tmp_path):
    destino = _catalogo_minimo(tmp_path)
    arquivo = destino / "mg" / "mg-juiz-de-fora-sspdc.yaml"
    dados = yaml.safe_load(arquivo.read_text())
    dados["abrangencia"]["municipios"] = [{"nome": "Recife", "cd_ibge": "2611606"}]
    arquivo.write_text(yaml.safe_dump(dados, allow_unicode=True))
    with pytest.raises(CatalogoInvalido, match="é de PE, não MG"):
        carregar_catalogo(destino)


def test_tipologia_fora_do_vocabulario(tmp_path):
    destino = _catalogo_minimo(tmp_path)
    _editar(destino / "mg" / "mg-juiz-de-fora-sspdc.yaml", tipologias=["Avalanche"])
    with pytest.raises(CatalogoInvalido, match="Avalanche"):
        carregar_catalogo(destino)


def test_fonte_ativa_sem_mapeamento_viola_o_esquema(tmp_path):
    destino = _catalogo_minimo(tmp_path)
    arquivo = destino / "mg" / "mg-juiz-de-fora-sspdc.yaml"
    dados = yaml.safe_load(arquivo.read_text())
    del dados["mapeamento"]
    arquivo.write_text(yaml.safe_dump(dados, allow_unicode=True))
    with pytest.raises(CatalogoInvalido, match="mapeamento"):
        carregar_catalogo(destino)


def test_todos_os_erros_aparecem_juntos(tmp_path):
    destino = _catalogo_minimo(tmp_path)
    _editar(destino / "mg" / "mg-juiz-de-fora-sspdc.yaml", id="mg-x", tipologias=["Avalanche"])
    with pytest.raises(CatalogoInvalido) as exc:
        carregar_catalogo(destino)
    assert "Avalanche" in str(exc.value) and "nome do arquivo" in str(exc.value)


def test_selecionar_recusa_fonte_inexistente_ou_inativa():
    fontes = carregar_catalogo()
    with pytest.raises(CatalogoInvalido, match="inexistente"):
        selecionar(fontes, ["xx-nao-existe"])
    with pytest.raises(CatalogoInvalido, match="sem status ativa"):
        selecionar(fontes, ["sp-sao-paulo-geosampa"])
    assert all(f.ativa for f in selecionar(fontes, None))
