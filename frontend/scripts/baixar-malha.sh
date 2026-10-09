#!/usr/bin/env bash
# Malhas do IBGE (API de Malhas v3, qualidade mínima): os municípios de cada UF
# (public/geo/{UF}.json, de 31 KB no AC a 500 KB em MG). Fonte: https://servicodados.ibge.gov.br/api/docs/malhas?versao=3
# Em 09/10/2026, a malha mínima não traz Boa Esperança do Norte/MT (5101837, instalado em
# 2025): o município aparece na tabela do ranking, fora do mapa, com nota explicando.
set -euo pipefail
cd "$(dirname "$0")/.."
API="https://servicodados.ibge.gov.br/api/v3/malhas"
FORMATO="formato=application/vnd.geo%2Bjson&qualidade=minima"
declare -A UF=(
  [11]=RO [12]=AC [13]=AM [14]=RR [15]=PA [16]=AP [17]=TO
  [21]=MA [22]=PI [23]=CE [24]=RN [25]=PB [26]=PE [27]=AL [28]=SE [29]=BA
  [31]=MG [32]=ES [33]=RJ [35]=SP [41]=PR [42]=SC [43]=RS [50]=MS [51]=MT [52]=GO [53]=DF
)
mkdir -p public/geo
for cod in "${!UF[@]}"; do
  curl -sSf -o "public/geo/${UF[$cod]}.json" "$API/estados/$cod?$FORMATO&intrarregiao=municipio"
done
