# Esquema dos setores (versão 1.0.0)

Cada setor publicado tem as colunas abaixo, nesta ordem, e a geometria em
EPSG:4326. Todo nome tem no máximo 10 caracteres, o limite do DBF, para o mesmo
esquema sair em Shapefile sem truncar.

Valor ausente é `null`. Texto vazio ou só com espaço vindo da fonte vira `null`
(a CPRM usa `' '` como vazio).

## Colunas da CPRM

Mesmo nome e mesmo domínio do GeoPackage que o ORCA guarda na branch
`dados-base`. Nas outras fontes, cada coluna é preenchida pelo `mapeamento` do
catálogo, ou fica nula.

| Coluna | Tipo | Conteúdo |
|---|---|---|
| `num_setor` | texto | código único do setor no país. CPRM: o código da SGB (ex.: `MG_JUIZDEF_SR_44_CPRM`). Outras fontes: `{UF}_{SIGLA}_{id}_BELUGA` |
| `uf` | texto | sigla da UF |
| `munic` | texto | município em maiúsculas, sem o sufixo `(UF)` |
| `cd_geocmu` | texto | código IBGE do município, 7 dígitos |
| `data_setor` | texto | data do mapeamento, `AAAA-MM-DD` |
| `local` | texto | bairro ou localidade |
| `tipolo_g1` a `tipolo_g5` | texto | processo geral (vocabulário: Deslizamento, Queda, Inundação…) |
| `tipolo_e1` a `tipolo_e5` | texto | processo específico (Deslizamento planar, Queda de blocos…) |
| `cobrade_01` a `cobrade_05` | texto | código COBRADE (só a CPRM informa) |
| `descricao` | texto | descrição do setor |
| `obs_ocup` | texto | observação sobre a ocupação |
| `grau_vulne` | texto | grau de vulnerabilidade |
| `grau_risco` | texto | `Muito alto`, `Alto`, `Médio`, `Baixo` ou nulo |
| `num_edif` | número | edificações |
| `num_domi` | número | domicílios |
| `num_pess` | número | pessoas |
| `sug_interv` | texto | intervenção sugerida |
| `orgao_exec` | texto | órgão que mapeou. Sem informação na fonte, o órgão do catálogo |

Graus R1 a R4 viram `Baixo`, `Médio`, `Alto` e `Muito alto`. A correspondência
de cada fonte está no YAML dela; valor sem correspondência vira nulo e o
original fica em `bl_grau_or`.

## Colunas do BELUGA

| Coluna | Tipo | Conteúdo |
|---|---|---|
| `bl_fonte` | texto | id da fonte no catálogo |
| `bl_id_orig` | texto | identificador do registro na fonte. Vários, separados por vírgula, quando partes do mesmo setor foram unidas |
| `bl_num_or` | texto | código do setor na fonte. Difere de `num_setor` só quando o código foi desambiguado |
| `bl_coleta` | texto | instante da coleta, ISO 8601 em UTC |
| `bl_sha256` | texto | sha256 do payload bruto de onde o setor saiu (está na Release da coleta) |
| `bl_produto` | texto | `setorizacao_risco`, `area_risco_sem_grau` ou `ponto_risco` |
| `bl_licenca` | texto | licença declarada pela fonte |
| `bl_grau_or` | texto | grau como a fonte escreve (ex.: `R3`, `Área de Risco Nível 3`) |
| `bl_tipo_or` | texto | tipologia como a fonte escreve |
| `bl_geom_or` | texto | tipo da geometria na fonte |
| `bl_crs_or` | texto | CRS da fonte (o bruto está nele ou, no ArcGIS, reprojetado pelo servidor) |
| `bl_sob_cp` | booleano | a CPRM cobre ao menos 1% da área do setor (ou o ponto está num setor da CPRM). Nulo nos setores da própria CPRM |
| `bl_cp_set` | texto | `num_setor` dos setores da CPRM sobrepostos, separados por vírgula |
| `bl_cp_frac` | número | fração da área do setor coberta pela CPRM, de 0 a 1. Pode existir com `bl_sob_cp = false` quando a sobreposição é só uma faixa de borda (abaixo de 1%) |

No Shapefile, `bl_sob_cp` vai como inteiro (1, 0 ou vazio), porque o DBF não
tem booleano.

## Códigos repetidos

`num_setor` é único. Quando a fonte repete um código:

1. Feições com o mesmo código e os mesmos atributos são partes do mesmo setor e
   viram uma geometria só.
2. Feições com o mesmo código e atributos diferentes são setores diferentes e
   recebem o id da fonte como sufixo (`AL_CA_SR_01_CPRM_9915`). O código
   original fica em `bl_num_or`.

## Validação

Antes de publicar, cada setor passa por:

| Teste | Falhou |
|---|---|
| geometria não nula, não vazia, válida (após `make_valid`), de tipo aceito, dentro do Brasil | erro: sai da publicação |
| `num_setor` presente e único | erro |
| UF válida, grau no vocabulário, `cd_geocmu` com 7 dígitos | erro |
| ponto representativo a até 500 m do município declarado (malha do IBGE) | aviso: publicado e listado |
| município com código IBGE | aviso |

O resultado vai em `relatorio_validacao.json`.
