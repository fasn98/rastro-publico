# ADR-0014: Só uma coleta roda por vez, garantido por advisory lock no PostgreSQL

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-08 (commits `2254701` e `171c6e1`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

Duas coletas simultâneas gravariam no mesmo banco e disputariam a publicação no `gh-pages`.
Isso pode acontecer com Run now, Republish ou dois agendadores, como Replit e Actions
(ADR-0016).

## Opções consideradas

Não registradas na época.

## Decisão

`rastro coleta-exclusiva <comando>` (`backend/src/rastro/trava.py`) pega um advisory lock
numa conexão mantida viva por toda a coleta. Uma coleta concorrente sai com aviso. Uma
trava presa (sem consulta há mais de 10 min ou aberta há mais de 12 h) é solta e a coleta
recomeça.

## Consequências

- Mais fácil: Replit e Actions podem coexistir na fase de teste sem corromper dados.
- Mais difícil: a trava depende de todos os agendadores usarem o mesmo banco.
- Proibido: script de coleta agendada que não passe por `coleta-exclusiva`.

## Como revisitar

Se a coleta passar a ser dividida em execuções paralelas por fonte.
