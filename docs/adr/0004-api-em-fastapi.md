# ADR-0004: A API HTTP é escrita em FastAPI e é a fonte única do conteúdo exibido

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `82fc84a`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

O mesmo conteúdo precisa estar disponível na API (desenvolvimento e auditoria) e no site
estático (produção), sem duas implementações divergentes.

## Opções consideradas

Não registradas na época.

## Decisão

FastAPI em `backend/src/rastro/api/`: `main.py` (completa), `politicos.py` e `auditoria.py`
(app separado, ADR-0010). O site estático é gerado chamando essas mesmas rotas dentro do
processo (ADR-0009).

## Consequências

- Mais fácil: uma regra de exibição (travas, ordenação neutra, rótulos) vale para a API e
  para o site ao mesmo tempo.
- Mais difícil: mudar uma rota muda o formato exportado. Isso é mudança de formato e
  exige aprovação do Fabio (`CLAUDE.md`).
- Proibido: tela do site com dado que não saia de uma rota da API.

## Como revisitar

Se a exportação pelas rotas ficar lenta demais para a janela da coleta.
