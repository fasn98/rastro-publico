# Rastro Público

Coleta, organiza e expõe dados públicos brasileiros (finanças públicas, legislativo,
contratações) a partir das APIs oficiais, para que qualquer pessoa consiga seguir o
rastro do dinheiro e das decisões públicas.

## Arquitetura

```
coletores (Python)  ──►  PostgreSQL  ──►  API (FastAPI)  ──►  frontend (React)
   APIs oficiais        dados normalizados     /api/...         busca e consulta
```

| Parte | Tecnologia | Onde |
|---|---|---|
| Coletores | Python 3.12+, httpx, tenacity (novas tentativas) | `backend/src/rastro/coletores/` |
| Banco | PostgreSQL 16, SQLAlchemy 2, Alembic (migrações) | `backend/src/rastro/models.py`, `backend/alembic/` |
| API | FastAPI | `backend/src/rastro/api/` |
| Frontend | React + TypeScript + Vite | `frontend/` |

Cada execução de coletor fica registrada na tabela `coleta` (fonte, status, quantidade
de registros, erro), consultável em `GET /api/coletas`.

### Fontes implementadas

| Fonte | Comando | Tabela |
|---|---|---|
| IBGE — municípios (API de Localidades) | `rastro coletar ibge-municipios` | `municipio` |
| Tesouro — entes do SICONFI | `rastro coletar siconfi-entes` | `ente_siconfi` |

Peculiaridades dos dados tratadas no código (verificadas nas respostas reais):

- O SICONFI devolve `uf = "BR"` para os estados e o DF, e `uf = null` para a União; a UF
  é derivada do código IBGE.
- O campo `capital` do SICONFI vem como texto com espaços (`"1  "` / `"0  "`).
- O IBGE devolve `microrregiao: null` para municípios criados depois de 2017
  (ex.: Boa Esperança do Norte/MT); a UF é lida da hierarquia de regiões imediatas.
- O IBGE lista 5.571 municípios; o SICONFI tem 5.570 municípios + DF. A diferença é
  Fernando de Noronha (2605459), distrito estadual de PE sem prefeitura própria.

## Como rodar

Requisitos: Docker (ou PostgreSQL 16 local), [uv](https://docs.astral.sh/uv/) e Node 22.

```bash
docker compose up -d db                      # PostgreSQL em localhost:5432

cd backend
uv sync
uv run alembic upgrade head                  # cria as tabelas
uv run rastro coletar                        # roda todos os coletores
uv run uvicorn rastro.api.main:app --reload  # API em http://localhost:8000/docs

cd ../frontend
npm install
npm run dev                                  # http://localhost:5173
```

A conexão com o banco vem de `RASTRO_DATABASE_URL` (veja `.env.example`).

### Testes

```bash
cd backend
uv run pytest        # usa o banco rastro_teste; testes de banco são pulados se ele não existir
uv run ruff check .
```

Os testes não acessam a internet: usam respostas reais gravadas em `backend/tests/fixtures/`.
Para os testes de banco, crie o banco `rastro_teste` (o `docker-compose.yml` cria só
`rastro`): `docker compose exec db createdb -U rastro rastro_teste`.

## Próximas fontes

Domínios já liberados no ambiente: Tesouro (SICONFI/RREO/RGF), IBGE SIDRA, Portal da
Transparência (exige chave), PNCP, dados.gov.br, Banco Central (SGS e Olinda), Câmara,
Senado, DataJud (exige chave pública do CNJ) e LexML.
