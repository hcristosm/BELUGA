"""Monta o diretório que vai anexado à Release de dados.

Duas coisas que o `cp` solto não fazia:

1. **Copia exatamente o que o manifest lista, e reprova se faltar.** Uma
   Release incompleta que vira `latest` deixa as URLs documentadas em
   `docs/usar-os-dados.md` dando 404 até a coleta seguinte, sem que nenhuma
   guarda recuse nada: a guarda anti-regressão conta setores do manifest
   publicado e não tem opinião sobre o conteúdo da Release.

2. **Reescreve as URLs do manifest para a tag desta coleta.** No manifest
   publicado, `arquivos[*].url` aponta para `releases/latest/download/`, que é
   ponteiro móvel e é o que o consumidor quer. Dentro de uma Release, que é
   imutável, esse ponteiro mentiria: no mês seguinte entregaria arquivo cujo
   sha256 não bate com o manifest que a pessoa está lendo.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PREFIXO_MOVEL = "releases/latest/download/"


class EmpacotamentoError(RuntimeError):
    """Falta um arquivo que o manifest promete."""


def assets_do_manifesto(manifesto: dict[str, Any]) -> list[str]:
    """Nomes dos arquivos que o manifest lista como asset de Release.

    O PMTiles fica de fora: ele é servido pelo Pages, não pela Release.
    """
    arquivos = manifesto.get("arquivos") or {}
    nomes = []
    for chave, info in arquivos.items():
        if chave == "pmtiles":
            continue
        if "arquivo" in info:
            nomes.append(str(info["arquivo"]))
        for por_uf in (info.get("por_uf") or {}).values():
            nomes.append(str(por_uf["arquivo"]))
    return nomes


def reescrever_urls(valor: Any, tag: str) -> Any:
    """Troca o prefixo móvel pelo da tag, em qualquer profundidade."""
    if isinstance(valor, dict):
        return {
            chave: (
                item.replace(PREFIXO_MOVEL, f"releases/download/{tag}/")
                if chave == "url" and isinstance(item, str)
                else reescrever_urls(item, tag)
            )
            for chave, item in valor.items()
        }
    if isinstance(valor, list):
        return [reescrever_urls(item, tag) for item in valor]
    return valor


def empacotar(manifesto_path: Path, origem: Path, destino: Path, tag: str) -> list[str]:
    manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
    destino.mkdir(parents=True, exist_ok=True)

    copiados = []
    faltando = []
    for nome in assets_do_manifesto(manifesto):
        achados = [c for c in origem.rglob(nome) if c.is_file()]
        if not achados:
            faltando.append(nome)
            continue
        shutil.copy2(achados[0], destino / nome)
        copiados.append(nome)
    if faltando:
        raise EmpacotamentoError(
            f"o manifest lista {len(faltando)} arquivo(s) que não existem em {origem}: "
            + ", ".join(sorted(faltando))
        )

    (destino / "manifest.json").write_text(
        json.dumps(reescrever_urls(manifesto, tag), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return copiados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifesto", type=Path, required=True)
    parser.add_argument("--origem", type=Path, required=True, help="diretório com os agregados")
    parser.add_argument("--destino", type=Path, required=True, help="diretório que vai na Release")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)

    try:
        copiados = empacotar(args.manifesto, args.origem, args.destino, args.tag)
    except (EmpacotamentoError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"{len(copiados)} asset(s) em {args.destino}: {', '.join(sorted(copiados))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
