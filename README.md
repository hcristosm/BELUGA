<div align="center">

<img src="docs/logo/beluga-header.png" alt="Logo do BELUGA: uma beluga emitindo ondas sonoras, ao lado do nome BELUGA" width="640">

*Brazilian External Landslide & Unmapped Geohazard Archive*

**Catálogo e base padronizada de setores de risco geológico do Brasil: CPRM/SGB e mapeamentos estaduais e municipais.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](#instalação)
[![Licença](https://img.shields.io/badge/licença-AGPL--3.0-blue)](LICENSE)

</div>

---

## Sobre

A setorização de risco geológico da CPRM/SGB cobre cerca de 1.600 municípios.
Muitas cidades têm mapeamento próprio, feito pela defesa civil municipal, por
órgão estadual ou por instituto de pesquisa, que a CPRM não cobre ou cobre com
dado mais antigo. São Paulo, Rio de Janeiro, Belo Horizonte e Recife não têm
nenhum setor da CPRM.

O BELUGA faz três coisas:

1. **Cataloga** as fontes de mapeamento de risco, uma por arquivo YAML, com
   órgão, município, formato de acesso, licença e status de verificação.
2. **Coleta e padroniza** as fontes com dado aberto, no mesmo esquema de
   colunas que o [ORCA](https://github.com/hcristosm/ORCA) já usa para os
   setores da CPRM, guardando a proveniência de cada setor.
3. **Publica** um conjunto único, por UF, com os setores da CPRM e das demais
   fontes. Setores que se sobrepõem a setores da CPRM são marcados, não
   descartados.

O BELUGA é projeto irmão do ORCA e vai ser a fonte de onde o ORCA puxa os
setores de risco, os da CPRM inclusive. O contrato entre os dois está em
[docs/contrato-dados.md](docs/contrato-dados.md).

## O que está publicado

Coleta de 2026-11-21: **21.429 setores** em 27 UFs.

| Fonte | Órgão | UF | Formato de acesso | Setores | Licença |
|---|---|---|---|---:|---|
| Setorização de Risco Geológico | SGB/CPRM | 27 UFs | ArcGIS REST | 18.890 | não declarada |
| Setores de risco geológico de Juiz de Fora | SSPDC, Prefeitura de Juiz de Fora | MG | ArcGIS REST | 994 | não declarada |
| Área de Risco Geológico de Belo Horizonte | PBH (estudo UFMG de 1996) | MG | CSV com WKT (CKAN) | 665 | CC Atribuição |
| Áreas de Risco da Regional Sul do Recife | Sedec, Prefeitura do Recife | PE | GeoJSON (CKAN) | 364 | ODbL |
| Risco geológico e hidrológico de Contagem (2024) | Prefeitura de Contagem | MG | ArcGIS REST | 265 | não declarada |
| Setores de risco de Suzano (2019) | Prefeitura de Suzano | SP | ArcGIS REST (ArcGIS Online) | 178 | não declarada |
| Risco geológico do PMRR de Congonhas | Prefeitura de Congonhas | MG | ArcGIS REST (ArcGIS Online) | 73 | não declarada |

Fontes catalogadas que **não** entram na publicação:

| Fonte | Status | Motivo |
|---|---|---|
| Setorização de Contagem (MG) | ativa, `publicar: false` | republica os mesmos 28 setores da CPRM; serve de teste da sobreposição (o levantamento próprio de Contagem de 2024 é outra fonte e é publicado) |
| Risco geológico de São Paulo (GeoSampa) | não verificada | o servidor recusou a conexão; endpoint não confirmado |
| Mapeamentos do IPT no DataGEO (SP) | não verificada | serviço de dados das camadas de risco não localizado |
| GEO-RIO (Rio de Janeiro) | precisa contato | só há suscetibilidade em raster; sem setores vetoriais abertos |

Diferenças de produto que o ORCA precisa considerar:

- **Belo Horizonte** não é setorização: são áreas com tendência a risco,
  mapeadas em 1996, **sem grau de risco** (`bl_produto = area_risco_sem_grau`).
- **Recife** são **pontos** (imóveis), não polígonos, só da Regional Sul. O
  grau vem de "Área de Risco Nível N"; a correspondência com R1 a R4 é
  suposição do BELUGA, registrada no catálogo.
- **Juiz de Fora** inclui setores de grau **Baixo** (R1), que a CPRM quase não
  publica. 151 dos 994 setores se sobrepõem a setores da CPRM.
- **Contagem (2024)** são **pontos**, geológicos e hidrológicos, sem o processo:
  a tipologia fica vazia e a classe ("GEOLOGICO", "HIDROLOGICO") vai em
  `bl_tipo_or`.
- **Suzano** tem o processo em texto livre. A tipologia é extraída por
  palavra-chave ("escorreg" vira Deslizamento, "solapamento" vira Erosão de
  margem fluvial); 6 dos 178 setores não citam processo reconhecível e ficam
  sem tipologia. A CPRM não tem setores em Suzano.

## Visualizador

Um mapa para conferir o que está sendo agregado: setores por UF, filtro por
fonte, grau e sobreposição com a CPRM, ficha de cada setor com a proveniência,
o catálogo e o relatório de validação.

```bash
scripts/rodar_visualizador.sh
```

Abre em `http://localhost:8010/`. Os dados vêm de `docs/visualizador/v1/`,
gerado pelo `exportar`. Publicado, o visualizador fica no GitHub Pages junto
com os dados. Sem servidor, aberto como arquivo, o navegador bloqueia a leitura
de `v1/`; nesse caso o painel permite abrir um GeoJSON local.

## Instalação

Requer Python 3.11+.

```bash
git clone https://github.com/hcristosm/BELUGA
cd BELUGA
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Uso

```bash
# Confere todos os YAML do catálogo
python -m src.cli validar-catalogo

# Lista as fontes, o status e se entram na publicação
python -m src.cli listar-fontes

# Coleta e normaliza (todas as fontes ativas, ou uma fonte, ou algumas UFs)
python -m src.cli coletar
python -m src.cli coletar --fonte mg-juiz-de-fora-sspdc
python -m src.cli coletar --fonte br-sgb-setorizacao --ufs MG,PE

# Refaz a normalização a partir do bruto já baixado, sem acessar as fontes
python -m src.cli coletar --do-bruto

# Junta, marca sobreposição com a CPRM, valida e publica em docs/visualizador/v1/
python -m src.cli exportar
```

A coleta grava em `data/` (fora do git):

- `data/bruto/<fonte>/`: o payload como a fonte entregou, com sha256 e os
  parâmetros da requisição;
- `data/normalizado/<fonte>.gpkg`: os setores no esquema comum;
- `data/release/shp/setores_<uf>.zip`: a mesma publicação em Shapefile.

## Coleta responsável

- User-Agent identificado: `BELUGA/<versão> (+https://github.com/hcristosm/BELUGA)`.
- O `robots.txt` de cada host é lido antes da primeira requisição. Caminho
  proibido não é acessado. `Crawl-Delay` é respeitado. `robots.txt` que não
  responde bloqueia a coleta daquele host. A exceção é a API de malhas do IBGE,
  documentada para consumo automatizado, cujo `robots.txt` não responde.
- Intervalo mínimo entre requisições ao mesmo host, definido por fonte no
  catálogo (`intervalo_minimo_s`), e espera exponencial em erro transitório.
- Coleta mensal. Para mudar só o mapeamento, `coletar --do-bruto` reaproveita
  o que já foi baixado.

## Proteções contra publicar dado ruim

O BELUGA herda as regras de publicação do ORCA:

- Fonte fora do ar, resposta vazia, página HTML no lugar do arquivo e
  paginação truncada pelo ArcGIS viram erro, não um conjunto menor.
- Uma partição (fonte ou UF da CPRM) que perde mais de 10% das feições de uma
  coleta para outra é recusada e fica com o dado anterior. Remoção real e grande
  pede `coletar --aceitar-queda`.
- A publicação é recusada se tiver menos setores do que a que está no ar
  (`scripts/conferir_publicacao.py`, a mesma guarda do ORCA).
- Nenhum setor é descartado em silêncio. Erro de esquema ou de geometria tira o
  setor da publicação e entra em `relatorio_validacao.json`; aviso (setor fora
  do município declarado, município sem código IBGE) fica só no relatório.

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
  export/publicacao.py      GeoJSON por UF, manifest e Shapefile
  pipeline.py, cli.py, config.py
docs/
  visualizador/             mapa estático (HTML/JS, Leaflet); v1/ é gerado
  contrato-dados.md, esquema-setores.md, catalogo.md
```

## Documentação

- [Contrato de dados com o ORCA](docs/contrato-dados.md): formato, URLs, versionamento e como consumir.
- [Esquema dos setores](docs/esquema-setores.md): cada coluna, domínio e origem.
- [Catálogo de fontes](docs/catalogo.md): campos do YAML e como adicionar uma fonte.
- [Como contribuir](CONTRIBUTING.md).

## Limitações conhecidas

- **Licenças.** A CPRM, Juiz de Fora e Contagem não declaram licença nos
  serviços. Os dados do Recife são ODbL, que exige compartilhar o derivado sob a
  mesma licença. A licença de cada setor vai em `bl_licenca`.
- **A camada da CPRM mudou em 2026-11.** A SGB passou a escrever o município
  como `NOME (UF)`, tirou o `cd_geocmu` e renumerou os `objectid`. O BELUGA
  normaliza de volta para o formato que o ORCA usa (`munic` sem sufixo e
  `cd_geocmu` pelo IBGE). Três grafias de município da CPRM não batem com o IBGE
  e estão em `catalogo/aliases_municipios.yaml`.
- **Códigos repetidos na CPRM.** 72 códigos `num_setor` aparecem em mais de uma
  feição. Partes com os mesmos atributos viram um setor só (multipolígono). Os
  demais são setores diferentes com o mesmo código (sigla de município que
  colide, como `AL_CA_SR_01_CPRM` em Campestre e em Cajueiro) e recebem o id da
  fonte como sufixo; o código original fica em `bl_num_or`.
- **13 setores da CPRM** têm o ponto representativo a mais de 500 m do
  município declarado. Estão publicados e listados no relatório de validação.
- **A cobertura é pequena.** As capitais com maior população em área de risco
  (São Paulo, Rio de Janeiro, Salvador) ainda não têm fonte aberta confirmada.
- **Itaguaí (RJ)** publica as áreas de risco no ArcGIS Online, mas o serviço
  exige login; não entra até haver acesso aberto.

## Roadmap

- Confirmar o acesso ao GeoSampa (São Paulo) e às camadas do IPT no DataGEO.
- Pedir à GEO-RIO e à Urbel (Belo Horizonte) os setores em formato aberto.
- Coletor WFS, para fontes em GeoServer.
- Ler o BELUGA no ORCA no lugar da ingestão direta da CPRM.

## Licença

Código sob [AGPL-3.0](LICENSE). Os dados publicados seguem a licença de cada
fonte, informada no catálogo, no `manifest.json` e em cada setor (`bl_licenca`).

<div align="center">
<img src="docs/logo/beluga-icone.png" alt="Ícone do BELUGA" width="120">

Projeto irmão do [ORCA](https://github.com/hcristosm/ORCA).
</div>
