# ADRs: decisões de arquitetura

Uma decisão por arquivo, `NNNN-slug.md`. Os ADRs 0001 a 0015 registram decisões que já
estavam no código quando o projeto passou a usar o fluxo do squad, em 2026-10-08
(status "Aceito retroativo"). Decisões novas começam em "Proposto" e só valem depois de
aprovadas pelo Fabio.

| ADR | Decisão | Status |
|---|---|---|
| [0001](0001-backend-em-python-com-uv.md) | Backend em Python 3.12 com uv | Aceito retroativo |
| [0002](0002-postgresql-como-banco-unico.md) | PostgreSQL 16 único, via SQLAlchemy 2 | Aceito retroativo |
| [0003](0003-migracoes-alembic-sequenciais.md) | Migrações Alembic numeradas a partir do main | Aceito retroativo |
| [0004](0004-api-em-fastapi.md) | API FastAPI como fonte única do conteúdo | Aceito retroativo |
| [0005](0005-frontend-react-typescript-vite.md) | SPA React + TypeScript + Vite, rotas por hash | Aceito retroativo |
| [0006](0006-arquivo-bruto-por-sha256.md) | Arquivo bruto de toda resposta, por SHA-256 | Aceito retroativo |
| [0007](0007-redacao-lgpd-na-coleta.md) | Redação LGPD na coleta, também no bruto | Aceito retroativo |
| [0008](0008-armazenamento-enxuto.md) | Tabelas só com as contas mapeadas em YAML | Aceito retroativo |
| [0009](0009-site-estatico-no-github-pages.md) | Site estático exportado pela API, no GitHub Pages | Aceito retroativo |
| [0010](0010-api-de-auditoria-separada.md) | API de auditoria separada, só leitura | Aceito retroativo |
| [0011](0011-travas-de-publicacao.md) | Travas de publicação em Settings | Aceito retroativo |
| [0012](0012-metodologia-do-ranking-em-arquivo-versionado.md) | Metodologia do ranking em arquivo versionado | Aceito retroativo |
| [0013](0013-vinculo-confirmado-de-emendas.md) | Emenda ligada a parlamentar só com vínculo confirmado | Aceito retroativo |
| [0014](0014-uma-coleta-por-vez.md) | Uma coleta por vez (advisory lock) | Aceito retroativo |
| [0015](0015-testes-com-respostas-reais.md) | Testes só com respostas reais gravadas | Aceito retroativo |
| [0016](0016-onde-roda-a-coleta-agendada.md) | Coleta agendada: GitHub Actions ou Replit | **Proposto** |

O status fica numa linha `- **Status:** <valor>`, sem parênteses: o painel War Room lê essa
linha, e todo status que começa com "Propos" aparece como pendente de aprovação.
