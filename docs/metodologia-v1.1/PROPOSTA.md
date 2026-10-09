# Ranking Fiscal — proposta da metodologia v1.1

**Situação: aprovada pelo Fabio em 09/10/2026 (D1 a D7, como propostas) e implementada no PR #24.
A publicação depende do merge desse PR, que também precisa da aprovação dele.**

Base: os 645 municípios de SP, exercícios 2023, 2024 e 2025, como publicados em 08/10/2026
(`site-20261008-223829`), mais verificações feitas na API do SICONFI e do IBGE em 08/10/2026.
Todos os números deste documento saem de `simular.py` (resultado completo em `simulacao.md`),
que primeiro reproduz a v1.0 publicada sem nenhuma diferença nos 645 municípios e depois aplica
cada mudança.

## Decisões a aprovar

| # | Proposta | Tipo | Efeito principal |
|---|---|---|---|
| D1 | Ler o relatório da **Prefeitura**, nunca o de um consórcio entregue com o código do município | correção de leitura | Votuporanga passa a ter nota (7,2; 28º); o investimento de 2023 dela, publicado como 1,51% (valor do consórcio), passa a 12,32% |
| D2 | Quando a API omite a linha "recursos não vinculados (I)" do RGF Anexo 5, usar I = IV − II − III | regra de leitura | 11 município-anos passam de "não reportado" a liquidez 0% (o próprio relatório mostra I = 0) |
| D3 | Teto da autonomia: 10 → **7** | âncora | a nota da autonomia deixa de ficar espremida perto de 0 |
| D4 | Transparência como **multiplicador** da nota fiscal, em vez de 5º indicador com peso 1 | peso | as notas deixam de ganhar o mesmo "+10" de quase todos; quem não entregou relatório continua perdendo |
| D5 | Faixas populacionais pela **estimativa do IBGE** (SIDRA 6579), com o ano | fonte | nenhum município muda de faixa hoje |
| D6 | Per capita (com a população do IBGE de cada ano) só como **contexto**, fora da nota | exibição | novos números na página do município, com fonte e ano |
| D7 | Gasto com pessoal acima de 100% da RCL: **manter o valor declarado** na nota e marcar "valor declarado acima de 100% da RCL" | rótulo | 18 município-anos ganham a marca; nenhuma nota muda |

D1, D2 e D3 mudam notas publicadas; D2 é regra de leitura de contas; D4 muda os pesos. Pelo
`CLAUDE.md`, tudo isso precisa da sua aprovação antes de virar código e de ser publicado.

## 1. Distribuição real de cada indicador e âncoras

Município-ano, 2023–2025, como publicados:

| Indicador | mínimo | 1º quartil | mediana | 3º quartil | máximo | âncoras v1.0 | no teto | no piso |
|---|---|---|---|---|---|---|---|---|
| Autonomia (razão) | 0,24 | 2,14 | 3,10 | 4,19 | 21,97 | 1 → 10 | 0,9% | 3,8% |
| Pessoal (% da RCL) | 5,54 | 39,97 | 43,45 | 47,15 | 805,41 | 54% → 37,8% (100% → 70% do limite) | 14,5% | 4,4% |
| Liquidez (% da RCL) | −131,22 | −1,31 | 2,02 | 7,61 | 263,61 | 0% → 20% | 6,9% | 34,3% |
| Investimento (% da receita) | 0,17 | 3,09 | 4,94 | 7,74 | 23,53 | 0% → 10% | 12,5% | 0,0% |
| Transparência (índice) | 0,75 | 1,00 | 1,00 | 1,00 | 1,00 | 0 → 1 | 99,3% | 0,0% |

Proposta de âncoras:

- **Autonomia: teto 7 (D3).** Com teto 10, só 0,9% dos casos chegam à nota máxima, e a nota
  média do indicador é 0,27: ele diferencia pouco. O percentil 95 é 6,94; com teto 7, os 5% mais
  autônomos ficam com nota 1. O piso continua em 1 (a receita local não cobre nem a estrutura
  administrativa).
- **Pessoal: sem mudança.** As âncoras vêm da lei (limite máximo declarado no RGF). 18
  município-anos declaram gasto acima de 100% da RCL (até 805%, Pontal 2025), quase certamente
  erros de preenchimento. Ver D7.
- **Liquidez: sem mudança.** 34% dos casos estão no piso porque o caixa livre, depois dos restos
  a pagar, é zero ou negativo. É uma informação fiscal real, não um defeito da escala.
- **Investimento: sem mudança.** O teto de 10% fica perto do percentil 90 (10,75%).

## 2. Transparência

Hoje o índice é "relatórios disponíveis ÷ esperados" (RREO, RGF do Executivo, RGF do
Legislativo, DCA). Ele vale 1 em 99,3% dos casos, então soma praticamente o mesmo a todas as
notas e quase não muda a ordem.

Opções, todas com D1, D2 e D3:

| Opção | 0–2 / 2–4 / 4–6 / 6–8 / 8–10 | mediana | desvio | correlação de posições com a v1.0 |
|---|---|---|---|---|
| T0: peso 1 (como hoje) | 0 / 38 / 392 / 197 / 18 | 5,5 | 1,14 | 0,988 |
| T1: peso 0,5 | 0 / 127 / 373 / 135 / 10 | 5,0 | 1,27 | 0,988 |
| T2: fora da nota, só informativa | 23 / 229 / 297 / 91 / 5 | 4,4 | 1,43 | 0,988 |
| **T3: multiplicador (nota fiscal × índice)** | 23 / 230 / 296 / 91 / 5 | 4,4 | 1,43 | 0,988 |
| T4: incluir a MSC no índice | igual a T0 | | | |

- **Incluir a MSC não muda nada:** os 645 municípios entregaram as 12 MSC mensais e a de
  encerramento em 2023, 2024 e 2025 (1.935 de 1.935 município-anos, pelo extrato de entregas do
  SICONFI).
- **Pontualidade não dá para medir de forma confiável:** o extrato de entregas só traz
  `data_status`, a data do último status, que muda quando o município retifica o relatório.
- **Recomendação: T3.** A nota passa a refletir só os indicadores fiscais e não ganha o "+10"
  comum a quase todos. Quem deixou de entregar relatório continua perdendo, na proporção do que
  faltou: 14 município-anos estão abaixo de 1 (por exemplo, Sarutaiá 2025, com 0,75).
  T2 descartaria essa penalidade.
- **A queda da mediana (5,3 → 4,4) não é piora dos municípios.** É a retirada de um
  componente que valia 10 para quase todos. A Metodologia precisa dizer isso, com a data da
  mudança.

## 3. População do IBGE: faixas e per capita

- **Faixas (D5):** com a estimativa IBGE 2025 (SIDRA 6579) no lugar da população informada ao
  SICONFI, **nenhum município muda de faixa**. Distribuição: até 10 mil: 271; 10 a 50 mil: 236;
  50 a 100 mil: 57; 100 a 500 mil: 71; acima de 500 mil: 10.
- **Anos disponíveis:** a tabela 6579 tem 2024, 2025 e 2026, mas não tem 2022 nem 2023 (2022 foi
  ano de Censo). Para o exercício 2023, a população oficial mais próxima é a do **Censo 2022**
  (SIDRA 4709). Proposta: 2023 → Censo 2022; 2024 → estimativa 2024; 2025 → estimativa 2025.
- **Per capita (D6), como contexto, fora da nota:**

  | Per capita, 2023–2025 | mínimo | 1º quartil | mediana | 3º quartil | máximo |
  |---|---|---|---|---|---|
  | Receita local (R$) | 413 | 2.225 | 2.772 | 3.674 | 23.225 |
  | Investimento liquidado (R$) | 16 | 216 | 351 | 604 | 5.379 |

  Por que fora da nota: os quatro indicadores já são razões (não dependem do tamanho), e um
  indicador per capita na nota favoreceria municípios pequenos com receitas excepcionais
  (máximo 56 vezes o mínimo na receita local) sem dizer nada sobre a gestão.
- **RGF semestral:** os 114–118 municípios por ano que entregam o RGF por semestre **já são
  tratados corretamente** (2º semestre = período final; a transparência espera 2 relatórios).
  Só falta registrar na Metodologia.

## 4. Correções de leitura (D1, D2) e lacunas da fonte

Indicadores vazios ou errados em 2023–2025, verificados um a um na API do SICONFI:

| Caso | Município-anos | Causa | Proposta |
|---|---|---|---|
| Consórcio no lugar da Prefeitura | Votuporanga 2023–2025 (autonomia, investimento, liquidez) | dois consórcios entregam RREO/RGF com o código de Votuporanga; o código pegava o primeiro em ordem alfabética ("Consórcio…" < "Prefeitura…") | D1 |
| Linha (I) omitida | 11 (Biritiba Mirim 2023, Gastão Vidigal 2024, Monções 2024–2025, Nipoã 2025, Nova Castilho 2024, Nova Luzitânia 2024, Planalto 2024, Queluz 2023, São João de Iracema 2024–2025) | a API não devolve linhas com valor zero; nos 11, o total IV = II + III, então I = 0 | D2 |
| Anexo 5 ausente na fonte | 41 | o RGF do período final não tem o Anexo 5 na API (ex.: Arujá 2023 tem os Anexos 1, 2, 3, 4 e 6) | manter "não reportado", com o motivo |
| Anexo 5 sem totais | 1 (Pedro de Toledo 2023) | idem | idem |
| Sem RGF do Executivo no período final | 1 (Jandira 2025) | idem | idem |
| RREO incompleto | Apiaí 2024 (investimento), General Salgado 2023 (autonomia) | o relatório da Prefeitura não traz as linhas | idem |

Votuporanga é o único município de SP com consórcio entregando RREO/RGF com o próprio código
(conferido no extrato de entregas dos 645 municípios, 2023–2025). A correção D1 vale para
qualquer UF.

## 5. Simulação v1.0 × v1.1 proposta (D1 + D2 + D3 + D4/T3)

| Etapa | com nota | 0–2 / 2–4 / 4–6 / 6–8 / 8–10 | mediana | desvio |
|---|---|---|---|---|
| v1.0 publicada | 644 | 0 / 59 / 417 / 159 / 9 | 5,3 | 1,09 |
| + D1, D2 | 645 | 0 / 59 / 417 / 160 / 9 | 5,3 | 1,09 |
| + D3 | 645 | 0 / 38 / 392 / 197 / 18 | 5,5 | 1,14 |
| + D4 (T3) = v1.1 | 645 | 23 / 230 / 296 / 91 / 5 | 4,4 | 1,43 |

Correlação de posições v1.0 × v1.1: 0,988. Os 20 primeiros e os 20 últimos com v1.0 e v1.1, e os
20 que mais mudam de posição com a contribuição de cada etapa, estão em `simulacao.md`.

Maiores mudanças:

- **São João de Iracema (196º → 503º):** liquidez de 2024 e 2025 passa de "não reportado" (fora
  da média) para 0%, pelo próprio relatório (D2); −277 posições.
- **Nipoã (327º → 425º):** idem, em 2025; −67.
- **Itapetininga, Salto, Taubaté, Pitangueiras e outros (+64 a +89):** autonomia alta, que com
  teto 10 rendia pouca nota (D3).
- **Sarutaiá e Ribeira (−75 e −71):** autonomia baixa (D3) e relatórios faltando em 2025 (D4).

## Depois da aprovação

1. Código: D1 e D2 em `indicadores.py`, `metodologia_v1_1.toml` (versão 1.1.0), D7 no site, D5 e
   D6 com a coleta dos anos do IBGE; testes com respostas reais gravadas em `tests/fixtures/`.
2. Página Metodologia: as mudanças, o motivo e a data; o histórico da v1.0 continua consultável.
3. PR para a sua aprovação antes da publicação, com a simulação refeita sobre a coleta da época.
