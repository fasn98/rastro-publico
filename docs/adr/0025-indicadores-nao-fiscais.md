# ADR-0025: Indicadores não fiscais (segurança pública e educação) para uma metodologia v1.2.0

- **Status:** Proposto
- **Data:** 2026-11-07 (rascunho enviado ao Fabio; numerado 0025 em 18/11/2026, depois dos ADRs 0023 e 0024)
- **Autor:** sessão principal
- **Decisor:** Fabio

## Contexto

O Fabio pediu em 07/11/2026 um ADR, só de documento, sobre indicadores não fiscais:

- segurança pública: levantamento das 27 secretarias estaduais (URL oficial, formato,
  periodicidade, publicação por município, contagem por ocorrências ou vítimas e a definição
  de homicídio, latrocínio e roubo);
- educação: o INEP (Ideb e Censo Escolar) como fonte nacional por município;
- para cada indicador, se dá para comparar entre estados sem misturar séries incompatíveis e
  como ele entraria numa metodologia v1.2.0 sem alterar a v1.1.0 publicada.

Este ADR não traz código nem publicação. O site continua na v1.1.0 (ADR-0017), só com
indicadores fiscais, e nenhuma fonte nova entra antes da aprovação do Fabio (CLAUDE.md).

**Como o levantamento foi feito:** leitura das páginas e dos arquivos oficiais em
07/11/2026. Tudo o que não foi lido na fonte oficial está marcado como **não verificado**,
com o motivo. Pistas de notícias ou de memória aparecem só como "pista" e não sustentam
nenhuma decisão. Nenhum bloqueio foi contornado.

**Limites de acesso nesta pesquisa:**

- Não abriram: SE, AL, CE, PB, RN, MA, TO e AP, por conexão recusada, erro 503, falha de
  TLS, CAPTCHA ou DNS.
- Abriram só em parte: SP (aplicativo com API de exportação, que recusou a conexão), MG (o
  CSV oficial respondeu 403), MS e AC (só a URL do painel) e AM (painel Power BI).
- Os arquivos do INEP (`download.inep.gov.br`) não abriram: o servidor não envia o
  certificado intermediário da cadeia TLS, e a verificação TLS não foi desligada.

## Segurança pública: as 27 secretarias

Legenda das colunas:

- **Unidade:** V = vítimas; O = ocorrências.
- **HD:** o que o homicídio doloso publicado inclui ou exclui, segundo a nota oficial.
- **MIP:** morte por intervenção de agente do Estado.
- n.v. = não verificado.

| UF | Órgão e URL | Formato | Periodicidade e período | Por município | Unidade | HD (feminicídio, MIP) | Roubo |
|---|---|---|---|---|---|---|---|
| RS | SSP/RS, https://ssp.rs.gov.br/indicadores-criminais | XLSX (2012–2026), XLS (2002–2011) | mensal, até set/2026 | sim, todos | HD e latrocínio em O e V; roubo em O | separação da coluna HD: n.v. (a nota do CVLI lista feminicídio e MIP à parte) | "Roubos" e "Roubo de veículo" em colunas separadas; carga não aparece |
| SC | SSP/SC (GEAC), https://ssp.sc.gov.br/segurancaemnumeros/ | PDF | boletim mensal, jan/2023–set/2026 | homicídio sim; roubo só estadual; latrocínio n.v. | homicídio V; roubo O | sem nota escrita; feminicídio e confrontos em linhas separadas | n.v. |
| PR | SESP/PR (CAPE), https://www.seguranca.pr.gov.br/CAPE/Estatisticas | PDF (painel Qlik n.v.) | anual, 2007–2025 | mortes sim; roubo só por AISP | mortes V (NT 001/2012); roubo O | feminicídio em coluna separada; MIP n.v. | roubo de veículo em tabela própria |
| SP | SSP/SP, https://www.ssp.sp.gov.br/estatistica/dados-mensais | n.v. (aplicativo; a API de exportação recusou a conexão) | n.v. | n.v. | n.v. | n.v. | n.v. |
| RJ | ISP, https://www.ispdados.rj.gov.br/estatistica.html | CSV (`BaseMunicipioMensal.csv`) | mensal, jan/2014–set/2026 | sim, 92, com código IBGE | letais V; roubo O | feminicídio dentro do HD de 2016 a set/2024 e separado desde out/2024; MIP fora; confronto com agente dentro do HD desde nov/2025 | "Total de roubos" inclui veículo e carga |
| MG | Sejusp/MG, https://dados.mg.gov.br/dataset/crimes-violentos | CSV/JSON (download recusou com 403) | mensal, arquivos de 2019 a 2026 | sim, pelo schema (`cod_municipio`) | "registros" (O); homicídio ambíguo | n.v. ("consumado e tentado") | n.v. |
| ES | SESP/ES, https://observatorio.sesp.es.gov.br/serie-historica-de-dados | XLSX e CSV de microdados | mensal (CSV de 2018 a out/2026) | sim, nos microdados | homicídio e latrocínio V; roubo O | feminicídio separado desde jan/2025; MIP fora | 4 tipos; sem veículo |
| MS | Sejusp/MS, http://estatistica.sigo.ms.gov.br/ | n.v. (painel não respondeu) | n.v. | n.v. | n.v. | n.v. | n.v. |
| MT | Sesp/MT, https://www.sesp.mt.gov.br/estatisticas-mt e /anuario-sesp | planilhas Google (não abriram) e PDF anual | anual, 2019–2025 | não, por RISP | HD e latrocínio V; roubo O | HD não inclui feminicídio; MIP não mencionada | roubo total e de veículo separados |
| GO | SSP/GO, https://goias.gov.br/seguranca/estatisticas/ | PDF | anual com meses, 2018–2025 | não (só estadual) | O ("ocorrências reativas") | HD exclui MIP (Portaria 0028/18); feminicídio em linha separada | por tipo, sem total |
| DF | SSP/DF, https://www.ssp.df.gov.br/dados-por-regiao-administrativa/ | PDF e XLSX | mensal, 2014–out/2026 | por região administrativa (33) | não declarada | CVLI = homicídio + feminicídio + latrocínio + lesão seguida de morte; MIP não aparece | por tipo, sem carga |
| BA | SSP/BA, https://www.ba.gov.br/ssp/publicacoes/Estat%C3%ADstica | XLSX, PDF, microdados | mensal, 2015–set/2026 | sim, todos, com código IBGE | CVLI V; roubo n.v. | CVLI com 10 naturezas, sem MIP (MVI = CVLI + MIP) | veículo e carga pela Res. ConSinesp 6 |
| SE | SSP/SE | n.v. (conexão recusada) | n.v. | n.v. | n.v. | n.v. | n.v. |
| AL | SSP/AL | n.v. (conexão recusada; pista: boletins em PDF no dados.al.gov.br) | n.v. | n.v. | n.v. | n.v. | n.v. |
| PE | SDS/PE, https://www.sds.pe.gov.br/estatisticas | XLSX de microdados, PDF | mensal, CVLI desde jan/2004, CVP desde jan/2014, até out/2026 | sim, 185 | CVLI e MVI V; CVP O | feminicídio como natureza separada dentro do CVLI; MIP fora do CVLI (no MVI) | CVP = todos os roubos; tipo não informado no microdado |
| PB | SESDS/PB | n.v. (CAPTCHA) | n.v. | n.v. | n.v. | n.v. | n.v. |
| RN | SESED/RN | n.v. (DNS) | n.v. | n.v. | n.v. | n.v. | n.v. |
| CE | SSPDS/CE | n.v. (503 e TLS) | n.v. | n.v. | n.v. | n.v. | n.v. |
| PI | SSP/PI (DataSSP), https://www.ssp.pi.gov.br/datassp/estatisticas-criminais/ | só painel (Metabase, Looker), sem arquivo | contínua; "dados finais até 2024" | sim, no painel | MVI e CVLI V; roubo O | MVI inclui MIP, homicídio no trânsito e "morte a esclarecer com indício de crime" | n.v. |
| MA | SSP/MA | n.v. (DNS) | n.v. | n.v. | n.v. | n.v. | n.v. |
| TO | SSP/TO | n.v. (503) | n.v. | n.v. | n.v. | n.v. | n.v. |
| PA | Segup/PA, https://sistemas.segup.pa.gov.br/transparencia/ e https://codec.segup.pa.gov.br/ | painel e consulta com download (limite de 1 ano por consulta) | mensal, até out/2026 | sim, municípios e bairros | CVLI V; roubo O ("casos") | MIP separada; feminicídio crime autônomo desde a Lei 14.994/2024 | n.v. |
| AP | Sejusp/AP | n.v. (503) | n.v. | n.v. | n.v. | n.v. | n.v. |
| AM | SSP/AM, https://www.ssp.am.gov.br/ssp-dados/ | Power BI (n.v.); catálogo e notas técnicas em PDF | mensal (NT 004/2022) | n.v. | catálogo: O | HD exclui feminicídio, latrocínio e mortes com excludente (MIP separada) | latrocínio inclui roubo de veículo e de carga |
| RR | Polícia Civil/RR, https://policiacivil.rr.gov.br/estatisticas/ | XLSX | anual, 2019–2025 | sim | MVI V (IML); veículos em BO | linhas separadas; a base de MVI tem 471 linhas de "SUICÍDIO" sem nota | só veículo e celular |
| AC | Sejusp/AC, https://sejusp.ac.gov.br/estatisticas/ | Power BI (n.v.) | n.v. | n.v. | n.v. | n.v. | n.v. |
| RO | Sesdec/RO, https://observatorio.sepog.ro.gov.br/sesdec/indicadores | painel com exportação Excel | dados até 31/10/2026 | sim | O | sem nota; MIP em filtro separado | n.v. |

**Leitura das secretarias:**

- **Não há duas secretarias com a mesma definição de homicídio doloso.**
  - Feminicídio: fica dentro do homicídio no RJ até set/2024 e fora dele no MT, no AM e no
    ES desde 2025.
  - MIP: fica dentro do MVI do PI e fora do homicídio em GO, no RJ, no AM e no ES.
  - Homicídio no trânsito, "morte a esclarecer" e confronto com agente entram em umas e não
    em outras.
- **A unidade de contagem varia:** vítimas (RS, RJ, ES, PE, BA, PA, MT, RR), ocorrências
  (GO, AM, RO) ou não declarada (DF).
- **Por município:**
  - Não há publicação por município em GO, no MT, no roubo de SC e no roubo do PR.
  - Fica n.v. em 12 UFs.
- **A definição muda ao longo do tempo dentro da mesma UF:** RJ (out/2024 e nov/2025), ES
  (jan/2025), PA (Lei 14.994/2024).
- **LGPD:**
  - ES e RR publicam microdados por vítima, com logradouro, idade, cor e coordenadas.
  - Uma coleta teria de agregar por município sem gravar esses campos (ADR-0007).

**Conclusão:** uma série estadual não se compara com a de outra UF, e nenhuma delas cobre as
27 UFs por município. Comparar as 27 séries das secretarias num mesmo ranking seria misturar
séries incompatíveis.

## Fontes nacionais

### Sinesp VDE (Ministério da Justiça e Segurança Pública)

- **Página e arquivos:**
  - página oficial: https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/estatistica
  - "Base de Dados e Notas Metodológicas dos Gestores Estaduais - Sinesp VDE 2015 a 2026",
    atualizada em 06/11/2026;
  - um XLSX por ano, de 2015 a 2026, em
    `.../dnsp-base-de-dados/bancovde-AAAA.xlsx/@@download/file`. Exemplo: o de 2025 tem
    26.644.102 bytes e SHA-256 `953956b2…9cebc`.
- **Detalhe:** mensal, por município, só com o **nome** do município, sem código IBGE. Há
  homônimos, como UNA, ITU e POÁ, e uma linha "NÃO INFORMADO" por UF.
- **Eventos por município** (2025: os 5.570 municípios):
  - homicídio doloso, latrocínio, lesão corporal seguida de morte e feminicídio;
  - tentativa de homicídio, suicídio, morte no trânsito e mortes a esclarecer.
- **Eventos só por UF:**
  - roubo de veículo, roubo de carga e roubo a instituição financeira;
  - estupro;
  - morte por intervenção de agente do Estado;
  - tráfico.
- **Não há roubo comum por município.**
- **Unidade:**
  - vítimas: homicídio, latrocínio, lesão seguida de morte e feminicídio;
  - ocorrências: os roubos.
- **Definições e origem:**
  - as definições vêm da Resolução nº 06 do ConSinesp e da Portaria 229/2018;
  - os dados são informados pelos gestores estaduais, ficam validados até o dia 15 do mês
    seguinte e podem mudar depois.
- **Limites:**
  - as notas por UF mostram diferenças de registro: o RJ conta pela data do registro; o AM
    reclassificou "mortes a esclarecer" em 2022; o TO não tem vários indicadores de 2015 a
    2018;
  - a série municipal não é completa em todos os anos: o ES tem 0 municípios em homicídio
    doloso em 2015;
  - as notas de SP e das UFs no fim da página: n.v.

### SIM / DATASUS (Ministério da Saúde)

- **Página:** TabNet "Óbitos por Causas Externas" por UF (`sim/cnv/ext10XX.def`).
  - A de SP foi verificada: linha Município, óbitos por residência ou por ocorrência, 1996 a
    2026.
  - As outras 26 UFs: n.v. (pista: o mesmo padrão de nome).
- **Indicador:** o grupo "Agressões" (CID-10 X85–Y09), a partir da Declaração de Óbito.
  - É uma fonte nacional e uniforme.
  - Mede óbitos por agressão, não "homicídio doloso" no sentido policial.
- **Defasagem:**
  - dados finais até 2024 (extração de 02/12/2025);
  - 2025 preliminar; 2026 em prévia.
- **Ainda n.v.:** microdados e FTP (timeout), e o tratamento da MIP na classificação.

### INEP: Ideb

- **Página:** https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb/resultados
  - Aba "2005 | 2025", com ZIP municipais de 2025 para anos iniciais, anos finais e ensino
    médio.
  - Ideb 2025 divulgado em 05/08/2026.
- **Regra de divulgação** (Portaria 435/2025, art. 22):
  - o município tem resultado com no mínimo 10 estudantes e 50% de participação;
  - município com uma única escola avaliada que não atinge 80% fica sem resultado.
  - Portanto, nem todo município tem Ideb.
- **Ainda n.v.** (arquivos fora do ar para esta sessão):
  - as redes publicadas nos arquivos;
  - como os municípios sem resultado aparecem;
  - as edições anteriores a 2025;
  - a nota oficial sobre a pandemia no Ideb 2021.

### INEP: Censo Escolar

- **Páginas e anos:**
  - microdados de 1995 a 2025: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar
  - sinopse de 1995 a 2025: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/sinopses-estatisticas/educacao-basica
  - anual, com participação obrigatória de todas as escolas.
- **LGPD:**
  - desde 2022, os microdados foram reestruturados para impedir a identificação de pessoas
    (NT 5/2021, ANPD NT 12/2023, ação civil pública transitada em 20/03/2026);
  - o projeto usaria só agregados por município.
- **Ainda n.v.:** se a sinopse traz tabelas por município.

## Comparabilidade, indicador por indicador

| Indicador | Fonte que serviria às 27 UFs | Comparável entre estados? | Situação |
|---|---|---|---|
| Vítimas de homicídio doloso por 100 mil | Sinesp VDE (por município) | **Em parte.** Uma só definição nacional (ConSinesp), mas informada por cada UF com práticas diferentes (data do fato ou do registro, reclassificações) | candidata, com nota de limitação por UF |
| Óbitos por agressão por 100 mil | SIM/DATASUS (por município de residência) | **Sim.** É a mesma classificação (CID-10) em todo o país, mas não é a mesma coisa que homicídio doloso, e o dado final chega com cerca de 1 ano de atraso | candidata, como série de saúde, separada da policial |
| Latrocínio | Sinesp VDE | Mesma ressalva do homicídio. Os números municipais são pequenos e oscilam muito | só contagem (sem taxa) ou agregado de 3 anos |
| Roubo | nenhuma: o Sinesp só tem roubo por UF; as secretarias divergem e várias não publicam por município | **Não** | fora da v1.2.0; marcar "não publicado pela fonte oficial" |
| Séries das secretarias (SSP) | 27 fontes diferentes | **Não**, entre UFs | se entrarem um dia, só dentro da própria UF, com a definição dela e sem ranking entre UFs |
| Ideb (anos iniciais e finais) | INEP | **Sim.** Mesma prova e mesma fórmula em todo o país; municípios abaixo da participação mínima ficam sem resultado | candidata, com "sem resultado divulgado pelo INEP" quando não houver |
| Matrículas e escolas (Censo Escolar) | INEP | **Sim** | candidata como contexto, sem peso |

## Proposta para a v1.2.0 (para decisão do Fabio)

1. **A v1.1.0 não muda.**
   - O Ranking Fiscal v1.1, com as fórmulas, os pesos e o `metodologia_v1_1.toml`, continua
     publicado como está.
   - A v1.2.0 seria um arquivo novo, `metodologia_v1_2.toml`, com o hash próprio no manifesto.
     O ADR-0012 já prevê isso.
2. **Os indicadores novos entram primeiro como informação, sem nota e sem peso no ranking.**
   - Cada número traz a fonte, o link, o período e a data da coleta.
   - Cada indicador traz a nota de limitação da UF (Sinesp) ou da regra de divulgação (Ideb).
   - Colocar algum deles no ranking seria um ADR posterior, depois de ver a distribuição real.
3. **Uma série por indicador, a mesma nas 27 UFs:**
   - Sinesp VDE para homicídio doloso e latrocínio;
   - SIM para óbitos por agressão;
   - INEP para Ideb e Censo Escolar.
   - As séries das secretarias não entram na comparação entre UFs.
4. **Roubo fica fora.** Nenhuma fonte cobre as 27 UFs por município com a mesma definição.
5. **Lacunas aparecem como lacunas:**
   - "não publicado pela fonte oficial" (por exemplo, o ES em 2015 no Sinesp);
   - "sem resultado divulgado pelo INEP";
   - nunca zero nem estimativa.
6. **Rótulos neutros:** "vítimas de homicídio doloso registradas", "óbitos por agressão", sem
   cor de bom ou ruim.

## Decisões pendentes antes de qualquer código

1. **Regra de cruzamento Sinesp ↔ IBGE.** O Sinesp traz só UF e nome do município. Cruzar
   por UF + nome normalizado exige uma regra aprovada, com exceções por homônimos e grafias e
   a exigência de 100% de cruzamento por UF, como no TSE.
2. Aprovar a lista de indicadores da tabela acima, ou parte dela.
3. Aprovar a forma de entrada: só informativa (recomendada) ou com peso num ranking.
4. **Rede da produção.** O Replit precisa alcançar `www.gov.br` (Sinesp), o TabNet do
   DATASUS e `download.inep.gov.br`. Nesta sessão, o INEP falhou na cadeia TLS. A produção
   precisa ser testada antes.
5. **Publicação de dado novo.** Exige aprovação explícita, UF por UF, no portão.

## O que falta verificar antes de implementar

- O conteúdo dos arquivos do INEP: redes, marcação de "sem resultado", edições anteriores a
  2025 e a nota da pandemia em 2021.
- As notas metodológicas do Sinesp de SP e das UFs no fim da página.
- O tratamento da MIP no SIM.
- Os tópicos marcados n.v. na tabela das secretarias. Eles não bloqueiam a proposta, que não
  usa as séries das secretarias.

## Consequências

- **Mais fácil:**
  - o site ganha segurança e educação com uma fonte nacional por indicador;
  - nada da v1.1.0 muda.
- **Mais difícil:**
  - o cruzamento por nome no Sinesp;
  - a defasagem de cerca de 1 ano do SIM;
  - os municípios sem Ideb;
  - notas de limitação por UF em cada indicador.

## Como revisitar

- Se o Sinesp passar a publicar o código IBGE ou roubo por município, o roubo e o cruzamento
  podem ser revistos.
- Usar uma série estadual de SSP exigiria ADR próprio, só dentro da UF.
