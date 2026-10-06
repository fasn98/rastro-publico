#!/usr/bin/env bash
# Ponto de entrada dos dois apps do Replit (o mesmo repositório importado duas vezes).
# RASTRO_PAPEL (Secret do deployment) escolhe o que roda:
#   coleta     -> Scheduled Deployment: coleta, ranking e publicação do site
#   auditoria  -> Autoscale Deployment: API de auditoria (só leitura)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
# nunca subir em produção com a credencial de desenvolvimento (rastro:rastro) ou sem senha
uv run rastro conferir-producao
case "${RASTRO_PAPEL:-}" in
  coleta) exec bash scripts/coleta_sp.sh ;;
  auditoria) exec uv run uvicorn rastro.api.auditoria:app --host 0.0.0.0 --port "${PORT:-8000}" ;;
  *) echo "Defina o Secret RASTRO_PAPEL como 'coleta' ou 'auditoria'." >&2; exit 1 ;;
esac
