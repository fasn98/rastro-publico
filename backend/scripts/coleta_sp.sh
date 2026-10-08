#!/usr/bin/env bash
# Coleta agendada de SP (Replit Scheduled Deployment) e publicação do site estático.
#
# Etapas: migrações -> cadastros -> RREO/RGF (lote retomável, 1 req/s) -> políticos ->
# ranking -> verificação de amostra do arquivo bruto -> frontend + JSON -> publicação no
# GitHub Pages. Se qualquer verificação falhar, nada é publicado e o site continua como está.
#
# A falha de UMA fonte não impede a publicação: cada fonte tenta de novo com espera
# progressiva (RASTRO_FONTE_ESPERAS) e, se continuar falhando, o site sai com os dados
# anteriores dela (ou com a seção "fonte indisponível nesta coleta", se nunca houve dado),
# e a execução termina com AVISO (código 0). Termina com ERRO só quando algo crítico
# falha: banco, migrações, verificação do arquivo bruto, exportação/verificação do site ou
# o envio ao GitHub.
#
# Variáveis (Secrets do Replit):
#   DATABASE_URL           banco de produção (criado pelo Replit)
#   RASTRO_GITHUB_TOKEN    token fine-grained, só este repositório, Contents: read and write
#   RASTRO_URL_AUDITORIA   URL pública da API de auditoria (ex.: https://rastro-auditoria.replit.app)
#   RASTRO_SIMULAR=1       (opcional) coleta, exporta e verifica, mas não publica o site
set -euo pipefail
# qualquer etapa que falhar diz qual foi e com que código (137 = processo morto pelo
# sistema, em geral por falta de memória; 143 = encerrado pelo agendador)
trap 'codigo=$?; echo "ERRO: a etapa \"${BASH_COMMAND}\" terminou com código ${codigo}$( [ "$codigo" -eq 137 ] && echo " (processo morto pelo sistema: provável falta de memória)")" >&2' ERR
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ/backend"
ANO_ATUAL="$(date +%Y)"
# início desta coleta: a exportação compara a última atualização de cada fonte com ele
RASTRO_INICIO_COLETA="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
export RASTRO_INICIO_COLETA

echo "== migrações e cadastros"
uv run alembic upgrade head
uv run rastro coletar ibge-municipios ibge-populacao siconfi-entes \
  || echo "AVISO: cadastros com falha; seguem os dados anteriores (resumo no fim)"

echo "== RREO/RGF (código 1 = algum item falhou; fica para a próxima execução)"
uv run python -m rastro.coletores.siconfi_lote --uf SP --anos "2022-$ANO_ATUAL" || [ $? -eq 1 ]

echo "== políticos (falha de uma fonte não apaga dados já coletados)"
uv run rastro politicos --uf SP --anos "2023-$ANO_ATUAL" \
  || echo "AVISO: coleta de políticos com falhas; seguem os dados anteriores (resumo no fim)"

echo "== ranking e verificação do arquivo bruto"
uv run rastro ranking --uf SP
uv run rastro verificar-respostas --amostra 50

echo "== site estático (incremental: parte do que está publicado no gh-pages)"
DIST="$RAIZ/frontend/dist"
# os dados ficam fora do dist: o build do frontend apaga a pasta de saída dele
DADOS="$RAIZ/site-dados"
rm -rf "$DIST" "$DADOS"
# com o indice.json da publicação anterior, a exportação reaproveita os grupos sem
# mudança; sem publicação anterior (ou noutro formato), ela é completa
uv run rastro baixar-site --saida "$DADOS"
RASTRO_COMMIT="$(git -C "$RAIZ" rev-parse HEAD 2>/dev/null || true)" \
  uv run rastro exportar-site --uf SP --saida "$DADOS"
# as dependências vêm do build do deployment; só reinstala se faltar alguma coisa
bash scripts/frontend_deps.sh
(
  cd "$RAIZ/frontend"
  VITE_BASE=/rastro-publico/ VITE_API_AUDITORIA="${RASTRO_URL_AUDITORIA:?defina RASTRO_URL_AUDITORIA}" npm run build
)
cp -a "$DADOS" "$DIST/dados"

echo "== situação das fontes nesta coleta"
RESUMO="$(uv run rastro resumo-coleta --desde "$RASTRO_INICIO_COLETA")"
echo "$RESUMO"

if [ "${RASTRO_SIMULAR:-}" = "1" ]; then
  echo "== simulação: verifica contra o site publicado, sem publicar"
  uv run rastro publicar-site --dist "$DIST" --simular
  echo "Duração da coleta: ${SECONDS} s"
  exit 0
fi

echo "== publicação (verifica antes; tudo ou nada)"
uv run rastro publicar-site --dist "$DIST"
echo "Duração da coleta: ${SECONDS} s"
if ! grep -q "^Fontes com falha: nenhuma$" <<<"$RESUMO"; then
  echo "AVISO: site publicado com fontes desatualizadas: $(grep '^Fontes com falha:' <<<"$RESUMO")"
fi
