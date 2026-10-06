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

### Auditoria: todo número rastreável até a resposta original

Princípio do portal: todo número precisa ser auditável até a resposta original da fonte.
Isso é feito no core (`backend/src/rastro/coletores/arquivo.py`) e vale para qualquer
coletor que use `novo_cliente()`:

- Toda resposta HTTP é arquivada **antes** de qualquer processamento, em transação
  própria (sobrevive a falhas e rollbacks da coleta), inclusive respostas de erro e novas
  tentativas.
- `resposta_bruta`: URL completa com parâmetros, método, status HTTP, content-type, data,
  duração, tamanho, SHA-256 e a coleta (`coleta_id`) em que ocorreu.
- `payload_bruto`: os bytes originais, comprimidos com gzip, indexados pelo SHA-256 dos
  bytes **originais**; conteúdo idêntico é guardado uma única vez.
- `municipio`, `ente_siconfi`, `entrega_siconfi` e `conta_demonstrativo` têm
  `resposta_id`: cada valor aponta para a resposta (a página exata) de onde saiu.
- API: `GET /api/respostas/{id}/bruto` (bytes originais, cabeçalho `X-Rastro-SHA256`),
  `GET /api/respostas/{id}` (metadados + verificação de integridade),
  `GET /api/demonstrativos/{id}/respostas`.
- `uv run rastro verificar-respostas` recalcula o SHA-256 de todo o arquivo.
- `RASTRO_ARQUIVAR_RESPOSTAS=false` desliga o arquivo (não recomendado).

Dados coletados antes desta funcionalidade não têm origem; recolete com `--forcar`.

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

### Coleta em lote (séries históricas)

Para coletar muitos entes e anos de uma vez, de forma **retomável**:

```bash
uv run python -m rastro.coletores.siconfi_lote --uf SP --anos 2022-2025
# ou: uv run rastro siconfi-lote --uf SP --anos 2022-2025
# amostra: --ente 3550308 3500105 3507209
```

- O lote e cada item (ente × exercício) ficam no banco (`lote_coleta`, `item_lote`).
  Se o processo cair ou for encerrado (Ctrl+C ou SIGTERM do agendador), rodar o
  **mesmo comando** continua de onde parou; itens com falha são tentados de novo até
  `--max-tentativas` (padrão 3). `--novo` ignora o lote aberto e começa outro.
- Todas as requisições passam por um limite global de **1 por segundo**
  (`RASTRO_REQ_POR_SEGUNDO`), inclusive novas tentativas e páginas.
- O extrato de entregas de cada ente/ano é gravado em `entrega_siconfi`.
- Para agendar (ex.: Replit Scheduled Deployment): `backend/scripts/coleta_sp.sh`,
  que aplica as migrações, atualiza municípios/entes, roda o lote de SP 2022–2025 e
  recalcula o ranking.

**Tempo estimado para os 645 municípios de SP, 2022–2025 (2.580 itens):** medido na
amostra de 10 municípios (40 itens): 12,6 requisições por item em média e ~15 s por
item (respostas grandes passam de 1 s). Primeira coleta: **~9 a 11 horas** (~32,5 mil
requisições). Execuções seguintes só baixam relatórios novos ou retificados: ~1
requisição por item (o extrato), **~45 min**.

### Indicadores fiscais

`GET /api/entes/{cod_ibge}/indicadores?exercicio=2025` (e o painel no detalhe do
município) usa o último período entregue no exercício:

| Indicador | Origem | Limites / contexto |
|---|---|---|
| Despesa total com pessoal / RCL ajustada, por instituição | RGF Anexo 1 | alerta, prudencial e máximo (art. 20, 22 e 59 da LRF), como declarados no relatório |
| Dívida consolidada líquida / RCL ajustada | RGF Anexo 2 (Executivo) | alerta e máximo calculados a partir dos valores de limite declarados no relatório |
| Receita realizada x prevista; despesa empenhada, liquidada e paga; resultado orçamentário | RREO Anexo 1 | — |
| Autonomia: (receita tributária + cotas-parte ICMS, IPVA, ITR) ÷ (funções Administração + Legislativa, empenhado) | RREO Anexos 1, 2 e 3 | — |
| Liquidez: caixa líquido após restos a pagar, recursos **não vinculados** ÷ RCL (Executivo) | RGF Anexo 5 (+ RCL do Anexo 2) | contexto: com vinculados (I + II) |
| Investimento: investimentos **liquidados** (exceto intra) ÷ receita total realizada | RREO Anexo 1 | contexto: empenhado e restos a pagar não processados |
| Transparência (provisório): RREO, RGF Executivo, RGF Legislativo e DCA disponíveis ÷ esperados | extrato de entregas + API | — |

O painel mostra também a **evolução por ano** (`GET /api/entes/{cod}/indicadores/serie`).

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

## Ranking Fiscal v1 (municípios de SP)

```bash
uv run rastro ranking --uf SP   # calcula, grava e mostra a distribuição da transparência
```

- **Indicadores:** autonomia, gastos com pessoal, liquidez e investimento (os 4 fiscais) +
  transparência (provisório). Dívida e resultado orçamentário ficam só no painel.
- **Regras em arquivo:** `backend/src/rastro/ranking/metodologia_v1.toml` (normalização
  0–1 linear entre "pior" e "melhor", pesos iguais, janela de 3 exercícios, faixas
  populacionais, mínimo de indicadores). A **versão** e o **hash** do arquivo são gravados
  com cada nota (`nota_ranking`); mudar uma regra exige subir a versão.
- **Ausência:** indicador sem dado em todos os anos = não reportado (sai da média e é
  contado); só a transparência penaliza ausência. Com menos de 3 indicadores fiscais, o
  município fica sem nota.
- **Páginas:** `#/ranking` (mapa, filtro por faixa e busca, CSV) e `#/metodologia`
  (fórmulas, pesos, fontes, escolhas, alternativas descartadas e limitações).
- **API:** `GET /api/ranking?uf=SP&faixa=...&busca=...`, `GET /api/ranking.csv`,
  `GET /api/ranking/{cod_ibge}`, `GET /api/metodologia`.
- Mapa: malha municipal do IBGE em `frontend/public/geo/sp-municipios.json`
  (`frontend/scripts/baixar-malha.sh` para baixar de novo).

**Antes de publicar:** os limites de autonomia (teto 10), liquidez (20%) e investimento
(10%) foram escolhidos com uma amostra de 10 municípios e precisam ser revistos com a
coleta completa. O mesmo vale para a transparência, que deu 100% em toda a amostra.

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
