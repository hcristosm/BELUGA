# Como o BELUGA funciona

Documento de operação: o que cada peça faz, o que protege a publicação, e como
reverter. Para consumir os dados, veja
[usar-os-dados.md](usar-os-dados.md); para o compromisso de estabilidade,
[contrato-dados.md](contrato-dados.md).

## O caminho do dado

```
catalogo/fontes/   ──→  coleta  ──→  data/bruto/        (payload como veio, com sha256)
(um YAML por fonte)      │
                         ↓
                    normalização  ──→  data/normalizado/<fonte>.gpkg
                         │                (esquema comum, 44 colunas)
                         ↓
                    sobreposição  ──→  bl_sob_cp, bl_cp_set, bl_cp_frac
                         │
                         ↓
                      validação  ──→  relatorio_validacao.json
                         │                (erro tira o setor, aviso só reporta)
                         ↓
                      publicação ──→  docs/visualizador/v1/   (Pages)
                                      data/release/           (Release)
```

Nada em `data/` vai para o git. O estado entre coletas vive na branch
`dados-base`, a publicação na `gh-pages`, e o bruto de cada coleta numa Release.

## Estrutura do repositório

```
catalogo/
  fontes/<uf>/<id>.yaml     uma fonte por arquivo (br/ para a CPRM)
  esquema_fonte.json        JSON Schema dos arquivos de fonte
  vocabulario.yaml          graus, tipologias, status e produtos
  municipios_ibge.json      códigos IBGE (gerado por scripts/gerar_municipios_ibge.py)
  aliases_municipios.yaml   grafias das fontes que não batem com o IBGE
src/
  coleta/                   um coletor por tipo de fonte (arcgis_rest, arquivo) e o cliente HTTP
  normalizacao/             leitura do bruto, esquema e mapeamento para o esquema comum
  cprm/sobreposicao.py      marcação de sobreposição com setores da CPRM
  validacao/                esquema, geometria e município (malha do IBGE)
  export/publicacao.py      GeoJSON, manifest, PMTiles, GeoPackage, GeoParquet, CSV e Shapefile
  pipeline.py, cli.py, config.py
docs/
  visualizador/             mapa estático (HTML/JS, Leaflet); v1/ é gerado
scripts/
  conferir_publicacao.py    guarda anti-regressão (a mesma do ORCA)
  empacotar_release.py      monta o diretório da Release a partir do manifest
  gerar_municipios_ibge.py  atualiza o catálogo de municípios
  rodar_visualizador.sh     servidor local do visualizador
```

Toda convenção de caminho mora em `src/config.py`. Não monte um caminho de
`data/` à mão.

## Comandos

```bash
python -m src.cli validar-catalogo   # confere todos os YAML
python -m src.cli listar-fontes      # status e se entram na publicação
python -m src.cli coletar            # todas as fontes ativas
python -m src.cli coletar --fonte mg-juiz-de-fora-sspdc
python -m src.cli coletar --ufs MG,PE
python -m src.cli coletar --do-bruto # renormaliza sem acessar a rede
python -m src.cli exportar           # junta, valida e grava todos os formatos
```

Opções do `exportar` para quando falta ferramenta ou rede:

| Opção | Quando usar |
|---|---|
| `--sem-malha` | não consulta a API de malhas do IBGE (pula o teste de município) |
| `--sem-shapefile` | não gera os zip de Shapefile |
| `--sem-agregados` | não gera GeoPackage, GeoParquet e CSV nacionais |
| `--sem-pmtiles` | não gera o PMTiles (que exige o `tippecanoe` no PATH) |

Sem `--sem-pmtiles` e sem o tippecanoe instalado, o `exportar` **falha**. Isso
é de propósito: publicar sem os tiles em silêncio deixaria no ar um PMTiles de
uma coleta anterior que o manifest não lista.

O `exportar` também confere a assinatura do arquivo que o tippecanoe gerou. O
tippecanoe escolhe o formato de saída pela **extensão** do arquivo e grava
MBTiles quando não reconhece `.pmtiles`, saindo com 0. Extensão não é prova de
formato: os bytes são.

## Coleta responsável

- User-Agent identificado: `BELUGA/<versão> (+https://github.com/hcristosm/BELUGA)`.
- O `robots.txt` de cada host é lido antes da primeira requisição, e cacheado
  por host inclusive quando falha. Caminho proibido não é acessado.
  `Crawl-Delay` é respeitado. **`robots.txt` que não responde bloqueia** a
  coleta daquele host; ausente (HTTP 4xx) libera. A única exceção é a API de
  malhas do IBGE, documentada para consumo automatizado, cujo `robots.txt` não
  responde.
- Intervalo mínimo entre requisições ao mesmo host, por fonte
  (`intervalo_minimo_s` no catálogo), e espera exponencial em erro transitório
  (5 s, 10 s, 20 s, 40 s). HTTP 4xx não é retentado.
- Coleta mensal. Para mudar só o mapeamento, `coletar --do-bruto` reaproveita o
  que já foi baixado, e recusa bruto adulterado conferindo o sha256 registrado.

## O que protege a publicação

Cinco camadas, de fora para dentro.

**1. O coletor recusa resposta suspeita.** Corpo vazio, HTML no lugar do
arquivo (portal fora do ar que responde 200 com uma página), GeoJSON sem
feições, CSV sem o separador declarado, paginação do ArcGIS truncada,
`objectid` repetido entre páginas e contagem que não bate com o
`returnCountOnly`. Camada ativa com zero feições é erro, porque toda fonte
ativa tem setores.

**2. A guarda de queda por partição.** Uma partição (uma fonte, ou uma UF da
CPRM) que perde mais de 10% das feições de uma coleta para a outra é recusada e
fica com o dado anterior. O piso é de 5 feições, para UF pequena poder perder
uma ou duas sem travar o mês. Remoção real e grande exige
`coletar --aceitar-queda`. A contagem comparada é de **feições recebidas**, não
de setores depois da união de partes, senão unir multipolígono dispararia a
guarda.

**3. Falha por partição não contamina as outras.** Fonte fora do ar mantém o
normalizado anterior, e as demais seguem. O passo de coleta no workflow usa
`continue-on-error: true` por isso, e o último passo do job reprova se alguma
partição falhou: publicação parcial é aceitável, esconder a falha não é.

**4. A validação, antes de publicar.** Erro tira o setor da publicação; aviso
só é reportado.

| Teste | Resultado se falhar |
|---|---|
| geometria não nula, não vazia, válida após `make_valid`, de tipo aceito, dentro do Brasil | erro |
| `num_setor` presente e único | erro |
| UF válida, grau no vocabulário, `cd_geocmu` com 7 dígitos | erro |
| ponto representativo a até 500 m do município declarado (malha do IBGE) | aviso |
| município com código IBGE | aviso |

Malha do IBGE indisponível não bloqueia a publicação: o teste é pulado e fica
um aviso global. Falta de insumo de conferência nunca impede publicar.

**5. A guarda anti-regressão**, em `scripts/conferir_publicacao.py`, a mesma do
ORCA. Compara o total de setores desta execução com o da publicação no ar e
recusa quando o atual é menor, quando é zero, e **quando o anterior é
indeterminado**. Esse último caso é o que importa mais: arquivo ausente,
ilegível ou que não é lista devolve `None`, não `0`, porque `0` significaria
"não há nada publicado, pode publicar à vontade" e deixaria um conjunto de uma
UF passar por cima do que estiver no ar.

Duas propriedades dessa guarda não podem mudar sem olhar
`tests/test_conferir_publicacao.py` primeiro:

1. Toda recusa grava `publicar=false` no `$GITHUB_OUTPUT` **antes** de sair com
   1, nessa ordem. É o output que faz o passo de publicação ser pulado; se a
   saída com erro viesse antes da escrita, a publicação não seria pulada.
2. Toda recusa sai com 1. Uma guarda que recusasse em silêncio num cron mensal
   poderia bloquear a publicação por meses sem ninguém notar.

E a regra que não é código: **nunca julgue um run pelo status.** Confira no log
a contagem de setores por fonte e o relatório de validação.

## Os workflows

### `ci.yml`

A cada push e PR: `ruff check src tests scripts`, `mypy src scripts`,
`bandit -c pyproject.toml -r src scripts`, `python -m src.cli validar-catalogo`
e `pytest`. Não toca em branch nenhuma e não publica nada.

### `coletar.yml`

Mensal, dia 1 às 03:00 UTC (antes do ingest do ORCA, às 06:00), e por
`workflow_dispatch` com os inputs opcionais `fontes` e `ufs`.

| # | Passo | O que faz |
|---|---|---|
| 1 | Baixar normalizados da coleta anterior | `dados-base` para `data/`. Ausente é a 1ª execução e segue; falha de rede aborta, porque sem o estado anterior a guarda de queda não tem contra o que comparar |
| 2 | Buscar a publicação anterior | busca a ref da `gh-pages` para ler o manifest com `git show` |
| 3 | Coletar e normalizar | `continue-on-error: true` |
| 4 | Instalar o tippecanoe | pelo apt. Se falhar, o job reprova em vez de publicar sem os tiles |
| 5 | Exportar publicação v1 | gera todos os formatos |
| 6 | Conferir antes de publicar | a guarda. Na 1ª execução passa `--anterior 0` explícito |
| 7 | Publicar normalizados em `dados-base` | **com histórico**, sem `force_orphan` |
| 8 | Publicar visualizador e dados no `gh-pages` | idem |
| 9 | Empacotar bruto e agregados | `scripts/empacotar_release.py` copia exatamente o que o manifest lista e reprova se faltar algum |
| 10 | Criar Release de dados | com `make_latest: true`, e só se o passo 9 passou |
| 11 | Conferir que `latest` aponta para esta Release | pela API. Input desconhecido em `with:` só gera warning, então o `make_latest` não é tomado como garantido |
| 12 | Reprovar se alguma coleta falhou | deixa o job vermelho sem desfazer a publicação |

O passo 9 existe porque uma Release incompleta que vira `latest` deixa as URLs
de [usar-os-dados.md](usar-os-dados.md) dando 404 até a coleta seguinte, e
nenhuma guarda pegaria isso: a guarda anti-regressão conta setores do manifest
publicado e não tem opinião sobre o conteúdo da Release. Ele também reescreve
as URLs do manifest que vai **dentro** da Release, trocando `latest` pela tag
daquela coleta, porque Release é imutável e ponteiro móvel ali mentiria no mês
seguinte.

Os passos 7 e 8 **não** usam `force_orphan`, de propósito: histórico é a rede
de segurança atrás da guarda, e é o que permite um `git revert`.

Isso tem um preço que vale ter medido. A publicação de 2026-11-27 ocupa **158
MB** em `v1/`, dos quais **77 MB são o `setores.pmtiles`**, que é binário e é
regerado inteiro todo mês. A coleta é mensal, então a `gh-pages` cresce por
volta de 1,9 GB por ano. O site servido é um instantâneo e fica longe do limite
de 1 GB do Pages; o que cresce é o histórico da branch. Quando incomodar, o
conserto é truncar o histórico da `gh-pages`, porque o dado autoritativo está
na Release de cada coleta e na `dados-base`. A alternativa, se o tamanho
apertar antes disso, é baixar `PMTILES_ZOOM_MAX` de 14 para 12.

### `release.yml`

Dispara em tag `v*`: `python -m build` (sdist e wheel) e cria a Release com
`make_latest: false`, para não roubar o apelido `latest` da Release de dados,
que é onde moram os arquivos nacionais.

## Como reverter

| Situação | O que fazer |
|---|---|
| A publicação no `gh-pages` saiu errada | `git revert` do commit de publicação na `gh-pages`. Ela tem histórico |
| O normalizado de uma fonte ficou ruim | `git revert` na `dados-base`, e depois `coletar --fonte <id>` |
| A coleta pegou dado errado da fonte | o bruto está na Release daquela coleta. Baixe, ponha em `data/bruto/` e rode `coletar --do-bruto` |
| Uma fonte precisa sair da publicação sem sair do catálogo | `publicar: false` no YAML dela |
| Uma fonte quebrou de vez | `status: quebrada` no YAML. Ela sai da coleta e continua listada no manifest, com `publicada: false` |

Nenhuma reversão precisa de force push. Não reescreva histórico de branch
publicada.

## Dependabot

Um PR por ecossistema (`pip` e `github-actions`), por mês, agrupado. Antes era
um PR por dependência, por semana.

## Primeira publicação de um repositório novo

Na ordem, porque cada passo depende do anterior:

1. Dispare `coletar.yml` à mão pelo `workflow_dispatch`. É esse run que **cria**
   as branches `gh-pages` e `dados-base` e a primeira Release de dados.
2. Ligue o GitHub Pages: Settings, Pages, branch `gh-pages`, pasta raiz. Só é
   possível depois do passo 1, porque a branch tem de existir. Até aqui,
   `https://hcristosm.github.io/BELUGA/v1/manifest.json` responde 404.
3. Confira as contagens no log do run, e o manifest no ar.
4. Só então crie a tag `vX.Y.Z`, que dispara o `release.yml`.
