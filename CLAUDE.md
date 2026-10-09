# Rastro Público — instruções para o Claude

## Idioma

Responda sempre em **português do Brasil**: conversas, relatórios, mensagens de commit,
descrições de PR, comentários no GitHub e comentários no código.

## Princípios do projeto

- **Nenhum dado inventado, estimado ou fictício**, nem em testes. Os testes usam
  respostas reais das fontes, gravadas em `backend/tests/fixtures/`.
- **Todo número exibido** tem fonte oficial, link, período e data da coleta. A auditoria
  leva à resposta bruta arquivada, pelo SHA-256 (`/api/bruto/{sha256}`).
- **Rótulos neutros.** Nunca usar "desvio", "corrupção" ou termos parecidos sem auditoria
  ou decisão judicial citada. Nenhuma nota, ranking ou cor de "bom/ruim" para pessoas.
- **LGPD.** Nenhum CPF, data de nascimento, título de eleitor, e-mail ou endereço de
  pessoa física em nenhuma tabela nem no arquivo bruto. A redação é feita na coleta
  (`coletores/redacao.py`, `politicos/lgpd.py`).
- **O site publicado é estático.** Nenhuma tela chama a API, exceto os endpoints de
  auditoria. Toda tela nova exige:
  - exportação em `backend/src/rastro/site.py`, pelas rotas da API, para que as travas
    `Settings.pol_publicar_*` valham;
  - teste em `backend/tests/test_site.py`;
  - leitura no frontend por `lerJson` (`frontend/src/dados.ts`), com os links de
    auditoria atrás de `AUDITORIA_ATIVA`.
- **Pare e peça aprovação do Fabio antes de:**
  - mapeamentos de contas;
  - regras de cruzamento de dados;
  - exceções;
  - publicação de dados novos;
  - mudanças de formato.

## Fluxo de Git

- O `main` só recebe mudanças **por PR, um por vez, com CI verde**.
- Cada sessão trabalha no próprio branch.
- Migrações do Alembic são numeradas a partir da **última que está no `main`**.

### Merge dos próprios PRs

A sessão pode fazer o merge do PR que ela mesma abriu, **sem pedir autorização ao Fabio**,
quando o CI estiver verde no último commit e não houver conflito com o `main`.

**Exceções: pare e mostre ao Fabio antes do merge** quando o PR:
- muda dados que aparecem no site: publicar fonte nova, ligar trava, mudar regra de
  vínculo ou de cruzamento;
- muda a metodologia, as fórmulas ou os pesos do ranking;
- muda o formato dos arquivos exportados ou o pipeline de publicação;
- mexe em segurança, LGPD ou credenciais.

Na dúvida se um PR se enquadra numa exceção, trate como exceção e pare para a aprovação
do Fabio. Se o `main` mudar antes do merge, traga o `main` para o branch e espere o CI
verde de novo antes de mesclar.

## Onde ler mais

- `README.md`: visão geral, arquitetura e como rodar.
- `backend/src/rastro/politicos/README.md`: módulo de políticos (fontes, cruzamentos,
  travas de publicação, LGPD).
- `docs/deploy-replit.md`: deploy (Replit + GitHub Pages), operação e riscos aceitos.
- Página **Metodologia** do site (`frontend/src/Metodologia.tsx`, rota `#/metodologia`):
  indicadores, ranking, auditoria e fontes.

## Fluxo do squad (desde 2026-10-08)

O projeto usa o fluxo do squad de `~/.claude/CLAUDE.md` e os agentes de `~/.claude/agents/`.
Onde as regras se chocam, **este arquivo vale** sobre o global.

### Artefatos

- `docs/backlog.md`: tarefas priorizadas (dono: `command`).
- `docs/adr/NNNN-slug.md`: uma decisão por arquivo (dono: `keystone`). Os ADRs 0001 a 0015
  registram decisões que já estavam no código ("Aceito retroativo"). Decisão nova começa
  em "Proposto". Índice em `docs/adr/README.md`.
- `docs/overview.md`: mapa do sistema em cinco minutos.
- `docs/handoffs/AAAA-MM-DD-<de>-para-<para>.md`: passagem de bastão entre agentes.
- A linha de status do ADR é `- **Status:** <valor>`, sem parênteses, para o painel War
  Room conseguir ler.

### Como as regras do squad se encaixam nas regras deste projeto

- **Portão de aprovação.** Os itens de "Pare e peça aprovação do Fabio" (mapeamento de
  contas, regra de cruzamento, exceção, publicação de dado novo, mudança de formato)
  exigem ADR "Aceito" ou aprovação explícita do Fabio antes do código. O mesmo vale para
  metodologia do ranking, travas, LGPD e segurança.
- **Git.** O `main` só recebe por PR, um por vez, com CI verde. Isso vale também para
  `docs/adr/`, `docs/handoffs/` e `docs/backlog.md`: eles são escritos no checkout
  principal (`/home/fasn98/rastro-publico`), nunca dentro de uma worktree, e chegam ao
  `main` por PR. Push e abertura de PR passam pelo Fabio (`permissions.ask`).
- **Worktrees.** `.claude/worktrees/<tarefa>`, branch `feat/<tarefa>` ou `fix/<tarefa>`
  (ignoradas pelo Git). Tarefas que criam migração do Alembic são serializadas (ADR-0003).
- **Papéis neste projeto.**
  - `node-runner`: backend Python (coletores, FastAPI, Alembic, CLI `rastro`, scripts,
    GitHub Actions, Replit). Não há Node no backend.
  - `feather`: frontend React (`frontend/src/`). Toda tela lê por `lerJson`, nunca da API.
  - `scalpel`: pytest com respostas reais em `backend/tests/fixtures/` (ADR-0015).
    Nenhum dado fictício. Fixture de fonte com dado pessoal entra já redigida.
  - `reviewer`: além de código e segurança, confere LGPD, rótulos neutros, fonte e link
    de auditoria de cada número, e travas.
  - `lexicon`: README, READMEs de módulo, `docs/*.md` e a página Metodologia (o texto; o
    código da página é de `feather`).

### Testes

- Backend: `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`.
  Sem o banco `rastro_teste`, os testes de banco são **pulados**: pulado não é passou. A
  referência é o CI (`.github/workflows/ci.yml`, com PostgreSQL 16).
- Frontend: só `npm run build` (`tsc -b` + `vite build`); ainda não há testes.

## Estado em 2026-10-08

- **Stack:** Python 3.12 + uv, FastAPI, SQLAlchemy 2, Alembic (migrações 0001 a 0017),
  PostgreSQL 16; React 19 + TypeScript + Vite; site no GitHub Pages; API de auditoria e
  coleta agendada no Replit.
- **Em produção, em prévia** (faixa + `noindex`): municípios de SP, indicadores fiscais,
  Ranking Fiscal v1.0, políticos de SP (Câmara, Senado, cota, TSE 2022/2024/2026, emendas).
- **CI:** `ci.yml` (backend: ruff + pytest com Postgres; frontend: build) em todo push e
  PR. `coleta.yml`: coleta no Actions, só manual, em fase de teste.
- **Em aberto:** ADR-0016 (Actions ou Replit) e PR #24 (proposta do ranking v1.1, draft).
- **Backlog:** `docs/backlog.md`.
