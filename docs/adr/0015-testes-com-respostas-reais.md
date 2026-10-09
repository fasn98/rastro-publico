# ADR-0015: Os testes usam só respostas reais das fontes, gravadas em fixtures, sem acesso à internet

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `3d670b7` reforçou a regra no `test_site.py`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

Princípio do projeto: nenhum dado inventado, nem em testes. Várias peculiaridades das
fontes tratadas no código só aparecem nas respostas reais (o `capital` do SICONFI com
espaços, `uf = "BR"` para estados, `microrregiao: null` no IBGE; ver o README).

## Opções consideradas

Não registradas na época.

## Decisão

pytest + respx em `backend/tests/`, com respostas gravadas em `backend/tests/fixtures/`. As
fixtures com dado pessoal (TSE, cota) são guardadas já redigidas (ADR-0007). Os testes de
banco usam `rastro_teste` e são pulados sem ele; no CI há um PostgreSQL 16 de serviço.

## Consequências

- Mais fácil: testes reproduzíveis, que pegam mudanças de formato das fontes.
- Mais difícil: cobrir um caso novo exige achar uma resposta real que o contenha.
- Proibido: dado fictício em fixture; teste que acesse a internet.

## Como revisitar

Se uma fonte mudar de formato com frequência e as fixtures ficarem desatualizadas.
