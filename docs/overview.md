# Rastro Público: visão geral

Coleta dados públicos brasileiros das fontes oficiais (finanças dos municípios e do estado,
políticos, emendas) e publica um site estático em que **todo número leva à resposta
original da fonte**. Escopo atual: estado de SP.

```
 fontes oficiais                       backend (Python, um pacote: rastro)
 SICONFI, IBGE, Câmara,   ──HTTP──►  coletores ──► arquivo bruto (SHA-256, LGPD redigido)
 Senado, TSE, Portal da               │                     │
 Transparência                        ▼                     │
                                 PostgreSQL ◄───────────────┘
                                      │
                    ┌─────────────────┼──────────────────────┐
                    ▼                 ▼                      ▼
              API FastAPI      exportar-site (JSON)    API de auditoria
              (dev/consulta)   chama as rotas da API   (Replit, só leitura)
                                      │                      ▲
                                      ▼                      │ links "resposta original"
                               GitHub Pages (gh-pages) ──────┘
                               SPA React + Vite
```

## Onde mora cada coisa

| Responsabilidade | Onde |
|---|---|
| Coletores e arquivo bruto | `backend/src/rastro/coletores/` |
| Políticos (Câmara, Senado, TSE, emendas, LGPD, vínculo) | `backend/src/rastro/politicos/` |
| Modelos e migrações | `backend/src/rastro/models.py`, `backend/alembic/versions/` |
| Indicadores e ranking | `backend/src/rastro/indicadores.py`, `backend/src/rastro/ranking/` |
| API | `backend/src/rastro/api/` |
| Exportação e publicação do site | `backend/src/rastro/site.py`, `publicacao.py` |
| Trava de coleta | `backend/src/rastro/trava.py` |
| CLI | `backend/src/rastro/cli.py` (comando `rastro`) |
| Coleta agendada | `backend/scripts/coleta_sp.sh`; Replit Scheduled e `.github/workflows/coleta.yml` |
| Frontend | `frontend/src/` |
| CI | `.github/workflows/ci.yml` |

Detalhes: `README.md`, `backend/src/rastro/politicos/README.md`, `docs/deploy-replit.md`,
`docs/coleta-actions.md`.

## Decisões

Lista e status em [`docs/adr/README.md`](adr/README.md). Em aberto: ADR-0016 (onde roda a
coleta agendada).
