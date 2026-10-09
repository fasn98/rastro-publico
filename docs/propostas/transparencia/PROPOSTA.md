# Transparência: MSC mensal e pontualidade das entregas (proposta, não implementada)

**Situação:** proposta. Pelo ADR-0019, mudanças de metodologia não entram no `main` até
25/10/2026; este branch fica sem merge até lá.

Base: o extrato de entregas do SICONFI (`extrato_entregas`) dos 645 municípios de SP,
exercícios 2023 a 2025 (1.935 município-anos), baixado em 09/10/2026. O efeito na nota parte
do `ranking.json` publicado em `site-20261009-142118` (v1.1.0). A simulação reproduz a nota
publicada sem diferença nos 645 municípios: média dos indicadores fiscais × transparência.

Reproduzir: `mkdir raw` e `bash baixar.sh <cod> <ano>` para cada código de `codigos.txt` (os 645
municípios de SP, do IBGE) e cada ano; depois `python3 analisar.py ranking.json`.
O resultado completo está em `resultado.md`.

## Prazos legais (Portaria STN nº 642/2019, texto atualizado no SICONFI)

| Entrega | Prazo | Dispositivo |
|---|---|---|
| RREO | 30 dias após o fim de cada bimestre | art. 6º, I |
| RGF | 30 dias após o fim do quadrimestre (ou do semestre, na opção semestral) | art. 6º, II e §3º |
| MSC agregada (mensal) | último dia do mês seguinte ao de referência | art. 8º, §2º |
| DCA | 30 de abril do ano seguinte | art. 4º, §3º (LRF, art. 51, §1º) |

## O que os dados mostram

1. **Incluir a presença da MSC mensal não muda nada.** As 23.220 MSC esperadas (12 por
   município-ano) constam no extrato. Com a MSC como 5º bloco, nenhum município muda de nota
   (correlação de posições 1,000).
2. **A pontualidade é mensurável e diferencia os municípios.** Situação dos itens:

   | Bloco | No prazo | Com atraso | Retificado (data original perdida) | Não entregue |
   |---|---|---|---|---|
   | RREO | 56,6% | 36,6% | 6,8% | 0,0% |
   | RGF do Executivo | 50,5% | 30,6% | 18,9% | 0,0% |
   | RGF do Legislativo | 63,0% | 30,6% | 6,1% | 0,2% |
   | DCA | 78,9% | 15,7% | 5,3% | 0,1% |
   | MSC mensal | 59,9% | 40,1% | não se aplica | 0,0% |

   Mediana do atraso: 13 a 21 dias. No percentil 90, 48 a 114 dias.
3. **A data do extrato se comporta como data de entrega.** Há um pico no último dia do prazo
   e uma queda logo depois: no RREO, 1.054 itens no dia do prazo e 423 no dia seguinte; na
   DCA, 229 e 2.
4. **Limitações que impedem usar a data histórica sem cautela:**
   - **Retificação:** quando o ente retifica (status RE), a data passa a ser a da
     retificação, e a do primeiro envio se perde. São 6% a 19% dos itens, conforme o bloco.
   - **MSC:** a MSC não tem status. Um reenvio pode sobrescrever a data. Exemplo: as MSC de
     janeiro e de fevereiro de 2024 de Votuporanga têm a mesma data, 18/03/2024. Não dá para
     separar um primeiro envio atrasado de um reenvio.
   - **Homologado:** que um item homologado (status HO) guarde a data do único envio é uma
     inferência pelo comportamento dos dados. Não está documentado pelo Tesouro, e falta
     confirmar com o Tesouro (Fale Conosco do SICONFI).

## Efeito na nota (multiplicador, como na v1.1)

| Regra | Índice = 1 | Mediana do índice | Nota 0–2 / 2–4 / 4–6 / 6–8 / 8–10 | Mediana da nota | Correlação de posições | Maior queda |
|---|---|---|---|---|---|---|
| Publicada (v1.1.0) | 98% | 1,000 | 23 / 230 / 296 / 91 / 5 | 4,36 | 1 | — |
| E1: + presença da MSC | 98% | 1,000 | 23 / 230 / 296 / 91 / 5 | 4,36 | 1,000 | 2 |
| P1: no prazo 1; atraso 0,5; falta 0 (sem MSC) | 7% | 0,882 | 53 / 308 / 227 / 56 / 1 | 3,80 | 0,938 | 273 |
| P2: P1 + MSC no prazo | 0% | 0,869 | 56 / 310 / 226 / 51 / 2 | 3,76 | 0,937 | 261 |
| P3: P2, sem contar os retificados | 0% | 0,864 | 61 / 308 / 226 / 49 / 1 | 3,71 | 0,931 | 266 |
| P4: P2 com atraso = 0 | 0% | 0,739 | 160 / 291 / 158 / 35 / 1 | 3,16 | 0,787 | 451 |
| P5: P2 com tolerância de 30 dias (até 30 dias = 1; mais = 0,5) | 18% | 0,981 | 29 / 258 / 275 / 79 / 4 | 4,18 | 0,979 | 239 |

## Custo de coleta

- **Zero requisições a mais.** O extrato já é lido em toda execução, de 2022 até o ano
  corrente, e já guarda a data e o status (`entrega_siconfi`). As linhas da MSC já vêm
  nele.
- O custo é só de cálculo, mais a regra nova.

## Proposta

1. **Até 25/10:** nada muda (ADR-0019).
2. **Passar a guardar a primeira vez que cada item aparece no extrato** (uma coluna e uma
   migração). A coleta semanal vê a entrega com uma semana de precisão, e uma retificação ou
   reenvio posterior não apaga a data. Isso só vale daqui para a frente. Por ser mudança de
   formato do banco, precisa de aprovação.
3. **Depois de pelo menos dois quadrimestres medidos assim**, decidir a regra na v1.2. A
   recomendação inicial é a P5, que penaliza atrasos longos e não o atraso de poucos dias,
   e muda pouco a ordem (0,979). Para os anos anteriores, a data do extrato entraria só como
   contexto, com a limitação explicada, sem peso na nota.
4. Antes de qualquer uso, confirmar com o Tesouro o significado de `data_status`.
