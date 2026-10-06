#!/usr/bin/env bash
# Malha dos municípios de SP (IBGE, API de Malhas v3, qualidade mínima: ~310 KB).
# Fonte: https://servicodados.ibge.gov.br/api/docs/malhas?versao=3
set -euo pipefail
cd "$(dirname "$0")/.."
curl -sSf -o public/geo/sp-municipios.json \
  "https://servicodados.ibge.gov.br/api/v3/malhas/estados/35?formato=application/vnd.geo%2Bjson&intrarregiao=municipio&qualidade=minima"
