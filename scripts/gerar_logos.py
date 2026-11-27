"""Gera os ícones do visualizador e o header do README a partir da marca.

Uso (precisa de Pillow, que não é dependência do projeto):

    pip install pillow
    python scripts/gerar_logos.py

A arte de origem é `docs/logo/beluga-marca.png`: a beluga com as ondas de
sonar, em PNG com fundo transparente e proporção 2:1. Ela fica versionada
porque é a origem de tudo o que este script escreve.

Saídas:

- docs/visualizador/img/beluga-{32,192}.png: cartão quadrado arredondado,
  claro, com cantos transparentes. A marca inteira é larga demais para um
  quadrado: encaixada em 192 px a beluga fica com 20 px de altura, e em 32 px
  vira borrão. O ícone sai do recorte da cabeça com as ondas, que é a parte
  que ainda se lê pequena. O cartão claro não é enfeite: o miolo da cabeça é
  transparente na arte, então sem fundo a beluga some no painel escuro do
  visualizador e sobra só o sonar laranja;
- docs/logo/beluga-header.webp: a marca com o nome escrito ao lado, para o
  topo do README, em WebP porque o PNG equivalente pesa 1 MB.

O recorte e a margem são proporcionais à caixa do conteúdo, não pixels fixos:
reexportar a arte com outra resolução ou outra folga continua funcionando.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
MARCA = RAIZ / "docs" / "logo" / "beluga-marca.png"
HEADER_ORIGEM = RAIZ / "docs" / "logo" / "beluga-header.png"
ICONES = RAIZ / "docs" / "visualizador" / "img"
LOGO = RAIZ / "docs" / "logo"

# Fração da largura da marca onde a cabeça começa. Medida na arte: à esquerda
# disso entram pedaços do corpo e da nadadeira, que cortados viram borrão.
CORTE_CABECA = 0.63
MARGEM = 0.10  # folga de cada lado do quadrado, em fração do lado
FUNDO = (247, 249, 252)  # branco levemente azulado, a barriga da beluga
RAIO_CANTO = 0.22  # raio do cartão, em fração do lado
SUPERAMOSTRA = 4  # desenha a máscara maior e reduz, para a borda não serrilhar
LADOS_ICONE = (32, 192)
LARGURA_HEADER = 1200
QUALIDADE_WEBP = 88


def _conteudo(imagem: Image.Image) -> Image.Image:
    """Recorta a imagem na caixa do que não é transparente."""
    caixa = imagem.split()[3].getbbox()
    if caixa is None:
        raise ValueError(f"arte sem pixel opaco: {imagem}")
    return imagem.crop(caixa)


def _mascara_arredondada(lado: int) -> Image.Image:
    grande = lado * SUPERAMOSTRA
    mascara = Image.new("L", (grande, grande), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (0, 0, grande - 1, grande - 1), radius=int(grande * RAIO_CANTO), fill=255
    )
    return mascara.resize((lado, lado), Image.Resampling.LANCZOS)


def _icone(marca: Image.Image) -> Image.Image:
    """Cartão quadrado arredondado com a cabeça e as ondas, centralizadas."""
    conteudo = _conteudo(marca)
    cabeca = _conteudo(
        conteudo.crop((int(conteudo.width * CORTE_CABECA), 0, conteudo.width, conteudo.height))
    )

    lado = int(max(cabeca.size) / (1 - 2 * MARGEM))
    cartao = Image.new("RGBA", (lado, lado), (*FUNDO, 255))
    cartao.alpha_composite(cabeca, ((lado - cabeca.width) // 2, (lado - cabeca.height) // 2))
    cartao.putalpha(_mascara_arredondada(lado))
    return cartao


def main() -> int:
    if not MARCA.exists():
        print(f"Arte de origem não encontrada: {MARCA}", file=sys.stderr)
        return 2

    icone = _icone(Image.open(MARCA).convert("RGBA"))
    for lado in LADOS_ICONE:
        destino = ICONES / f"beluga-{lado}.png"
        icone.resize((lado, lado), Image.Resampling.LANCZOS).save(destino, optimize=True)
        print(f"{destino.relative_to(RAIZ)} ({lado}x{lado})")

    header = Image.open(HEADER_ORIGEM)
    altura = round(header.height * LARGURA_HEADER / header.width)
    destino = LOGO / "beluga-header.webp"
    header.convert("RGB").resize(
        (LARGURA_HEADER, altura), Image.Resampling.LANCZOS
    ).save(destino, quality=QUALIDADE_WEBP, method=6)
    print(f"{destino.relative_to(RAIZ)} ({LARGURA_HEADER}x{altura})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
