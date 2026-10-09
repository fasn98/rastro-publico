# ADR-0012: As regras do ranking ficam num arquivo versionado, cuja versão e hash são gravados com cada nota

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `c46ad26`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

O ranking fiscal dos municípios precisa ser reproduzível e explicável: quem lê uma nota tem
de saber exatamente com que regras ela foi calculada.

## Opções consideradas

As alternativas descartadas estão na página Metodologia (`frontend/src/Metodologia.tsx`).

## Decisão

`backend/src/rastro/ranking/metodologia_v1.toml` (versão `1.0.0`) define a normalização
linear 0–1, os pesos iguais, a janela de 3 exercícios, as faixas populacionais e o mínimo
de indicadores. A versão e o hash do arquivo são gravados em `nota_ranking`; mudar uma
regra exige subir a versão.

## Consequências

- Mais fácil: qualquer nota publicada remonta à regra exata.
- Mais difícil: limites provisórios (autonomia, liquidez, investimento, transparência)
  escolhidos com amostra de 10 municípios ainda precisam de revisão (proposta v1.1 no PR
  #24).
- Proibido: mudar fórmula, peso ou limite fora do arquivo ou sem subir a versão; mudar a
  metodologia sem aprovação do Fabio.

## Como revisitar

A cada mudança de metodologia (a v1.1 está em proposta).
