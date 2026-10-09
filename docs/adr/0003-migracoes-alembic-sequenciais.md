# ADR-0003: O esquema muda só por migrações do Alembic, numeradas em sequência a partir do main

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `82fc84a`; regra de numeração no `CLAUDE.md`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

Várias sessões trabalham em branches paralelas. Duas branches com migrações novas já
colidiram: a `0010_politicos` foi renumerada depois da `0008`/`0009` (commit `cb6298e`), e
a `0017_junta_0015_0016` existe para unir dois ramos.

## Opções consideradas

Não registradas na época.

## Decisão

Toda mudança de esquema é uma migração em `backend/alembic/versions/NNNN_slug.py`. O número
segue a **última migração que está no `main`**, não a da branch. A coleta aplica
`alembic upgrade head` antes de tudo (`backend/scripts/coleta_sp.sh`).

## Consequências

- Mais fácil: o banco de produção se atualiza sozinho na próxima coleta.
- Mais difícil: duas worktrees com migração nova colidem. Tarefas que criam migração são
  serializadas.
- Proibido: alterar uma migração que já está no `main`; criar tabela fora do Alembic.

## Como revisitar

Se as colisões de numeração passarem a ser frequentes com o trabalho em paralelo.
