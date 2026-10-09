# ADR-0008: As tabelas do SICONFI guardam só as contas mapeadas em YAML; o resto é reconstruído do bruto

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `03b433a`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

O RREO e o RGF devolvem de 5,7 mil a 21,9 mil linhas por município e ano, mas os
indicadores usam de 120 a 186 linhas. Guardar tudo projetava ~56 GB para o Brasil.

## Opções consideradas

- Guardar todas as linhas em tabela: descartada pelo volume (medido: 544.045 → 6.611
  linhas na amostra, 145 MB → 1,5 MB, com ranking e indicadores idênticos).

## Decisão

`conta_demonstrativo` guarda só as linhas e colunas listadas em
`backend/src/rastro/mapeamento_siconfi.yaml`. Conta nova entra no YAML e
`rastro aplicar-mapeamento` reconstrói a partir do bruto, sem baixar de novo.

## Consequências

- Mais fácil: banco pequeno; mudar o mapeamento não exige recoleta.
- Mais difícil: depende do arquivo bruto completo (ADR-0006).
- Proibido: mudar o mapeamento de contas sem aprovação do Fabio (`CLAUDE.md`).

## Como revisitar

Se os indicadores passarem a usar a maior parte das linhas dos demonstrativos.
