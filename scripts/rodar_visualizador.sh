#!/usr/bin/env bash
# Sobe um servidor HTTP local e serve o visualizador do BELUGA.
# Uso: scripts/rodar_visualizador.sh [porta]
# Os dados vêm de docs/visualizador/v1/, gerado por `python -m src.cli exportar`.
set -euo pipefail

PORTA="${1:-8010}"
DIRETORIO_RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "$DIRETORIO_RAIZ/docs/visualizador/v1/manifest.json" ]; then
  echo "Aviso: docs/visualizador/v1/manifest.json não existe. Rode antes:"
  echo "  python -m src.cli coletar && python -m src.cli exportar"
fi
echo "Servindo o visualizador em http://localhost:${PORTA}/ (Ctrl+C para parar)"
cd "$DIRETORIO_RAIZ"
python3 -m http.server "$PORTA" --bind 127.0.0.1 --directory docs/visualizador
