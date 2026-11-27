<div align="center">

<img src="docs/logo/beluga-header.webp" alt="Logo do BELUGA: uma beluga emitindo ondas sonoras, ao lado do nome BELUGA" width="640">

*Brazilian External Landslide & Unmapped Geohazard Archive*

**Catálogo e base padronizada de setores de risco geológico do Brasil: CPRM/SGB e mapeamentos estaduais e municipais.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](#rodar-localmente)
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
2. **Coleta e padroniza** as fontes com dado aberto, num esquema de colunas só,
   guardando a proveniência de cada setor.
3. **Publica** um conjunto único por UF, com os setores da CPRM e das demais
   fontes, em GeoJSON, GeoPackage, GeoParquet, PMTiles, CSV e Shapefile.
   Setores que se sobrepõem a setores da CPRM são marcados, não descartados.

É projeto irmão do [ORCA](https://github.com/hcristosm/ORCA), que lê daqui os
setores de risco, os da CPRM inclusive.

## Para quem é

- **Prefeituras e defesas civis.** Ver como o mapeamento da cidade aparece ao
  lado do da CPRM e indicar uma fonte que esteja faltando, por issue ou por um
  YAML no [catálogo](docs/catalogo.md).
- **Pesquisa.** Uma base nacional única, com a proveniência de cada setor,
  pronta para abrir no QGIS, no Python ou no R, sem juntar dezenas de arquivos
  com colunas diferentes.
- **Outros projetos.** Os arquivos são estáticos e têm um
  [contrato de estabilidade](docs/contrato-dados.md). O ORCA é o primeiro a
  usar, mas a base foi feita para servir a qualquer um.

## Usar os dados

Tudo é arquivo estático: não há API, não há chave, não há limite de requisição.
O primeiro arquivo a ler é o manifest, que traz as contagens, o sha256 de cada
arquivo e a licença de cada fonte.

```bash
curl -s https://hcristosm.github.io/BELUGA/v1/manifest.json | jq '.total_setores, .ufs.mg.setores'
```

```python
import geopandas as gpd
mg = gpd.read_file("https://hcristosm.github.io/BELUGA/v1/setores_mg.geojson")
```

**[docs/usar-os-dados.md](docs/usar-os-dados.md)** tem as URLs de cada formato e
exemplos em QGIS, Python, DuckDB, R e MapLibre, mais as licenças por fonte e
como conferir o sha256.

## Fontes e créditos

Sete fontes entram na publicação. O levantamento de campo é de cada órgão; o
BELUGA só padroniza e agrega.

| Fonte | Órgão | UF | Acesso | Setores | Licença |
|---|---|---|---|---:|---|
| Setorização de Risco Geológico | SGB/CPRM | 27 UFs | ArcGIS REST | 18.890 | não declarada |
| Setores de risco geológico de Juiz de Fora | SSPDC, Prefeitura de Juiz de Fora | MG | ArcGIS REST | 994 | não declarada |
| Área de Risco Geológico de Belo Horizonte | PBH (estudo UFMG de 1996) | MG | CSV com WKT (CKAN) | 665 | CC Atribuição |
| Áreas de Risco da Regional Sul do Recife | Sedec, Prefeitura do Recife | PE | GeoJSON (CKAN) | 364 | ODbL |
| Risco geológico e hidrológico de Contagem (2024) | Prefeitura de Contagem | MG | ArcGIS REST | 265 | não declarada |
| Setores de risco de Suzano (2019) | Prefeitura de Suzano | SP | ArcGIS REST | 178 | não declarada |
| Risco geológico do PMRR de Congonhas | Prefeitura de Congonhas | MG | ArcGIS REST | 73 | não declarada |

Total esperado: **21.429 setores em 27 UFs**. O número no ar é o do
`manifest.json`, que é a fonte de verdade.

Quatro fontes catalogadas **não** entram na publicação: a setorização de
Contagem (republica os mesmos 28 setores da CPRM e serve de caso de teste da
sobreposição), o GeoSampa de São Paulo e as camadas do IPT no DataGEO (acesso
não confirmado) e a GEO-RIO (só suscetibilidade em raster). Elas aparecem no
manifest com `publicada: false`, para quem consome saber que existem e por que
não vieram.

Os dados do IBGE (malha municipal e códigos de município) entram no catálogo e
na validação.

## Diferenças de produto que importam

Não é tudo setorização com grau de risco.

- **Belo Horizonte** são áreas com tendência a risco, mapeadas em 1996, **sem
  grau de risco** (`bl_produto = area_risco_sem_grau`).
- **Recife** são **pontos** (imóveis), não polígonos, e só da Regional Sul. O
  grau vem de "Área de Risco Nível N"; a correspondência com R1 a R4 é
  suposição do BELUGA, registrada no catálogo.
- **Contagem (2024)** são **pontos**, geológicos e hidrológicos, sem o processo:
  a classe ("GEOLOGICO", "HIDROLOGICO") vai em `bl_tipo_or`.
- **Juiz de Fora** inclui setores de grau **Baixo** (R1), que a CPRM quase não
  publica. 151 dos 994 setores se sobrepõem a setores da CPRM.
- **Suzano** tem o processo em texto livre, extraído por palavra-chave; 6 dos
  178 setores não citam processo reconhecível. A CPRM não tem setores em Suzano.

## Visualizador

Um mapa para conferir o que está sendo agregado: setores por UF, filtro por
fonte, grau e sobreposição com a CPRM, ficha de cada setor com a proveniência,
o catálogo e o relatório de validação.

Publicado em **https://hcristosm.github.io/BELUGA/**, ou local:

```bash
scripts/rodar_visualizador.sh   # http://localhost:8010/
```

## Rodar localmente

Requer Python 3.11+. Para gerar o PMTiles também é preciso o `tippecanoe`
(`sudo apt install tippecanoe`); sem ele, use `exportar --sem-pmtiles`.

```bash
git clone https://github.com/hcristosm/BELUGA
cd BELUGA
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/python -m src.cli validar-catalogo
.venv/bin/python -m src.cli coletar --fonte mg-congonhas-pmrr
.venv/bin/python -m src.cli exportar --sem-malha
```

Os comandos, as opções e o que protege a publicação estão em
**[docs/funcionamento.md](docs/funcionamento.md)**.

## Limitações conhecidas

- **A cobertura é pequena.** As capitais com maior população em área de risco
  (São Paulo, Rio de Janeiro, Salvador) ainda não têm fonte aberta confirmada.
- **Licenças.** A CPRM, Juiz de Fora, Contagem, Suzano e Congonhas não declaram
  licença nos serviços. Os dados do Recife são ODbL, que exige compartilhar o
  derivado sob a mesma licença, e isso vale para os arquivos agregados.
- **A camada da CPRM mudou em 2026-11.** A SGB passou a escrever o município
  como `NOME (UF)`, tirou o `cd_geocmu` e renumerou os `objectid`. O BELUGA
  normaliza de volta. Três grafias de município da CPRM não batem com o IBGE e
  estão em `catalogo/aliases_municipios.yaml`.
- **Códigos repetidos na CPRM.** 72 códigos `num_setor` aparecem em mais de uma
  feição. Partes com os mesmos atributos viram um setor só (multipolígono); os
  demais são setores diferentes com o mesmo código (sigla de município que
  colide, como `AL_CA_SR_01_CPRM` em Campestre e em Cajueiro) e recebem o id da
  fonte como sufixo, com o código original em `bl_num_or`.
- **13 setores da CPRM** têm o ponto representativo a mais de 500 m do município
  declarado. Estão publicados e listados no relatório de validação.
- **Itaguaí (RJ)** publica as áreas de risco no ArcGIS Online, mas o serviço
  exige login; não entra até haver acesso aberto.
- **O PMTiles descarta feição em zoom baixo**, para o tile caber. Serve para
  desenhar mapa, não para contar setores.

## Documentação

- [Usar os dados](docs/usar-os-dados.md): formatos, URLs, exemplos e licenças.
- [Como funciona](docs/funcionamento.md): pipeline, workflows, guardas e como reverter.
- [Contrato de dados](docs/contrato-dados.md): o compromisso de estabilidade com quem consome.
- [Esquema dos setores](docs/esquema-setores.md): cada coluna, domínio e origem.
- [Catálogo de fontes](docs/catalogo.md): campos do YAML e como adicionar uma fonte.
- [Como contribuir](CONTRIBUTING.md).

## Como citar

Se o BELUGA entrar num trabalho, relatório ou artigo, use o botão **Cite this
repository**, no topo da página do GitHub. Ele lê o
[`CITATION.cff`](CITATION.cff) e entrega a referência em APA e BibTeX. Cite
também a fonte primária de cada setor, que vem na coluna `bl_fonte` e no
`manifest.json`: o levantamento de campo é da CPRM/SGB, da prefeitura ou do
órgão estadual.

## Licença

Código sob [AGPL-3.0](LICENSE). **Os dados publicados seguem a licença de cada
fonte**, informada no catálogo, no `manifest.json` e em cada setor
(`bl_licenca`).

<div align="center">
<img src="docs/logo/beluga-marca.png" alt="Marca do BELUGA: uma beluga emitindo ondas sonoras" width="120">

Projeto irmão do [ORCA](https://github.com/hcristosm/ORCA).
</div>
