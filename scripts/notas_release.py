"""Extrai de `CHANGELOG.md` a seção de uma versão, para o corpo da Release.

As notas automáticas do GitHub listam commits e PRs, que é informação que já
está no histórico. O que serve a quem lê uma Release é o CHANGELOG, que diz o
que mudou e por quê.

Falha quando a versão não está no CHANGELOG: Release com corpo vazio é pior que
Release que não sai, porque ninguém confere o corpo depois.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class NotasError(RuntimeError):
    """A versão pedida não está no CHANGELOG."""


def extrair(changelog: str, versao: str) -> str:
    """Devolve o corpo da seção `## [versao]`, sem o cabeçalho dela.

    Aceita a versão com ou sem o `v` da tag.
    """
    numero = versao.lstrip("vV")
    inicio = re.search(rf"^## \[{re.escape(numero)}\][^\n]*\n", changelog, re.MULTILINE)
    if inicio is None:
        raise NotasError(f"não há seção `## [{numero}]` no CHANGELOG")
    resto = changelog[inicio.end():]
    fim = re.search(r"^## \[", resto, re.MULTILINE)
    corpo = (resto[: fim.start()] if fim else resto).strip()
    if not corpo:
        raise NotasError(f"a seção `## [{numero}]` está vazia")
    return corpo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versao", required=True, help="1.0.0 ou v1.0.0")
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--saida", type=Path, help="arquivo a gravar; sem ele, imprime")
    args = parser.parse_args(argv)

    try:
        corpo = extrair(args.changelog.read_text(encoding="utf-8"), args.versao)
    except (NotasError, OSError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    if args.saida:
        args.saida.write_text(corpo + "\n", encoding="utf-8")
        print(f"{len(corpo)} caracteres em {args.saida}")
    else:
        print(corpo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
