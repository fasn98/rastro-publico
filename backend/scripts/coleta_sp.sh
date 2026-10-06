#!/usr/bin/env bash
# Coleta agendada de SP (Replit Scheduled Deployment) e publicação do site estático.
#
# Etapas: migrações -> cadastros -> RREO/RGF (lote retomável, 1 req/s) -> políticos ->
# ranking -> verificação de amostra do arquivo bruto -> frontend + JSON -> publicação no
# GitHub Pages. Se qualquer verificação falhar, nada é publicado e o site continua como está.
#
# Variáveis (Secrets do Replit):
#   DATABASE_URL           banco de produção (criado pelo Replit)
#   RASTRO_GITHUB_TOKEN    token fine-grained, só este repositório, Contents: read and write
#   RASTRO_URL_AUDITORIA   URL pública da API de auditoria (ex.: https://rastro-auditoria.replit.app)
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ/backend"
ANO_ATUAL="$(date +%Y)"

echo "== migrações e cadastros"
uv run alembic upgrade head
uv run rastro coletar ibge-municipios siconfi-entes

echo "== RREO/RGF (código 1 = algum item falhou; fica para a próxima execução)"
uv run python -m rastro.coletores.siconfi_lote --uf SP --anos "2022-$ANO_ATUAL" || [ $? -eq 1 ]

echo "== políticos (falha de uma fonte não apaga dados já coletados)"
uv run rastro politicos --uf SP --anos "2023-$ANO_ATUAL" || echo "aviso: coleta de políticos com falhas"

echo "== ranking e verificação do arquivo bruto"
uv run rastro ranking --uf SP
uv run rastro verificar-respostas --amostra 50

echo "== site estático"
DIST="$RAIZ/frontend/dist"
rm -rf "$DIST"
(
  cd "$RAIZ/frontend"
  npm ci --no-audit --no-fund
  VITE_BASE=/rastro-publico/ VITE_API_AUDITORIA="${RASTRO_URL_AUDITORIA:?defina RASTRO_URL_AUDITORIA}" npm run build
)
RASTRO_COMMIT="$(git -C "$RAIZ" rev-parse HEAD 2>/dev/null || true)" \
  uv run rastro exportar-site --uf SP --saida "$DIST/dados"

echo "== publicação (verifica antes; tudo ou nada)"
uv run rastro publicar-site --dist "$DIST"
