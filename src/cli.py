"""CLI do BELUGA: `python -m src.cli --help`."""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from src.catalogo import CatalogoInvalido, carregar_catalogo, selecionar
from src.coleta.http import Cliente
from src.config import DATA_DIR, PUBLICACAO_DIR, validar_uf

app = typer.Typer(help="BELUGA: catálogo e base padronizada de setores de risco geológico.")


def _configurar_log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _ufs(texto: str | None) -> list[str] | None:
    if not texto:
        return None
    return [validar_uf(u) for u in texto.split(",") if u.strip()]


@app.command("validar-catalogo")
def validar_catalogo() -> None:
    """Valida todos os YAML de catalogo/fontes (esquema e regras entre arquivos)."""
    try:
        fontes = carregar_catalogo()
    except CatalogoInvalido as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    ativas = sum(f.ativa for f in fontes)
    typer.echo(f"Catálogo válido: {len(fontes)} fonte(s), {ativas} ativa(s).")


@app.command("listar-fontes")
def listar_fontes() -> None:
    """Lista as fontes do catálogo com status e se entram na publicação."""
    for fonte in carregar_catalogo():
        publica = "publica" if fonte.publicar else "-"
        typer.echo(f"{fonte.id:32} {fonte.uf:3} {fonte.status:18} {publica:8} {fonte.nome}")


@app.command()
def coletar(
    fontes: list[str] = typer.Option(None, "--fonte", help="Id da fonte (repetível). Padrão: todas as ativas."),
    ufs: str = typer.Option(None, help="Restringe a UFs, ex.: MG,PE."),
    diretorio: Path = typer.Option(DATA_DIR, help="Diretório de dados."),
    aceitar_queda: bool = typer.Option(
        False, help="Aceita perda grande de setores numa partição (remoção real na fonte).",
    ),
    do_bruto: bool = typer.Option(
        False, help="Renormaliza a partir do bruto da última coleta, sem acessar a fonte.",
    ),
    verboso: bool = typer.Option(False, "-v"),
) -> None:
    """Coleta, guarda o bruto e normaliza. Sai com 1 se alguma partição falhou."""
    from src.pipeline import coletar_fonte

    _configurar_log(verboso)
    selecionadas = selecionar(carregar_catalogo(), fontes)
    cliente = Cliente()
    falhas = 0
    for fonte in selecionadas:
        for r in coletar_fonte(fonte, cliente, diretorio, _ufs(ufs), aceitar_queda, do_bruto):
            marca = "ok   " if r.ok else "FALHA"
            typer.echo(f"{marca} {fonte.id} [{r.particao}] {r.setores} setores. {r.mensagem}")
            falhas += 0 if r.ok else 1
    if falhas:
        typer.echo(f"{falhas} partição(ões) falharam; o normalizado delas ficou como estava.", err=True)
        raise typer.Exit(1)


@app.command()
def exportar(
    diretorio: Path = typer.Option(DATA_DIR, help="Diretório de dados (normalizados)."),
    saida: Path = typer.Option(PUBLICACAO_DIR, help="Onde gravar a publicação v1."),
    sem_malha: bool = typer.Option(False, help="Pula o teste de município (não consulta o IBGE)."),
    sem_shapefile: bool = typer.Option(False, help="Não gera os Shapefiles da Release."),
    verboso: bool = typer.Option(False, "-v"),
) -> None:
    """Junta as fontes, marca sobreposição com a CPRM, valida e publica GeoJSON por UF."""
    from src.export.publicacao import ExportacaoError, juntar_fontes
    from src.export.publicacao import exportar as _exportar
    from src.validacao.malhas import obter_malhas

    _configurar_log(verboso)
    fontes = carregar_catalogo()
    malhas, avisos = None, []
    if not sem_malha:
        try:
            ufs = sorted(set(juntar_fontes(fontes, diretorio)["uf"].dropna()))
        except ExportacaoError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        malhas, sem = obter_malhas(ufs, data_dir=diretorio)
        if sem:
            avisos.append(f"malha do IBGE indisponível para: {', '.join(sem)}")
    try:
        manifesto = _exportar(
            fontes, diretorio, saida, malhas, avisos, shapefiles=not sem_shapefile,
        )
    except ExportacaoError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{manifesto['total_setores']} setores em {len(manifesto['ufs'])} UF(s) gravados em {saida}")


if __name__ == "__main__":
    app()
