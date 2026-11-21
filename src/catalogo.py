"""Leitura e validação do catálogo de fontes (`catalogo/fontes/<uf>/<id>.yaml`).

O JSON Schema (`catalogo/esquema_fonte.json`) cobre a forma de cada arquivo.
O que depende de mais de um arquivo fica aqui: id igual ao nome do arquivo,
pasta igual à UF, sigla única, código IBGE existente e na UF declarada, e
tipologias e graus dentro do vocabulário.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from src.config import ALIASES_MUNICIPIOS, ESQUEMA_FONTE, FONTES_DIR, MUNICIPIOS_IBGE, VOCABULARIO


class CatalogoInvalido(ValueError):
    """O catálogo tem erro; a mensagem lista todos, não só o primeiro."""


@dataclass(frozen=True)
class Fonte:
    dados: dict[str, Any]
    arquivo: Path = field(compare=False)

    @property
    def id(self) -> str:
        return str(self.dados["id"])

    @property
    def sigla(self) -> str | None:
        return self.dados.get("sigla")

    @property
    def nome(self) -> str:
        return str(self.dados["nome"])

    @property
    def orgao(self) -> str:
        return str(self.dados["orgao"])

    @property
    def uf(self) -> str:
        return str(self.dados["abrangencia"]["uf"])

    @property
    def nacional(self) -> bool:
        return bool(self.dados["abrangencia"].get("nacional", False))

    @property
    def municipios(self) -> list[dict[str, str]]:
        return list(self.dados["abrangencia"].get("municipios") or [])

    @property
    def status(self) -> str:
        return str(self.dados["status"])

    @property
    def produto(self) -> str:
        return str(self.dados["produto"])

    @property
    def ativa(self) -> bool:
        return self.status == "ativa"

    @property
    def publicar(self) -> bool:
        """Entra na saída publicada. Fonte espelho (ex.: Contagem) fica de fora."""
        return self.ativa and bool(self.dados.get("publicar", True))

    @property
    def coletor(self) -> str | None:
        return self.dados.get("coletor")

    @property
    def acesso(self) -> dict[str, Any]:
        return dict(self.dados["acesso"])

    @property
    def mapeamento(self) -> dict[str, Any]:
        return dict(self.dados.get("mapeamento") or {})

    @property
    def licenca(self) -> str:
        return str(self.dados["licenca"]["nome"])

    @property
    def intervalo_minimo_s(self) -> float:
        return float(self.dados.get("intervalo_minimo_s", 1.0))

    @property
    def crawl_delay_s(self) -> float | None:
        robots = self.dados.get("robots") or {}
        valor = robots.get("crawl_delay_s")
        return float(valor) if valor is not None else None

    @property
    def particionada(self) -> bool:
        """Coletada uma UF por vez (a CPRM)."""
        return bool((self.dados["acesso"].get("parametros") or {}).get("particionar_por_uf"))

    @property
    def e_cprm(self) -> bool:
        return self.id == ID_FONTE_CPRM

    def resumo(self) -> dict[str, Any]:
        """O que o manifest publica sobre a fonte (sem o mapeamento interno)."""
        d = self.dados
        return {
            "id": self.id,
            "nome": self.nome,
            "orgao": self.orgao,
            "esfera": d["esfera"],
            "uf": self.uf,
            "municipios": self.municipios,
            "produto": self.produto,
            "status": self.status,
            "publicada": self.publicar,
            "acesso": {"tipo": d["acesso"]["tipo"], "url": d["acesso"]["url"],
                       "pagina": d["acesso"].get("pagina")},
            "licenca": d["licenca"],
            "ultima_verificacao": str(d["ultima_verificacao"]),
            "notas": d.get("notas"),
        }


ID_FONTE_CPRM = "br-sgb-setorizacao"


@lru_cache(maxsize=1)
def vocabulario() -> dict[str, Any]:
    return dict(yaml.safe_load(VOCABULARIO.read_text()))


@lru_cache(maxsize=1)
def municipios_ibge() -> dict[str, tuple[str, str]]:
    """`{cd_ibge: (uf, nome)}` a partir de `catalogo/municipios_ibge.json`."""
    dados = json.loads(MUNICIPIOS_IBGE.read_text())
    return {cd: (uf, nome) for cd, uf, nome in dados["municipios"]}


@lru_cache(maxsize=1)
def aliases_municipios() -> dict[str, dict[str, str]]:
    """`{uf: {nome_na_fonte: cd_ibge}}` para grafias que não batem com o IBGE."""
    if not ALIASES_MUNICIPIOS.exists():
        return {}
    dados = yaml.safe_load(ALIASES_MUNICIPIOS.read_text()) or {}
    return {uf: {str(k): str(v) for k, v in (nomes or {}).items()} for uf, nomes in dados.items()}


def _validador() -> Draft202012Validator:
    return Draft202012Validator(json.loads(ESQUEMA_FONTE.read_text()))


def _erros_semanticos(fonte: Fonte, arquivo: Path) -> list[str]:
    erros: list[str] = []
    voc = vocabulario()
    if arquivo.stem != fonte.id:
        erros.append(f"id {fonte.id!r} diferente do nome do arquivo {arquivo.name!r}")
    pasta_esperada = "br" if fonte.nacional else fonte.uf.lower()
    if arquivo.parent.name != pasta_esperada:
        erros.append(f"arquivo deveria estar em fontes/{pasta_esperada}/")
    if fonte.nacional != (fonte.uf == "BR"):
        erros.append("abrangencia: uf BR se e só se nacional: true")

    tabela = municipios_ibge()
    for mun in fonte.municipios:
        achado = tabela.get(mun["cd_ibge"])
        if achado is None:
            erros.append(f"cd_ibge {mun['cd_ibge']} não existe no IBGE")
        elif achado[0] != fonte.uf:
            erros.append(f"cd_ibge {mun['cd_ibge']} ({achado[1]}) é de {achado[0]}, não {fonte.uf}")

    for tip in fonte.dados.get("tipologias") or []:
        if tip not in voc["tipologias"]:
            erros.append(f"tipologia fora do vocabulário: {tip!r}")

    mapeamento = fonte.mapeamento
    grau = mapeamento.get("grau") or {}
    for original, destino in (grau.get("valores") or {}).items():
        if destino is not None and destino not in voc["graus"]:
            erros.append(f"grau {original!r} mapeado para valor fora do vocabulário: {destino!r}")
    tipologia = mapeamento.get("tipologia") or {}
    for original, pares in (tipologia.get("valores") or {}).items():
        for par in pares:
            if len(par) != 2:
                erros.append(f"tipologia {original!r}: cada item é [geral, específica]")
                continue
            geral, especifica = par
            if geral not in voc["tipologias"]:
                erros.append(f"tipologia {original!r} → {geral!r} fora do vocabulário")
            if especifica is not None and especifica not in voc["tipologias_especificas"]:
                erros.append(f"tipologia {original!r} → {especifica!r} fora do vocabulário")
        if len(pares) > 5:
            erros.append(f"tipologia {original!r}: a CPRM só tem 5 pares (tipolo_g1..g5)")
    for regra in tipologia.get("palavras_chave") or []:
        if not isinstance(regra, dict) or set(regra) != {"padrao", "tipologia"}:
            erros.append("palavras_chave: cada regra é {padrao, tipologia: [geral, específica]}")
            continue
        try:
            re.compile(regra["padrao"])
        except re.error as exc:
            erros.append(f"palavras_chave: padrão inválido {regra['padrao']!r}: {exc}")
        geral, especifica = (list(regra["tipologia"]) + [None, None])[:2]
        if geral not in voc["tipologias"]:
            erros.append(f"palavras_chave {regra['padrao']!r} → {geral!r} fora do vocabulário")
        if especifica is not None and especifica not in voc["tipologias_especificas"]:
            erros.append(f"palavras_chave {regra['padrao']!r} → {especifica!r} fora do vocabulário")

    if fonte.ativa and not fonte.nacional and len(fonte.municipios) != 1 and "municipio" not in mapeamento:
        erros.append("fonte ativa com mais de um município precisa de mapeamento.municipio")
    if fonte.ativa and fonte.acesso.get("url") is None:
        erros.append("fonte ativa precisa de acesso.url")
    return erros


def carregar_catalogo(diretorio: Path = FONTES_DIR) -> list[Fonte]:
    """Lê e valida todas as fontes. Levanta `CatalogoInvalido` com todos os erros."""
    validador = _validador()
    fontes: list[Fonte] = []
    erros: list[str] = []
    for arquivo in sorted(diretorio.glob("*/*.yaml")):
        rotulo = arquivo.relative_to(diretorio)
        try:
            dados = yaml.safe_load(arquivo.read_text())
        except yaml.YAMLError as exc:
            erros.append(f"{rotulo}: YAML ilegível: {exc}")
            continue
        if not isinstance(dados, dict):
            erros.append(f"{rotulo}: o arquivo precisa ser um objeto YAML")
            continue
        # YAML lê `2026-11-21` como date; o esquema espera texto.
        for chave in ("ultima_verificacao",):
            if chave in dados:
                dados[chave] = str(dados[chave])
        if isinstance(dados.get("robots"), dict) and "verificado_em" in dados["robots"]:
            dados["robots"]["verificado_em"] = str(dados["robots"]["verificado_em"])
        problemas = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '(raiz)'}: {e.message}"
            for e in validador.iter_errors(dados)
        ]
        if problemas:
            erros.extend(f"{rotulo}: {p}" for p in problemas)
            continue
        fonte = Fonte(dados, arquivo)
        erros.extend(f"{rotulo}: {p}" for p in _erros_semanticos(fonte, arquivo))
        fontes.append(fonte)

    tabela = municipios_ibge()
    for uf, apelidos in aliases_municipios().items():
        for apelido, cd in apelidos.items():
            if tabela.get(cd, ("",))[0] != uf:
                erros.append(f"aliases_municipios.yaml: {apelido!r} aponta {cd}, que não é de {uf}")

    vistos: dict[str, str] = {}
    for fonte in fontes:
        if fonte.sigla is None:
            continue
        if fonte.sigla in vistos:
            erros.append(f"sigla {fonte.sigla} repetida em {vistos[fonte.sigla]} e {fonte.id}")
        vistos[fonte.sigla] = fonte.id
    ids = [f.id for f in fontes]
    if len(ids) != len(set(ids)):
        erros.append("id de fonte repetido no catálogo")
    if ID_FONTE_CPRM not in ids:
        erros.append(f"o catálogo precisa da fonte {ID_FONTE_CPRM} (base da sobreposição)")

    if erros:
        raise CatalogoInvalido("Catálogo inválido:\n- " + "\n- ".join(erros))
    return fontes


def selecionar(fontes: list[Fonte], ids: list[str] | None) -> list[Fonte]:
    """Fontes ativas, opcionalmente filtradas por id (erro se o id não existe)."""
    if not ids:
        return [f for f in fontes if f.ativa]
    por_id = {f.id: f for f in fontes}
    faltando = [i for i in ids if i not in por_id]
    if faltando:
        raise CatalogoInvalido(f"Fonte(s) inexistente(s) no catálogo: {', '.join(faltando)}")
    inativas = [i for i in ids if not por_id[i].ativa]
    if inativas:
        raise CatalogoInvalido(f"Fonte(s) sem status ativa: {', '.join(inativas)}")
    return [por_id[i] for i in ids]
