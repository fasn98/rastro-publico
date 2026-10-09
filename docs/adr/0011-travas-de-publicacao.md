# ADR-0011: A publicação de cada conjunto de dados sensível é controlada por uma trava em Settings

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `20d9f2f`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

Dados novos (TSE, eleitos de 2026, emendas) precisam ser coletados e validados antes de
aparecer no site, e a publicação de dado novo exige aprovação do Fabio.

## Opções consideradas

Não registradas na época.

## Decisão

Travas `pol_publicar_*` em `backend/src/rastro/config.py`, com variável
`RASTRO_POL_PUBLICAR_*` para sobrepor. A API esconde o que está travado, e o site herda isso
porque é exportado pelas rotas (ADR-0009). O estado das travas vai no `manifesto.json`.

## Consequências

- Mais fácil: coletar antes de publicar; desligar um conjunto sem mexer no código.
- Mais difícil: toda tela nova precisa respeitar as travas pela API, não pelo frontend.
- Proibido: ligar uma trava ou mudar o padrão dela sem aprovação do Fabio.

## Como revisitar

Se o número de travas crescer a ponto de exigir configuração por fonte em arquivo.
