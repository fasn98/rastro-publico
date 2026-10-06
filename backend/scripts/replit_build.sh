#!/usr/bin/env bash
# Build dos deployments no Replit: instala o uv (se faltar) e as dependências do backend.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || python3 -m pip install --user --quiet uv
uv sync --frozen --no-dev
