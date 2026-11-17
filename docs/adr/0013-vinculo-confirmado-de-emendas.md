# ADR-0013: Uma emenda só é ligada a um parlamentar por vínculo confirmado ou por exceção aprovada

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commits `20d9f2f` e `2845e86`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

O arquivo de emendas do Portal da Transparência identifica o autor por texto. Ligar uma
emenda ao político errado seria um dado falso publicado na página de uma pessoa.

## Opções consideradas

- Cruzamento só pelo nome: era a regra anterior, descartada (resultados em
  `backend/src/rastro/politicos/README.md`).

## Decisão

`backend/src/rastro/politicos/vinculo.py` exige nome normalizado único entre os 901
parlamentares federais da legislatura 57, parlamentar de SP, ano dentro do mandato e o
mesmo "Código do Autor" em todas as emendas. Desde 17/11/2026 (decisão do Fabio), "de SP"
passou a ser "de UF publicada": SP ou uma UF de `RASTRO_POL_UFS_LIBERADAS`; uma UF só
coletada, ainda não liberada, não grava vínculo. Os casos fora da regra só entram por
`politicos/excecoes_emendas.toml`, com texto exato da fonte, justificativa, aprovador e
data; um teste falha sem esses campos.

## Consequências

- Mais fácil: nenhuma ligação ambígua chega ao site.
- Mais difícil: parte das emendas fica sem link (as de 2023, por exemplo).
- Proibido: nova regra de cruzamento ou nova exceção sem aprovação do Fabio.

## Como revisitar

Se a fonte passar a trazer um identificador oficial do parlamentar.
