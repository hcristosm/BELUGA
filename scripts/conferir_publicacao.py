"""Guarda anti-regressão da publicação (mesma do ORCA, mais a contagem por manifest).

Invariante: nenhuma publicação destrói dado bom. O deploy sobrescreve a
branch de destino, então publicar um conjunto vazio -- ou menor do que o que
já está lá -- apaga dado bom. Foi assim que os runs #23 e #29 do ORCA
destruíram o dashboard, ambos fechando como `success`.

Publicação PARCIAL é aceitável (20 UFs frescas valem mais que nenhuma);
publicar MENOS do que já está no ar, não. Na dúvida (contagem anterior
indisponível ou ilegível), recusa.

Duas propriedades que não podem ser quebradas por nenhuma refatoração:

1. Toda recusa GRAVA `publicar=false` no `$GITHUB_OUTPUT` **antes** de sair
   com 1, nessa ordem. É o output que faz o passo de publicação ser pulado;
   se a falha viesse antes da escrita, a publicação não seria pulada.
2. Toda recusa SAI COM 1. Uma guarda que recusasse em silêncio num cron
   diário poderia bloquear a publicação por semanas sem ninguém notar --
   degradação silenciosa é justamente a doença que estes workflows existem
   para curar.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def contar_json(caminho: Path) -> int | None:
    """Conta os itens de um arquivo JSON que deve conter uma lista.

    Devolve `None` -- e não 0 -- para ausente, ilegível ou não-lista: 0
    significa "não há nada publicado, pode publicar à vontade", e tratar um
    estado indeterminado como 0 deixaria passar um conjunto de 1 UF por cima
    do que quer que esteja no ar.
    """
    try:
        dados = json.loads(caminho.read_text())
    except (OSError, ValueError):
        return None
    return len(dados) if isinstance(dados, list) else None


def contar_manifesto(caminho: Path) -> int | None:
    """`total_setores` de um manifest.json do BELUGA; `None` se indeterminado.

    Confere também que a soma por UF bate com o total: manifest com total
    escrito à mão ou cortado no meio não pode autorizar publicação.
    """
    try:
        dados = json.loads(caminho.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    total, ufs = dados.get("total_setores"), dados.get("ufs")
    if not isinstance(total, int) or isinstance(total, bool) or not isinstance(ufs, dict):
        return None
    try:
        soma = sum(int(uf["setores"]) for uf in ufs.values())
    except (TypeError, KeyError, ValueError):
        return None
    return total if soma == total else None


def _inteiro(valor: str | None) -> int | None:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _gravar_saida(publicar: bool) -> None:
    caminho = os.environ.get("GITHUB_OUTPUT")
    if caminho:
        with open(caminho, "a") as fh:
            fh.write(f"publicar={'true' if publicar else 'false'}\n")


def _recusar(mensagem: str) -> int:
    """Grava `publicar=false` e SÓ ENTÃO devolve 1. A ordem é a garantia."""
    print(f"::error::{mensagem}")
    _gravar_saida(False)
    return 1


def conferir(atual: int | None, anterior: int | None, rotulo: str) -> int:
    if anterior is None:
        return _recusar(
            "Contagem anterior indisponível ou inválida. Sem ela não dá para "
            "confirmar que não estamos regredindo -- publicação recusada."
        )
    if atual is None:
        return _recusar(
            f"Esta execução não gerou um conjunto legível de {rotulo} "
            f"(anterior={anterior}). Publicação recusada para não apagar o que está no ar."
        )

    print(f"{rotulo} nesta execução: {atual} (anterior: {anterior}).")

    if atual == 0:
        return _recusar(
            f"Conjunto atual está vazio (atual=0, anterior={anterior}). "
            "Publicação recusada para não apagar o que está no ar."
        )
    if atual < anterior:
        return _recusar(
            f"Regressão detectada: atual={atual} é menor que anterior={anterior}. "
            "Publicação recusada."
        )

    _gravar_saida(True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atual", help="Contagem desta execução (inteiro).")
    parser.add_argument("--atual-json", type=Path, help="Arquivo JSON (lista) a contar como atual.")
    parser.add_argument("--anterior", help="Contagem já publicada (inteiro).")
    parser.add_argument(
        "--anterior-json", type=Path, help="Arquivo JSON (lista) a contar como anterior."
    )
    parser.add_argument("--atual-manifesto", type=Path, help="manifest.json desta execução.")
    parser.add_argument("--anterior-manifesto", type=Path, help="manifest.json já publicado.")
    parser.add_argument("--rotulo", default="itens", help="Nome do que se conta, para as mensagens.")
    args = parser.parse_args(argv)

    if args.atual_manifesto:
        atual = contar_manifesto(args.atual_manifesto)
    elif args.atual_json:
        atual = contar_json(args.atual_json)
    else:
        atual = _inteiro(args.atual)
    if args.anterior_manifesto:
        anterior = contar_manifesto(args.anterior_manifesto)
    elif args.anterior_json:
        anterior = contar_json(args.anterior_json)
    else:
        anterior = _inteiro(args.anterior)
    return conferir(atual, anterior, args.rotulo)


if __name__ == "__main__":
    sys.exit(main())
