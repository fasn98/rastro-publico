#!/bin/bash
c=$1; a=$2; f="$(dirname "$0")"/raw/${c}_${a}.json
[ -s "$f" ] && exit 0
for t in 1 2 3; do
  curl -sf --max-time 60 "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/extrato_entregas?id_ente=$c&an_referencia=$a" -o "$f.tmp" && mv "$f.tmp" "$f" && exit 0
  sleep $((t*5))
done
echo "falha $c $a"
