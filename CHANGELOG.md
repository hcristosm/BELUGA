# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

As entradas são agrupadas por tipo (`FEATURES`, `FIXES`, `REFACTOR`, `CHORE`)
e cada item usa o prefixo do commit correspondente, no padrão
[Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/).
O projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.1.0] - 2026-11-27

### FEATURES
- feat(logo): ícone próprio para o visualizador. O `beluga-192.png` era a marca inteira, que é 2:1, encaixada num quadrado: sobravam tarjas, a beluga ficava com 20 px de altura e em 32 px virava borrão. O ícone passa a sair do recorte da cabeça com as ondas de sonar, sobre cartão arredondado claro com cantos transparentes, porque o miolo da cabeça é transparente na arte e sem fundo a beluga sumia no painel escuro. O `beluga-icone.png` vira `beluga-marca.png`, que é o que ele sempre foi, o header do README vira WebP e cai de 982 KB para 22 KB, e `scripts/gerar_logos.py` refaz tudo a partir da marca
- feat(workflow): a coleta poda as Releases de dados antigas, guardando as duas mais recentes com a tag junto. Cada coleta publica cerca de 120 MB de artefatos, e em um dia já havia três Releases empilhadas. A poda só roda depois de baixar de verdade, por range request, os arquivos nacionais de `releases/latest/download/`: apagar a coleta anterior antes dessa prova deixaria o país sem dado baixável se a Release nova tivesse subido incompleta. Release de código (`v*`) nunca entra na lista

### CHORE
- docs(readme): seção "Para quem é", com o uso por prefeituras, pesquisa e outros projetos, e seção "Como citar"
- chore(citation): nome completo do autor e ORCID no `CITATION.cff`, que antes trazia só "Hcristos" como sobrenome

## [1.0.0] - 2026-11-27

Primeira publicação do BELUGA: **21.429 setores em 27 UFs**, de 7 fontes, com
as 34 partições coletadas sem falha. Tamanhos medidos: `setores.pmtiles`
62,5 MB, `setores.gpkg` 61,3 MB, `setores.csv` 25,8 MB, `setores.parquet`
20,5 MB, e 143 MB em `v1/` no total.

### FEATURES
- feat(export): GeoPackage, GeoParquet e CSV nacionais, e PMTiles do país inteiro, além do GeoJSON e do Shapefile por UF. Cada arquivo entra no `manifest.json` com tamanho, sha256 e URL estável, na chave nova `arquivos`. O PMTiles fica no Pages, porque é lido por requisição Range e precisa de CORS; os agregados vão para a Release, porque o `gh-pages` guarda histórico e cada megabyte publicado ali fica no repositório para sempre
- feat(export): `exportar` recusa gerar a publicação quando o PMTiles foi pedido e o `tippecanoe` não está no PATH, em vez de publicar sem os tiles. Quem não tem a ferramenta passa `--sem-pmtiles` de propósito. As opções `--sem-agregados` e `--sem-pmtiles` acompanham as `--sem-malha` e `--sem-shapefile` que já existiam
- feat(ci): o workflow de coleta instala o `tippecanoe` e anexa os agregados nacionais à Release de dados. A Release de dados passa a ser a `latest`, e a de código deixa de ser, para `releases/latest/download/` resolver sempre para a coleta mais recente
- docs: `docs/usar-os-dados.md`, para quem consome: o que tem, as URLs de cada formato, como conferir o sha256, exemplos em QGIS, Python com geopandas, DuckDB, R com sf e MapLibre com PMTiles, as licenças por fonte e o versionamento. Mais `CITATION.cff`, validado contra o esquema 1.2.0
- docs: `docs/funcionamento.md`, com o caminho do dado, os comandos, a coleta responsável, as cinco camadas que protegem a publicação, os workflows passo a passo, como reverter cada situação e a ordem da primeira publicação

- feat(catalogo): três fontes municipais novas, todas em ArcGIS REST: Suzano/SP (178 setores de 2019, município sem setor da CPRM), Congonhas/MG (73 setores do PMRR) e o levantamento próprio de Contagem/MG de 2024 (265 pontos geológicos e hidrológicos). A publicação passa de 20.913 para 21.429 setores
- feat(normalizacao): `tipologia.palavras_chave` extrai a tipologia de processo em texto livre por expressão regular, ignorando maiúsculas e acentos, na ordem das regras e sem repetir a mesma tipologia geral
- fix(visualizador): a ficha do setor mostra as tipologias 4 e 5
- feat(catalogo): catálogo de fontes em YAML, um arquivo por fonte, validado por JSON Schema e por regras entre arquivos (id, pasta, sigla única, código IBGE na UF declarada, vocabulário). Primeira versão com 8 fontes: CPRM/SGB, Juiz de Fora, Belo Horizonte, Recife e Contagem verificadas; GeoSampa e DataGEO/IPT não verificadas; GEO-RIO sem setores abertos
- feat(coleta): cliente HTTP com User-Agent identificado, `robots.txt` respeitado (com `Crawl-Delay`), intervalo mínimo por host e retentativa com espera exponencial; coletores `arcgis_rest` (paginação com ordem estável e conferência da contagem) e `arquivo` (recusa HTML e arquivo vazio com HTTP 200)
- feat(normalizacao): esquema comum com as colunas da CPRM que o ORCA usa e colunas de proveniência `bl_*`, todas com até 10 caracteres para sair em Shapefile. Mapeamento declarativo no YAML de cada fonte; valor sem correspondência vira nulo e aviso, com o original preservado
- feat(normalizacao): códigos de setor repetidos viram um setor só quando os atributos são iguais (setor multiparte) ou ganham o id da fonte como sufixo quando são setores diferentes; o código original fica em `bl_num_or`
- feat(cprm): marcação de sobreposição com setores da CPRM (`bl_sob_cp`, `bl_cp_set`, `bl_cp_frac`), sem descartar setor; faixas de borda abaixo de 1% da área não contam
- feat(validacao): checagem de esquema e geometria antes de publicar (erro tira o setor, aviso só reporta) e teste de município pela malha do IBGE, com relatório por fonte
- feat(export): publicação v1 com `setores_<uf>.geojson`, `manifest.json` (contagem, sha256 e fontes) e `relatorio_validacao.json`; Shapefile por UF para as Releases
- feat(visualizador): mapa estático (HTML/JS, Leaflet) para conferir os setores agregados, com filtros por fonte, grau e sobreposição, ficha de proveniência, catálogo e relatório de validação
- feat(ci): workflow mensal de coleta e publicação (dados-base, gh-pages e Release de dados) com a guarda anti-regressão do ORCA, e CI com ruff, mypy, bandit, catálogo e pytest

### FIXES
- fix(export): o PMTiles publicado era MBTiles. O tippecanoe escolhe o formato de saída pela extensão do arquivo, e o temporário da escrita atômica terminava em `.tmp`, então ele gravou SQLite com nome `.pmtiles`, saiu com 0 e o arquivo foi para o ar com tamanho plausível e conteúdo que nenhum leitor de PMTiles abre. O temporário passa a manter a extensão `.pmtiles`, e a exportação confere a assinatura `PMTiles\x03` do arquivo gerado antes de aceitá-lo, porque o formato é decidido por ferramenta externa e extensão não é prova
- fix(export): o PMTiles passa `-n` e `-N` ao tippecanoe. Sem eles, o `name` e o `description` do metadata publicado vinham do nome do arquivo de saída, ou seja, levavam o caminho do temporário
- fix(ci): o manifest anexado a cada Release de dados passa a apontar para a tag daquela coleta, não para `releases/latest/download/`. Release é imutável, e o ponteiro móvel entregaria, no mês seguinte, arquivo cujo sha256 não bate com o manifest que a pessoa está lendo
- fix(ci): a Release de dados só é criada se o empacotamento passou. A condição era `!cancelled()`, que é verdadeiro depois de um passo que falhou, então um `cp` que falhasse criaria uma Release incompleta com `make_latest: true`, e as URLs documentadas dariam 404 por um mês sem nenhuma guarda recusar
- fix(ci): `scripts/empacotar_release.py` copia exatamente o que o manifest lista e reprova se faltar algum arquivo, com teste. Era `cp` em glob, que não conferia nada. Um passo novo confere pela API que `releases/latest` é mesmo a Release de dados, porque input desconhecido em `with:` só gera warning no Actions
- fix(export): a higiene que apaga arquivo de coleta anterior só apaga o que esta execução vai regerar. Antes, `--sem-pmtiles` destruía o PMTiles publicado sem substituto
- fix(export): os cinco escritores limpam o `.tmp` em caminho de erro
- fix(export): o PMTiles deixa de usar `--extend-zooms-if-still-dropping`, que estenderia o zoom além do `-z14` justamente quando ainda há descarte. O arquivo vai para a `gh-pages`, que guarda histórico, então tamanho previsível vale mais que detalhe extra
- fix(export): `num_edif`, `num_domi` e `num_pess` saem como inteiro no CSV, não como `12.0`
- fix(export): `_gravar_atomico` grava com `encoding="utf-8"` explícito. Dependia do locale do processo, e o manifest tem acento
- fix(docs): o exemplo de `geopandas.read_parquet` por URL não funcionava sem `fsspec`, e o de MapLibre não desenhava os pontos de Recife e de Contagem, porque `type: "fill"` ignora ponto e as duas geometrias estão na mesma camada do PMTiles

### CHORE
- chore(ci): as notas da Release de código saem do `CHANGELOG.md` (`scripts/notas_release.py`, com teste), em vez das notas automáticas do GitHub, que listam commits e PRs já visíveis no histórico. Falha se a versão não tiver seção no CHANGELOG
- docs(readme): README reorganizado em torno de propósito, como usar os dados, fontes e créditos, diferenças de produto, como rodar localmente, limitações e licença. O detalhe de operação foi para `docs/funcionamento.md` e o roadmap saiu
- chore(deps): dependabot agrupado, um PR por ecossistema e por mês, em vez de um PR por dependência e por semana. Incorpora os bumps que estavam abertos: jsonschema 4.26.0, pyyaml 6.0.3, typer 0.29.2 e ruff 0.17.5
- chore(deps): `pyarrow` entra como dependência de runtime (GeoParquet) e `duckdb` como de desenvolvimento, com teste que roda a consulta que a documentação promete: exemplo que ninguém executa é exemplo que apodrece
