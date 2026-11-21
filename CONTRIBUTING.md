# Contribuindo com o BELUGA

Issues, PRs e indicações de fontes são bem-vindos. A forma mais útil de
contribuir é apontar um mapeamento de risco estadual ou municipal com dado
aberto.

Ao participar, você concorda em seguir o [Código de Conduta](CODE_OF_CONDUCT.md).

## Indicar ou adicionar uma fonte

Siga [docs/catalogo.md](docs/catalogo.md). No PR, informe:

- a URL usada e o órgão responsável;
- a licença ou os termos de uso;
- o que o `robots.txt` diz;
- o limite de requisições observado, se houver;
- como a fonte falha (fora do ar, resposta vazia, página HTML com HTTP 200).

Fonte sem acesso confirmado entra com `status: nao_verificada`. Não invente
URL, endpoint ou nome de camada.

## A prioridade é confiabilidade

As fontes são servidores públicos que caem, mudam de formato e devolvem
resposta vazia com HTTP 200. Funcionar sem quebrar vale mais que fonte nova.
Duas regras valem para todo o código:

- **Caminhos moram em `src/config.py`.** Nunca monte um caminho de `data/` à mão.
- **Publicar menos do que já está no ar é proibido.** A guarda em
  `scripts/conferir_publicacao.py` grava `publicar=false` antes de sair com 1, e
  é coberta por `tests/test_conferir_publicacao.py`. Não mude essas
  propriedades sem olhar esses testes.

E uma regra para quem opera os workflows: nunca julgue um run pelo status.
Confira nos logs a contagem de setores por fonte e o relatório de validação.

## Ambiente de desenvolvimento

Requer Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Testes e gates

O CI roda estes comandos a cada push e PR. Rode-os antes de commitar:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m mypy src scripts
.venv/bin/python -m bandit -q -c pyproject.toml -r src scripts
.venv/bin/python -m src.cli validar-catalogo
```

Toda chamada de rede nos testes é mockada (`responses`): a suíte roda sem
internet. Coletor novo precisa de teste com a resposta mockada, incluindo os
casos de falha.

O visualizador é validado à mão: `scripts/rodar_visualizador.sh`, desktop e
celular (abaixo de 760 px), temas claro e escuro, console sem erro.

## Padrão de commits

[Conventional Commits](https://www.conventionalcommits.org/), em português:
`tipo(escopo): descrição breve`. Tipos: `feat`, `fix`, `refactor`, `chore`,
`docs`, `test`. Escopos comuns: `catalogo`, `coleta`, `normalizacao`,
`validacao`, `export`, `visualizador`, `ci`, `readme`.

Código, comentários, commits e documentação em português. Toda mudança
relevante ganha entrada no `CHANGELOG.md`, em `[Unreleased]`, agrupada por
`FEATURES`, `FIXES`, `REFACTOR` ou `CHORE`.

## Releases

Bump da versão no `pyproject.toml` e em `src/__init__.py`, entrada no
`CHANGELOG.md` e tag `vX.Y.Z`. As Releases de dados (`dados-*`) são criadas pelo
workflow de coleta, não à mão.
