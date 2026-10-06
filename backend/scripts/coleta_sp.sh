#!/usr/bin/env bash
# Coleta agendada: RREO/RGF de 2022 a 2025 dos 645 municípios de SP.
# Retomável: se for interrompida (fim do tempo do agendador, queda de rede...),
# a próxima execução continua de onde parou.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run alembic upgrade head
uv run rastro coletar ibge-municipios siconfi-entes
uv run python -m rastro.coletores.siconfi_lote --uf SP --anos 2022-2025
