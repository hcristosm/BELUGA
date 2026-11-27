# Usar os dados do BELUGA

Setores de risco geológico do Brasil, da CPRM/SGB e de mapeamentos estaduais e
municipais, num esquema de colunas só. Tudo é arquivo estático: não há API, não
há chave, não há limite de requisição.

Se você vai consumir isto num programa, leia também
[contrato-dados.md](contrato-dados.md), que é o compromisso de estabilidade, e
[esquema-setores.md](esquema-setores.md), que descreve cada coluna.

## O que tem

| Formato | Para quê | Onde |
|---|---|---|
| GeoJSON por UF | ler uma UF, sem baixar o país | `https://hcristosm.github.io/BELUGA/v1/setores_<uf>.geojson` |
| `manifest.json` | índice: contagens, sha256, fontes e licenças | `https://hcristosm.github.io/BELUGA/v1/manifest.json` |
| PMTiles | mapa web sem servidor de tiles | `https://hcristosm.github.io/BELUGA/v1/setores.pmtiles` |
| GeoPackage nacional | QGIS, ogr, uma camada com o país todo | `https://github.com/hcristosm/BELUGA/releases/latest/download/setores.gpkg` |
| GeoParquet nacional | DuckDB, pandas, análise colunar | `.../releases/latest/download/setores.parquet` |
| CSV | planilha e quem só quer a tabela | `.../releases/latest/download/setores.csv` |
| Shapefile por UF | ferramenta que só lê Shapefile | `.../releases/latest/download/setores_<uf>.zip` |

`releases/latest/download/` aponta sempre para a coleta mais recente. O release
de código (`v1.0.0` e os seguintes) é publicado com `make_latest: false`
justamente para não roubar esse apelido.

O CSV não tem geometria: traz `lat` e `lon` do centroide de cada setor,
calculado em projeção métrica. Serve para localizar o setor num mapa, não para
medir área.

O PMTiles serve para desenhar. Em zoom baixo o tippecanoe descarta feição para
o tile caber, então **não conte setores no PMTiles**: a contagem autoritativa
está no `manifest.json`.

## Conferir o que você baixou

O `manifest.json` é o primeiro arquivo a ler, e traz o sha256 de cada arquivo:

```bash
curl -sO https://hcristosm.github.io/BELUGA/v1/manifest.json
jq -r '.ufs.mg | "\(.sha256)  \(.arquivo)"' manifest.json > mg.sha256
curl -sO https://hcristosm.github.io/BELUGA/v1/setores_mg.geojson
sha256sum -c mg.sha256
```

Confira também `contrato` antes de confiar no resto. Se vier diferente de
`"v1"`, pare: o significado das colunas pode ter mudado.

```bash
jq -e '.contrato == "v1"' manifest.json
```

## Python, com geopandas

```python
import geopandas as gpd

# Uma UF, direto do Pages
mg = gpd.read_file("https://hcristosm.github.io/BELUGA/v1/setores_mg.geojson")

# O país inteiro, do GeoParquet (bem menor que o GeoJSON)
br = gpd.read_parquet(
    "https://github.com/hcristosm/BELUGA/releases/latest/download/setores.parquet"
)

# Só a CPRM, que é o que o ORCA usava antes de ler o BELUGA
cprm = br[br["bl_fonte"] == "br-sgb-setorizacao"]

# Setores externos que NÃO repetem área já mapeada pela CPRM
novos = br[(br["bl_fonte"] != "br-sgb-setorizacao") & (br["bl_cp_frac"].fillna(0) <= 0.5)]

print(len(br), len(cprm), len(novos))
print(br.groupby("bl_produto")["num_setor"].count())
```

`bl_sob_cp` tem três estados, e os três importam: `True` quando a CPRM cobre ao
menos 1% da área, `False` quando foi conferido e não cobre, e **nulo nos
próprios setores da CPRM**, onde a pergunta não se aplica. Em pandas, uma coluna
booleana com nulo pode voltar como real: compare com `== True`, não com
`is True`.

## DuckDB

```sql
INSTALL spatial; LOAD spatial;
INSTALL httpfs;  LOAD httpfs;

-- Quantos setores por fonte, sem baixar o arquivo inteiro
SELECT bl_fonte, count(*) AS setores
FROM read_parquet('https://github.com/hcristosm/BELUGA/releases/latest/download/setores.parquet')
GROUP BY 1 ORDER BY 2 DESC;

-- Municípios com mais setores de grau muito alto
SELECT uf, munic, count(*) AS n
FROM read_parquet('https://github.com/hcristosm/BELUGA/releases/latest/download/setores.parquet')
WHERE grau_risco = 'Muito alto'
GROUP BY 1, 2 ORDER BY n DESC LIMIT 10;
```

Para geometria, use o CSV com `lat`/`lon` ou leia o GeoPackage com a extensão
`spatial` (`SELECT * FROM st_read('setores.gpkg')`).

## QGIS

Camada, Adicionar camada, Adicionar camada vetorial, e cole a URL do
GeoPackage em Protocolo HTTP(S). Ou baixe o arquivo e arraste para a janela.

Para estilizar por grau, use `grau_risco` com os valores `Muito alto`, `Alto`,
`Médio`, `Baixo` e nulo. Nulo não é dado faltando: é setor de fonte que mapeia
área de risco sem atribuir grau, como Belo Horizonte.

Para ver só o que a CPRM não cobre, filtre
`"bl_fonte" <> 'br-sgb-setorizacao' AND coalesce("bl_cp_frac", 0) <= 0.5`.

## R, com sf

```r
library(sf)

mg <- st_read("https://hcristosm.github.io/BELUGA/v1/setores_mg.geojson")

# O país inteiro, do GeoPackage (baixe primeiro: o sf não lê GPKG por HTTP)
download.file(
  "https://github.com/hcristosm/BELUGA/releases/latest/download/setores.gpkg",
  "setores.gpkg", mode = "wb"
)
br <- st_read("setores.gpkg", layer = "setores_risco")

table(br$bl_fonte)
```

## MapLibre, com PMTiles

```html
<script src="https://unpkg.com/maplibre-gl@5/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/pmtiles@4/dist/pmtiles.js"></script>
<script>
  const protocolo = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocolo.tile);

  const mapa = new maplibregl.Map({
    container: "mapa",
    style: "https://demotiles.maplibre.org/style.json",
    center: [-43.9, -19.9], zoom: 10,
  });

  mapa.on("load", () => {
    mapa.addSource("beluga", {
      type: "vector",
      url: "pmtiles://https://hcristosm.github.io/BELUGA/v1/setores.pmtiles",
    });
    mapa.addLayer({
      id: "setores", type: "fill", source: "beluga", "source-layer": "setores",
      paint: {
        "fill-color": [
          "match", ["get", "grau_risco"],
          "Muito alto", "#7f1d1d", "Alto", "#b45309",
          "Médio", "#a16207", "Baixo", "#4d7c0f",
          "#6b7280",
        ],
        "fill-opacity": 0.6,
      },
    });
  });
</script>
```

A camada dentro do PMTiles chama `setores`. O PMTiles é lido por requisição
Range, e por isso fica no GitHub Pages, que serve Range com CORS; a URL de
download de Release não serve para isso.

## Licenças

**As licenças são por fonte, não do conjunto.** Cada setor carrega a sua em
`bl_licenca`, e o `manifest.json` traz a de cada fonte em
`fontes[].licenca`.

Um arquivo agregado (GeoPackage, GeoParquet, CSV, PMTiles) contém fontes de
licenças diferentes, e a mais restritiva hoje é a **ODbL** dos dados do Recife,
que é compartilha-igual. Se você quer evitar essa obrigação, filtre
`bl_fonte != "pe-recife-sedec"` antes de redistribuir.

| Fonte | Licença |
|---|---|
| CPRM/SGB | não declarada no serviço |
| Belo Horizonte (PBH) | Creative Commons Atribuição |
| Recife (Sedec) | ODbL |
| Juiz de Fora, Contagem, Suzano, Congonhas | não declarada |

"Não declarada" significa que o órgão publica o dado aberto e não diz sob qual
licença. Não é permissão irrestrita, e não é proibição: é ausência de
declaração. Credite a fonte.

O código do BELUGA é AGPL-3.0-or-later, o que não se aplica aos dados.

## Versionamento

Duas versões, com papéis diferentes:

- **`contrato`** (`v1`) é a versão maior, e é a mesma do caminho publicado.
  Sobe para `v2` quando uma coluna muda de nome, de tipo ou de significado, ou
  quando um arquivo muda de formato. O `/v1/` continua servido durante a
  transição. **Confira este campo e recuse outro valor.**
- **`versao_esquema`** segue semver. Coluna nova ou campo novo no manifest sobe
  a versão menor e não quebra você: ignore o que não conhece.

## Citar

Há um [CITATION.cff](../CITATION.cff) na raiz. O GitHub monta a citação a
partir dele, no botão "Cite this repository".

Cite também a fonte primária de cada setor. O BELUGA padroniza e agrega; o
levantamento de campo é da CPRM/SGB, da prefeitura ou do órgão estadual.

## Quando alguma coisa não estiver lá

A publicação é mensal. Uma fonte que estava fora do ar na coleta mantém o dado
da coleta anterior, e isso aparece em `fontes[].coletado_em` no manifest. Fonte
catalogada que nunca foi publicada aparece com `publicada: false` e
`setores_publicados: 0`, para você saber que ela existe e por que não veio.

Erros e avisos da validação ficam em
[relatorio_validacao.json](https://hcristosm.github.io/BELUGA/v1/relatorio_validacao.json),
por fonte.
