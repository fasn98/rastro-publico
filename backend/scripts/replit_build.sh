#!/usr/bin/env bash
# Build dos deployments no Replit: instala o uv (se faltar), as dependências do backend e
# as do frontend (a coleta só roda o build do site, sem baixar nada do npm).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || python3 -m pip install --user --quiet uv
uv sync --frozen --no-dev
bash scripts/frontend_deps.sh --forcar
