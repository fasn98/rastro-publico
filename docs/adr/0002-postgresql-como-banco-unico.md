# ADR-0002: Todos os dados ficam num único PostgreSQL 16, acessado pelo SQLAlchemy 2

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `82fc84a`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

O projeto guarda dados normalizados das fontes, o arquivo bruto de respostas (ADR-0006), os
lotes de coleta retomáveis e as notas do ranking. Os valores financeiros precisam ser
exatos.

## Opções consideradas

Não registradas na época.

## Decisão

PostgreSQL 16 (`docker-compose.yml`; serviço `postgres:16` no CI) com SQLAlchemy 2
(`backend/src/rastro/models.py`, `db.py`). Valores monetários em `NUMERIC`. Em produção,
o banco é o de produção do Replit (Neon).

## Consequências

- Mais fácil: a trava de coleta usa advisory lock do próprio PostgreSQL (ADR-0014); a
  impressão digital da exportação incremental é calculada no banco.
- Mais difícil: os testes de banco precisam do banco `rastro_teste` e são pulados sem ele.
  Fora do CI, "pulado" não quer dizer "passou".
- Proibido: `float` para valores monetários; acesso ao banco pelo site publicado
  (ADR-0009).

## Como revisitar

Se o volume projetado para o Brasil inteiro (~4,4 GB em 2022–2025, README) estourar o
plano de banco, ou se o Neon deixar de aceitar conexões de fora do Replit (ver ADR-0016).
