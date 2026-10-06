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
| Tesouro — RREO e RGF do SICONFI | `rastro siconfi-demonstrativos ...` (abaixo) | `demonstrativo_siconfi`, `conta_demonstrativo` |

Peculiaridades dos dados tratadas no código (verificadas nas respostas reais):

- O SICONFI devolve `uf = "BR"` para os estados e o DF, e `uf = null` para a União; a UF
  é derivada do código IBGE.
- O campo `capital` do SICONFI vem como texto com espaços (`"1  "` / `"0  "`).
- O IBGE devolve `microrregiao: null` para municípios criados depois de 2017
  (ex.: Boa Esperança do Norte/MT); a UF é lida da hierarquia de regiões imediatas.
- O IBGE lista 5.571 municípios; o SICONFI tem 5.570 municípios + DF. A diferença é
  Fernando de Noronha (2605459), distrito estadual de PE sem prefeitura própria.

### RREO e RGF (SICONFI)

```bash
uv run rastro coletar siconfi-entes                                   # pré-requisito
uv run rastro siconfi-demonstrativos --exercicio 2025 --ente 3550308  # um município
uv run rastro siconfi-demonstrativos --exercicio 2024 2025 --uf SP     # todos de SP
uv run rastro siconfi-demonstrativos --exercicio 2025 --esfera E D     # estados e DF
uv run rastro siconfi-demonstrativos --exercicio 2025 --todos          # todos (demorado)
```

Como funciona:

1. Lê o **extrato de entregas** do ente para saber o que existe. Municípios com menos
   de 50 mil habitantes costumam entregar **RREO Simplificado** e **RGF Simplificado
   semestral**; consultar "RREO" para eles volta vazio.
2. **Coleta incremental:** compara a data de status do extrato com a da última coleta e
   só baixa relatórios novos ou **retificados**. Use `--forcar` para baixar tudo de novo.
3. O RGF é baixado **por poder** (E, L, J, M, D; municípios só têm E e L).
4. Cada relatório é **substituído por inteiro**, porque não há chave única por linha
   (`cod_conta` se repete entre linhas) e uma retificação pode remover contas.
5. Valores ficam em `NUMERIC` (sem erro de ponto flutuante). Falha em um ente não
   interrompe os outros: a coleta fica com status `parcial` e o erro registrado.

6. O RGF é gravado **por instituição**: um mesmo poder pode ter várias (no Legislativo
   de São Paulo, a Câmara e o Tribunal de Contas do Município; no Judiciário estadual,
   o TJ e o TJ Militar).

Consulta pela API: `GET /api/entes/{cod_ibge}/demonstrativos?exercicio=2025` e
`GET /api/demonstrativos/{id}/contas?anexo=RGF-Anexo 01`.

### Indicadores fiscais

`GET /api/entes/{cod_ibge}/indicadores?exercicio=2025` (e o painel no detalhe do
município) usa o último período entregue no exercício:

| Indicador | Origem | Limites mostrados |
|---|---|---|
| Despesa total com pessoal / RCL ajustada, por instituição | RGF Anexo 1 | alerta, prudencial e máximo (art. 20, 22 e 59 da LRF), como declarados no relatório |
| Dívida consolidada líquida / RCL ajustada | RGF Anexo 2 (Executivo) | alerta e máximo calculados a partir dos valores de limite declarados no relatório |
| Receita realizada x prevista; despesa empenhada, liquidada e paga; resultado orçamentário | RREO Anexo 1 | — |

Percentuais e limites vêm prontos do relatório sempre que ele os traz; o resultado
orçamentário (receita realizada − despesa empenhada) confere com o déficit/superávit
declarado no próprio RREO. Os limites não são fixos no código: a Resolução do Senado
40/2001 prevê 120% da RCL para municípios e 200% para estados, mas o RGF do Estado de
SP no 3º quadrimestre de 2025, por exemplo, declara 169,93%; o painel mostra o valor
declarado. "Acima do limite" compara com os números informados pelo
ente; não substitui a análise do Tribunal de Contas.

Volume medido (exercício 2025): município de São Paulo ≈ 21 mil linhas, Adamantina/SP
≈ 8,5 mil, Estado de SP ≈ 27 mil; cerca de 200 bytes por linha no banco. Cada ente leva
cerca de 10 a 25 requisições por exercício, com pausa configurável entre elas
(`RASTRO_SICONFI_INTERVALO`, padrão 0,2 s).

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
