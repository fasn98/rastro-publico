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
# O RREO/RGF é coletado para todas as UFs (ADR-0020). A parte fiscal de cada UF entra no
# site só depois de aprovada no portão de qualidade; os políticos continuam só de SP.
#
# Variáveis (Secrets do Replit):
#   DATABASE_URL           banco de produção (criado pelo Replit)
#   RASTRO_GITHUB_TOKEN    token fine-grained, só este repositório, Contents: read and write
#   RASTRO_URL_AUDITORIA   URL pública da API de auditoria (ex.: https://rastro-auditoria.replit.app)
#   RASTRO_SIMULAR=1       (opcional) coleta, exporta e verifica, mas não publica o site
#   RASTRO_LOTE_LIMITE_MIN (opcional) minutos do lote RREO/RGF por execução (padrão 480)
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

echo "== versão do código"
# compara o código em disco com o main do GitHub: o Replit só muda com Pull + Republish.
# O aviso sai aqui e de novo no fim; a conferência nunca interrompe a coleta.
CONFERENCIA="$(mktemp)"
COMMIT_PUBLICADO="$(uv run rastro conferir-codigo 2>"$CONFERENCIA")" || COMMIT_PUBLICADO=""
grep -v "UV_NATIVE_TLS" "$CONFERENCIA" >&2 || true
AVISO_CODIGO="$(grep '^AVISO' "$CONFERENCIA" || true)"

echo "== migrações e cadastros"
uv run alembic upgrade head
# versão nova do mapeamento de contas: reconstrói do arquivo bruto, uma vez só, as linhas
# do RGF que ela passou a pedir (sem chamar a API; ver mapeamento_siconfi.yaml)
uv run rastro aplicar-mapeamento --tipo RGF --se-mudou
uv run rastro coletar ibge-municipios ibge-populacao siconfi-entes \
  || echo "AVISO: cadastros com falha; seguem os dados anteriores (resumo no fim)"

echo "== RREO/RGF de todas as UFs (código 1 = algum item falhou; fica para a próxima execução)"
# Lote nacional (ADR-0020): municípios, estados e DF; primeiro 2023-2025 (os exercícios do
# ranking v1.1), UF por UF, das UFs com menos municípios para as com mais; depois os demais
# exercícios. Não começa item novo depois de RASTRO_LOTE_LIMITE_MIN minutos (padrão 480):
# o que faltar continua na próxima execução, e o resto desta coleta roda dentro do limite
# de 11 h do Replit. Num lote novo, os exercícios antigos entram em rodízio de 4 semanas.
uv run python -m rastro.coletores.siconfi_lote --uf TODAS --esfera M E D \
  --anos "2022-$ANO_ATUAL" --prioridade 2023-2025 \
  --limite-minutos "${RASTRO_LOTE_LIMITE_MIN:-480}" --rodizio || [ $? -eq 1 ]

echo "== políticos (falha de uma fonte não apaga dados já coletados)"
uv run rastro politicos --uf SP --anos "2023-$ANO_ATUAL" \
  || echo "AVISO: coleta de políticos com falhas; seguem os dados anteriores (resumo no fim)"

echo "== ranking e verificação do arquivo bruto"
# cada UF com o seu ranking (o DF fica fora: Brasília não entrega como município)
uv run rastro ranking --uf TODAS
uv run rastro verificar-respostas --amostra 50

echo "== portão de qualidade por UF (ADR-0020)"
# completude, SHA-256 de uma amostra do bruto e 3 entes sorteados conferidos na fonte;
# só as UFs aprovadas entram no site (a reprovada fica com a versão anterior ou fora).
# Se o portão em si falhar, o site sai como antes (só SP), com aviso.
PORTAO="$(mktemp --suffix=.json)"
rm -f "$PORTAO"
uv run rastro portao --saida "$PORTAO" \
  || { echo "AVISO: o portão de qualidade falhou; o site sai só com SP, como antes" >&2; rm -f "$PORTAO"; }

echo "== site estático (incremental: parte do que está publicado no gh-pages)"
ARGS_PORTAO=()
if [ -f "$PORTAO" ]; then
  ARGS_PORTAO=(--portao "$PORTAO")
fi
DIST="$RAIZ/frontend/dist"
# os dados ficam fora do dist: o build do frontend apaga a pasta de saída dele
DADOS="$RAIZ/site-dados"
rm -rf "$DIST" "$DADOS"
# com o indice.json da publicação anterior, a exportação reaproveita os grupos sem
# mudança; sem publicação anterior (ou noutro formato), ela é completa
uv run rastro baixar-site --saida "$DADOS"
# commit do manifesto: o que a conferência identificou (o Replit não tem .git) ou o do Git
RASTRO_COMMIT="${COMMIT_PUBLICADO:-$(git -C "$RAIZ" rev-parse HEAD 2>/dev/null || true)}" \
  uv run rastro exportar-site --uf SP --saida "$DADOS" ${ARGS_PORTAO[@]+"${ARGS_PORTAO[@]}"}
# as dependências vêm do build do deployment; só reinstala se faltar alguma coisa
bash scripts/frontend_deps.sh
(
  cd "$RAIZ/frontend"
  # prévia (faixa + noindex) ligada até o lançamento ser aprovado: o lançamento é um PR
  # que troca o padrão para 0 (ou RASTRO_PREVIA=0 no ambiente)
  VITE_PREVIA="${RASTRO_PREVIA:-1}" VITE_BASE=/rastro-publico/ VITE_API_AUDITORIA="${RASTRO_URL_AUDITORIA:?defina RASTRO_URL_AUDITORIA}" npm run build
)
cp -a "$DADOS" "$DIST/dados"

echo "== situação das fontes nesta coleta"
RESUMO="$(uv run rastro resumo-coleta --desde "$RASTRO_INICIO_COLETA")"
echo "$RESUMO"

if [ "${RASTRO_SIMULAR:-}" = "1" ]; then
  echo "== simulação: verifica contra o site publicado, sem publicar"
  uv run rastro publicar-site --dist "$DIST" --simular
  echo "Duração da coleta: ${SECONDS} s"
  [ -n "$AVISO_CODIGO" ] && echo "$AVISO_CODIGO"
  exit 0
fi

echo "== publicação (verifica antes; tudo ou nada)"
uv run rastro publicar-site --dist "$DIST"
echo "Duração da coleta: ${SECONDS} s"
if ! grep -q "^Fontes com falha: nenhuma$" <<<"$RESUMO"; then
  echo "AVISO: site publicado com fontes desatualizadas: $(grep '^Fontes com falha:' <<<"$RESUMO")"
fi
if [ -n "$AVISO_CODIGO" ]; then
  echo "$AVISO_CODIGO"
fi
