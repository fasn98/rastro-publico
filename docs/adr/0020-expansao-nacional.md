# ADR-0020: Expansão nacional do escopo atual (metodologia v1.1.0)

- **Status:** Aceito
- **Data:** 2026-10-09
- **Decidido em:** 2026-10-09 (Fabio: "Plano nacional aprovado, com estas decisões")
- **Autor:** sessão principal
- **Decisor:** Fabio

## Contexto

O site cobre SP (645 municípios). A expansão nacional leva as mesmas fontes, indicadores e
metodologia v1.1.0 para todas as UFs: 5.570 municípios, 26 estados e o DF. É a exceção
prevista no ADR-0019.

Medições em 09/10/2026, com uma coleta real do Acre (22 municípios e o estado, 2022 a
2026, a 1 req/s, código do `main`):

| Medida | Resultado |
|---|---|
| Consultas | 1.435 em 1.673 s (1,17 s por consulta) |
| Consultas por ente e exercício | 12,1 (município); 20,6 (estado: 5 poderes no RGF) |
| Banco | +24 MB (cerca de 0,19 MB por município-exercício; 70% é o arquivo bruto) |
| Exportação | 0,16 s e cerca de 18 KB por município; pico de 89 MB |

Projeção nacional:

- cerca de 300 mil consultas (cerca de 98 h a 1 req/s, ou 12 execuções diárias);
- banco com cerca de 7,5 GB. Em 09/10/2026, o painel Database do Replit mostrava o banco
  de produção com 907,99 MB (só SP) e limite de 100 GB. Com os políticos de SP em cerca
  de 130 MB, a parte fiscal de SP dá cerca de 0,24 MB por município-exercício; para o
  país, cerca de 6,7 GB fiscais, mais 0,6 a 0,8 GB de políticos (estimativa da sessão de
  políticos). A primeira estimativa, de 5,4 a 5,6 GB, usava só a amostra do Acre e citava
  um limite de 10 GiB tirado da página de cobrança do Replit; o painel da conta é a
  referência;
- site com cerca de 155 MB.

## Decisão

1. **Ordem da coleta:**
   - UF por UF, das UFs com menos municípios para as com mais, terminando em MG;
   - primeiro os exercícios do ranking (2023 a 2025); depois 2026 e 2022.
2. **Limite de tempo por execução:** o lote RREO/RGF não começa item novo depois de
   `RASTRO_LOTE_LIMITE_MIN` minutos (padrão 480). O que faltar continua na próxima
   execução, e o resto da coleta (ranking, site) cabe no limite de 11 h do Replit.
   Agendamento diário durante a carga inicial; volta ao semanal quando duas execuções
   completas seguidas couberem em 8 h.
3. **Releitura:**
   - Num lote novo, o exercício corrente e o anterior são relidos sempre.
   - Os três mais antigos são relidos em rodízio de 4 semanas (um quarto dos entes por
     semana), ou se a última leitura passou de 35 dias.
   - Uma retificação de exercício antigo pode levar até 4 semanas para aparecer. A página
     Metodologia diz isso.
4. **Estados (esfera E) e DF:**
   - Só os indicadores pessoal, liquidez e investimento, sem ranking.
   - Sem autonomia: a fórmula é municipal (receita tributária mais as cotas-parte
     recebidas de ICMS, IPVA e ITR) e não é comparável para estados, cujo ICMS já está
     inteiro na receita tributária.
5. **Casos especiais:**
   - **Brasília (5300108):** fica fora do ranking municipal, com link para o DF. No SICONFI
     é um município sem nenhuma entrega; as contas são do DF.
   - **Fernando de Noronha (2605459):** aparece na busca como distrito estadual de PE, sem
     indicadores. Não é município no SICONFI.
   - **Boa Esperança do Norte (5101837):** aparece na tabela e fica fora do mapa, com uma
     nota explicando. Não está na malha mínima do IBGE.
6. **Portão de qualidade por UF antes de publicar:**
   - 100% dos entes da UF com dado ou "não reportado";
   - SHA-256 conferido numa amostra das respostas;
   - 3 municípios sorteados conferidos contra a fonte.

   Uma UF reprovada fica fora, sem bloquear as demais.
   Implementação (PR do portão): `rastro portao` grava o resultado de cada UF e
   `rastro exportar-site --portao` exporta só a parte fiscal das aprovadas. O resultado
   vai para o manifesto, em `ufs.{UF}.fiscal`; o campo `ufs.{UF}.politicos` fica para o
   portão dos políticos. A conferência com a fonte compara as células guardadas (as
   contas do mapeamento) do último RREO de cada sorteado.
   - Uma UF reprovada que já estava no site fica com a versão anterior (grupo `uf:XX`
     do índice); senão, fica fora.
   - A verificação antes de publicar recusa arquivo fiscal de UF fora do site.
   - SP: os arquivos de sempre (`municipios.json`, `ranking.json`, `ranking.csv` e
     `municipios/35*.json`, com os políticos) continuam saindo como antes. A tela de
     políticos (só SP) lê o `municipios.json`, e o CSV de SP sai do `ranking.csv`. O
     portão vale para os arquivos novos de SP (`ranking/SP.json`, `estados/SP.json`, a
     busca e o ranking do Brasil). As telas (PR 3) leem os arquivos por UF e, sem eles
     (exportação antiga), voltam aos de SP.
7. **Arquivos novos do site:** `busca`, `ranking/{UF}`, `ranking/BR`, `geo/{UF}` e
   `estados/{UF}`, aprovados como parte da expansão (ADR-0019). O formato de
   `municipios/{cod}.json` não muda.
8. **Políticos:** a expansão nacional deles (Câmara, Senado, TSE, emendas) é da sessão de
   políticos. O tamanho do site e a ordem de publicação por UF são combinados entre as
   duas sessões.
9. O modo prévia continua ligado.

## Consequências

- Mais fácil: o site cobre o país com a mesma metodologia auditável; cada UF entra só
  depois de passar no portão.
- Mais difícil:
  - a carga inicial ocupa cerca de 12 execuções diárias;
  - durante a carga, o exercício 2026 de SP só é relido quando o lote chegar a SP;
  - retificações de exercícios antigos levam até 4 semanas para aparecer.
- As âncoras da v1.1 foram calibradas com SP. A distribuição nacional vai ser diferente
  (por exemplo, mais municípios no piso da autonomia), sem mudança de metodologia.

## Como revisitar

Mudar a ordem, o limite de tempo ou o rodízio é decisão de operação, com aprovação do
Fabio. Ranking para estados seria metodologia nova (ADR próprio).
