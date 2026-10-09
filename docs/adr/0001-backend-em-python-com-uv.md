# ADR-0001: O backend é escrito em Python 3.12, com dependências gerenciadas pelo uv

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `82fc84a`, estrutura inicial)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

Coletores, banco, API, ranking, exportação do site e publicação formam um único pacote
(`backend/src/rastro`, comando `rastro`). As fontes são APIs REST, arquivos CSV/ZIP e
planilhas oficiais, com tratamento pesado de texto e números.

## Opções consideradas

Não registradas na época. Este ADR documenta o que está no código.

## Decisão

Python `>=3.12` (`backend/pyproject.toml`), empacotado com hatchling e com dependências
travadas em `backend/uv.lock`. O CI roda `uv sync --locked`, `ruff check`,
`ruff format --check` e `pytest`.

## Consequências

- Mais fácil: um único comando (`rastro ...`) para coleta, exportação e publicação, e o
  mesmo código serve a API, o CLI e o site estático.
- Mais difícil: o Replit usa poetry por padrão; o build instala o `uv` à parte
  (`backend/scripts/replit_build.sh`).
- Proibido: dependência fora do `uv.lock`; código que não passe no `ruff` (linha de 100,
  regras E, F, I, UP, B).

## Como revisitar

Se alguma fonte exigir uma biblioteca indisponível em Python, ou se o tempo de coleta
passar a ser limitado pela CPU, e não pelo limite de 1 req/s das fontes.
