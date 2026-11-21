# Catálogo de fontes

Uma fonte por arquivo, em `catalogo/fontes/<uf>/<id>.yaml` (a CPRM, nacional,
fica em `catalogo/fontes/br/`). O formato é validado por
`catalogo/esquema_fonte.json` e por regras entre arquivos em `src/catalogo.py`:

```bash
python -m src.cli validar-catalogo
```

## Regra de entrada

Só entra no catálogo o que foi verificado: URL aberta, resposta conferida,
`robots.txt` lido. Fonte com indício de existir e sem acesso confirmado entra
com `status: nao_verificada` e sem `coletor`, e nunca é publicada. Não se
inventa URL, endpoint nem nome de camada.

## Campos

| Campo | Obrigatório | Conteúdo |
|---|---|---|
| `id` | sim | `<uf>-<nome>`, igual ao nome do arquivo |
| `sigla` | se ativa | 2 a 8 letras maiúsculas, única; entra no `num_setor` |
| `nome`, `orgao` | sim | nome do conjunto e órgão responsável |
| `esfera` | sim | `federal`, `estadual`, `municipal`, `academica` |
| `abrangencia` | sim | `uf` e `municipios` (`nome`, `cd_ibge`); `nacional: true` com `uf: BR` |
| `produto` | sim | `setorizacao_risco`, `area_risco_sem_grau`, `ponto_risco`, `suscetibilidade` |
| `tipologias` | sim | processos cobertos, do vocabulário |
| `acesso` | sim | `tipo`, `url`, `pagina`, `formato`, `crs_origem`, `parametros` |
| `licenca` | sim | `nome`, `url`, `observacao` |
| `termos_uso_url` | não | página de termos de uso |
| `robots` | não | `verificado_em`, `resultado`, `crawl_delay_s` |
| `frequencia_atualizacao` | não | `declarada` (pelo órgão) e `observada` |
| `ultima_verificacao` | sim | data da última conferência manual |
| `status` | sim | `ativa`, `quebrada`, `sem_dados_abertos`, `precisa_contato`, `nao_verificada` |
| `publicar` | não | `false` deixa a fonte ativa fora da publicação (ex.: espelho da CPRM) |
| `coletor` | se ativa | `arcgis_rest` ou `arquivo` |
| `intervalo_minimo_s` | não | segundos entre requisições ao host (padrão 1) |
| `mapeamento` | se ativa | como converter para o esquema comum (abaixo) |
| `contato`, `notas` | não | texto livre |

Tipos de acesso: `arcgis_rest` (FeatureServer ou MapServer com Query),
`arquivo` (download direto: recurso CKAN, GeoJSON, CSV), `wfs` (ainda sem
coletor), `pdf` e `visualizacao_web` (só catalogados).

Formatos de arquivo: `geojson`, `csv_wkt` (com `parametros.separador` e
`parametros.coluna_geometria`) e `csv_xy` (com `coluna_x` e `coluna_y`).

## Mapeamento

```yaml
mapeamento:
  id_original: IDENTIDADE              # coluna; ou {gerar_de: [col1, col2]} sem id na fonte
  num_setor: {campo: num_setor}        # só para manter o código da fonte (CPRM)
  uf: {campo: uf}                      # padrão: abrangencia.uf
  municipio: {campo: municipio, remover_sufixo_uf: true}   # padrão: o único município
  grau:
    campo: RISCO
    valores: {R4: Muito alto, R3: Alto, R2: Médio, R1: Baixo, "Não Informado": null}
  tipologia:
    campo: PROCESSO
    valores:
      Escorregamento Planar: [[Deslizamento, Deslizamento planar]]
      Rolamento de Blocos e Escorregamento Planar: [[Queda, null], [Deslizamento, Deslizamento planar]]
  data_setor: {campo: data_setor}
  campos:                              # destino: coluna de origem, ou modelo com {COLUNA}
    local: "{BAIRRO}"
    descricao: "Setor {NOME_SETOR}. Origem do mapeamento: {ORIGEM_MAP}"
    num_pess: POPULACAO
  copiar: [local, descricao]           # mesmas colunas na fonte e no esquema
```

- Em `grau.valores`, valor listado com destino `null` é conhecido e não tem
  grau. Valor fora da lista vira nulo e gera aviso na coleta.
- Em `tipologia.valores`, cada item é `[geral, específica]`, até 5 pares
  (`tipolo_g1` a `tipolo_g5`). Lista vazia é valor conhecido sem tipologia.
- `tipologia: {copiar_colunas_cprm: true}` copia `tipolo_*` e `cobrade_*`.
- Para processo em texto livre, `tipologia.palavras_chave` é uma lista de
  regras `{padrao: <regex>, tipologia: [geral, específica]}`. Cada regra que
  casa com o texto (sem diferenciar maiúsculas e acentos) acrescenta um par, na
  ordem das regras; a mesma geral entra uma vez só. `valores`, se houver, tem
  prioridade. Texto que nenhuma regra reconhece fica sem tipologia e conta no
  aviso agregado "tipologia sem palavra-chave reconhecida". Exemplo em
  `catalogo/fontes/sp/sp-suzano-defesa-civil.yaml`.

## Como adicionar uma fonte

1. Confirme o acesso: abra a URL, confira o formato e o `robots.txt`.
2. Crie `catalogo/fontes/<uf>/<uf>-<nome>.yaml`. Se ainda não houver acesso
   confirmado, use `status: nao_verificada` e pare aqui.
3. Para fonte ativa, escreva o `mapeamento`. Levante os valores distintos dos
   campos de grau e tipologia antes de mapear.
4. `python -m src.cli validar-catalogo`.
5. `python -m src.cli coletar --fonte <id>` e leia os avisos: valor sem
   correspondência, município sem código IBGE.
6. `python -m src.cli exportar` e confira no visualizador
   (`scripts/rodar_visualizador.sh`).
7. Abra o PR com a URL, a licença, o limite de requisições observado e como a
   fonte falha.

Município cujo nome na fonte não bate com o IBGE vai em
`catalogo/aliases_municipios.yaml`, com o código conferido.
