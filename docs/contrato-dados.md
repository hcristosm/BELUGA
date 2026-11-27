# Contrato de dados BELUGA → ORCA (v1)

Este documento define o que o BELUGA publica e como o ORCA (ou qualquer outro
consumidor) deve ler. Mudança incompatível neste contrato só sai numa versão
nova do caminho (`/v2/`), com o `/v1/` mantido durante a transição.

## Onde

| O quê | Onde | Para quê |
|---|---|---|
| Publicação corrente | `https://hcristosm.github.io/BELUGA/v1/` (branch `gh-pages`) | leitura diária ou mensal pelo ORCA |
| Normalizados por fonte | branch `dados-base`, `normalizado/<fonte>.gpkg` | estado entre coletas (uso interno) |
| Snapshot de cada coleta | GitHub Release `dados-AAAA-MM-DD-<run>` | reprodutibilidade: bruto, Shapefiles, agregados nacionais e manifest |
| Última coleta, URL fixa | `https://github.com/hcristosm/BELUGA/releases/latest/download/<arquivo>` | GeoPackage, GeoParquet e CSV nacionais |

No `manifest.json` publicado, `arquivos[*].url` usa esse `latest`, que é
ponteiro móvel e é o que o consumidor quer. O manifest **anexado a cada
Release** é reescrito para a tag daquela coleta, porque Release é imutável: um
ponteiro móvel ali entregaria, no mês seguinte, arquivo cujo sha256 não bate
com o manifest que a pessoa está lendo.

A Release de dados é publicada com `make_latest: true` e a de código com
`make_latest: false`, para `releases/latest/download/` resolver sempre para a
coleta mais recente.

A branch `gh-pages` guarda histórico (sem `force_orphan`). As Releases são
imutáveis.

O GitHub Pages precisa ser ligado uma vez no repositório (Settings, Pages,
branch `gh-pages`, pasta raiz).

## Arquivos em `/v1/`

| Arquivo | Conteúdo |
|---|---|
| `manifest.json` | índice da publicação; é o primeiro arquivo a ler |
| `setores_<uf>.geojson` | todos os setores da UF, de todas as fontes publicadas (UF em minúsculas) |
| `relatorio_validacao.json` | erros e avisos da validação, por fonte |
| `setores.pmtiles` | tiles vetoriais do país, camada `setores` |

Só isto vai para o Pages. O `gh-pages` guarda histórico, então cada megabyte
publicado ali fica no repositório para sempre, e o git recusa arquivo acima de
100 MiB. Vai para o Pages apenas o que precisa de URL servida com CORS: o
contrato v1 e o PMTiles, que é lido por requisição Range. Os agregados
nacionais
(`setores.gpkg`, `setores.parquet`, `setores.csv`) e os Shapefiles por UF vão
para a Release.

O PMTiles é a exceção que custa: é binário, é regerado todo mês e não ganha
nada de compressão de delta. Se a `gh-pages` ficar grande, o histórico dela é o
que se trunca, porque o dado autoritativo está na Release e na `dados-base`.

**O PMTiles não serve para contar.** Em zoom baixo o tippecanoe descarta feição
para o tile caber. A contagem autoritativa é a do `manifest.json`.

`setores_<uf>.geojson` é GeoJSON RFC 7946: WGS84 (EPSG:4326), longitude e
latitude, coordenadas com 7 casas decimais. As feições vêm ordenadas por
`num_setor`. Geometrias possíveis: `Polygon`, `MultiPolygon`, `Point`,
`MultiPoint`. As colunas estão em [esquema-setores.md](esquema-setores.md).

### manifest.json

```json
{
  "contrato": "v1",
  "versao_esquema": "1.1.0",
  "beluga_versao": "1.0.0",
  "gerado_em": "2026-11-21T19:04:33+00:00",
  "crs": "EPSG:4326",
  "total_setores": 20913,
  "colunas": ["num_setor", "uf", "munic", "..."],
  "ufs": {
    "mg": {
      "arquivo": "setores_mg.geojson",
      "setores": 5354,
      "bytes": 20012345,
      "sha256": "…",
      "por_fonte": {"br-sgb-setorizacao": 3695, "mg-belo-horizonte-pbh": 665, "mg-juiz-de-fora-sspdc": 994},
      "por_grau": {"Alto": 3212, "Baixo": 141, "Muito alto": 880, "Médio": 338, "sem grau": 783}
    }
  },
  "arquivos": {
    "pmtiles": {
      "arquivo": "setores.pmtiles",
      "url": "https://hcristosm.github.io/BELUGA/v1/setores.pmtiles",
      "bytes": …, "sha256": "…"
    },
    "gpkg":    {"arquivo": "setores.gpkg",    "url": "…/releases/latest/download/setores.gpkg",    "bytes": …, "sha256": "…"},
    "parquet": {"arquivo": "setores.parquet", "url": "…/releases/latest/download/setores.parquet", "bytes": …, "sha256": "…"},
    "csv":     {"arquivo": "setores.csv",     "url": "…/releases/latest/download/setores.csv",     "bytes": …, "sha256": "…"},
    "shapefile": {"por_uf": {"mg": {"arquivo": "setores_mg.zip", "url": "…", "bytes": …, "sha256": "…"}}}
  },
  "fontes": [
    {
      "id": "mg-juiz-de-fora-sspdc", "nome": "…", "orgao": "…", "esfera": "municipal", "uf": "MG",
      "municipios": [{"nome": "Juiz de Fora", "cd_ibge": "3136702"}],
      "produto": "setorizacao_risco", "status": "ativa", "publicada": true,
      "acesso": {"tipo": "arcgis_rest", "url": "…", "pagina": null},
      "licenca": {"nome": "não declarada", "url": null, "observacao": "…"},
      "ultima_verificacao": "2026-11-21", "coletado_em": "2026-11-21T18:42:14+00:00",
      "setores_publicados": 994, "notas": "…"
    }
  ]
}
```

`fontes` lista todo o catálogo, inclusive as fontes não publicadas (com
`publicada: false` e `setores_publicados: 0`), para o consumidor saber o que
existe e por que não veio.

`arquivos` descreve os formatos agregados, com a URL estável, o tamanho e o
sha256 de cada um. Uma chave ausente significa que aquele formato não foi
gerado nesta publicação; o arquivo correspondente também sai do ar, porque o
deploy não usa `keep_files` e remove do destino o que não está no diretório
publicado (o `force_orphan`, que a publicação também não usa, é sobre
histórico, não sobre remoção). Chave nova aqui sobe `versao_esquema` e não quebra ninguém: ignore o
que você não conhece.

## Versionamento

- `contrato` (`v1`) é a versão maior, a mesma do caminho. Sobe quando uma
  coluna muda de nome, de tipo ou de significado, ou quando um arquivo muda de
  formato.
- `versao_esquema` segue semver. Coluna nova ou campo novo no manifest sobe a
  versão menor e não quebra o consumidor: ignore o que não conhece.
- O consumidor deve conferir `contrato == "v1"` e recusar outro valor.

## Como o ORCA deve consumir

1. Baixar `manifest.json` e conferir `contrato`.
2. Para cada UF, baixar `setores_<uf>.geojson` e conferir o `sha256`. Arquivo
   que não bate é descartado, e a UF fica com o dado anterior.
3. Gravar o resultado num arquivo próprio (por exemplo `beluga_<uf>.gpkg`), e
   não dentro do `risco_<uf>.gpkg`: a poda incremental do ORCA usa `objectid`
   da SGB e apagaria todo setor sem ele.
4. Usar `num_setor` como chave. Ele é único no país inteiro, inclusive entre
   fontes.
5. Decidir a exibição pelos campos do BELUGA: `bl_fonte` (de onde veio),
   `bl_produto` (setorização, área sem grau ou ponto), `bl_sob_cp` e
   `bl_cp_frac` (relação com a CPRM).
6. Aplicar a mesma guarda que o ORCA já usa: não substituir os setores
   publicados por um conjunto menor.

Quando o ORCA passar a ler a CPRM pelo BELUGA, basta filtrar
`bl_fonte == "br-sgb-setorizacao"`: as colunas da CPRM têm os mesmos nomes e
domínios do GeoPackage que o ORCA guarda hoje no `dados-base`.

## Garantias

- Nenhuma publicação tem menos setores que a anterior (guarda em
  `scripts/conferir_publicacao.py`).
- Fonte que falhou na coleta mantém o normalizado anterior.
- O `manifest.json` é gravado por último, depois de todos os GeoJSON.
- Todo setor publicado passou pela validação de esquema e de geometria.
