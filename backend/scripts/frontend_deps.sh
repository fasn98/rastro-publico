#!/usr/bin/env bash
# Instala as dependências do frontend (npm ci) e confere que o build tem o que precisa.
#
# Usado no build do deployment (scripts/replit_build.sh), para que a coleta agendada não
# dependa do registro do npm, e na coleta (scripts/coleta_sp.sh), que só reinstala se
# faltar alguma coisa.
#
# O npm pode quebrar no meio da instalação e ainda assim sair com código 0 (ex.: "npm
# error Exit handler never called!"). Por isso o resultado é conferido pelos executáveis
# instalados, e não pelo código de saída; são até 3 tentativas, com 30 s entre elas.
set -euo pipefail
cd "$(dirname "$0")/../../frontend"

completo() { [ -x node_modules/.bin/tsc ] && [ -x node_modules/.bin/vite ]; }

if [ "${1:-}" != "--forcar" ] && completo; then
  echo "frontend: dependências já instaladas"
  exit 0
fi
for tentativa in 1 2 3; do
  npm ci --no-audit --no-fund || echo "AVISO: npm ci terminou com código $? (tentativa $tentativa)"
  if completo; then
    echo "frontend: dependências instaladas (tentativa $tentativa)"
    exit 0
  fi
  echo "AVISO: npm ci não deixou tsc e vite instalados (tentativa $tentativa de 3)" >&2
  [ "$tentativa" -lt 3 ] && sleep 30
done
echo "ERRO: não foi possível instalar as dependências do frontend após 3 tentativas" >&2
exit 1
