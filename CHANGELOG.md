# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

As entradas são agrupadas por tipo (`FEATURES`, `FIXES`, `REFACTOR`, `CHORE`)
e cada item usa o prefixo do commit correspondente, no padrão
[Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/).
O projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### FEATURES
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
