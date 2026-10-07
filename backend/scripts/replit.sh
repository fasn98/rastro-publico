#!/usr/bin/env bash
# Ponto de entrada dos dois apps do Replit (o mesmo repositório importado duas vezes).
# RASTRO_PAPEL (Secret do deployment) escolhe o que roda:
#   coleta     -> Scheduled Deployment: coleta, ranking e publicação do site
#   auditoria  -> Autoscale Deployment: API de auditoria (só leitura)
# O valor não diferencia maiúsculas e ignora espaços nas pontas ("AUDITORIA " vale).
#
# `bash scripts/replit.sh --validar-papel` só confere o Secret: imprime o papel e sai.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

PAPEIS="coleta, auditoria"
# minúsculas e sem espaços nas pontas
PAPEL="$(printf '%s' "${RASTRO_PAPEL:-}" | tr '[:upper:]' '[:lower:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
case "$PAPEL" in
  coleta | auditoria) ;;
  "")
    echo "ERRO: o Secret RASTRO_PAPEL não está definido. Valores aceitos: $PAPEIS." >&2
    exit 64
    ;;
  *)
    echo "ERRO: RASTRO_PAPEL=\"${RASTRO_PAPEL}\" não é um papel válido. Valores aceitos: $PAPEIS (sem diferenciar maiúsculas)." >&2
    exit 64
    ;;
esac
if [ "${1:-}" = "--validar-papel" ]; then
  echo "$PAPEL"
  exit 0
fi

# nunca subir em produção com a credencial de desenvolvimento (rastro:rastro) ou sem senha
uv run rastro conferir-producao
case "$PAPEL" in
  coleta) exec bash scripts/coleta_sp.sh ;;
  auditoria) exec uv run uvicorn rastro.api.auditoria:app --host 0.0.0.0 --port "${PORT:-8000}" ;;
esac
