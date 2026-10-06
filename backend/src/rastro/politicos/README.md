# Módulo de políticos (estado de SP)

Quem ocupa cada cargo e os fatos registrados nas fontes oficiais sobre sua atuação.

**Princípios.**
- Somente fatos verificáveis de fontes oficiais, cada um com link para a fonte, período e
  data da coleta.
- Nenhuma nota, ranking, adjetivo ou juízo sobre políticos.
- Ordenação neutra: alfabética nas listas de pessoas e cronológica nas listas de atos.
- Toda página de político tem o link **"Contestar um dado"**, que abre uma issue pública
  no repositório já com o endereço da página.

## Situação (06/10/2026)

| Item | Situação |
|---|---|
| Deputados federais por SP (Câmara): mandato, proposições, votos nominais, presenças | feito |
| Cota parlamentar (CEAP) dos deputados de SP | feito (arquivo anual da Câmara) |
| Senadores por SP (Senado): mandato, matérias, votações, comissões | feito |
| Eleitos 2024 (prefeitos e vereadores) e 2022 (governador, deputados estaduais), TSE | **publicado** (aprovado em 06/10/2026) |
| Emendas parlamentares (Portal da Transparência, arquivo em lote) | coletado; **publicação travada** até validação do vínculo de autores |
| Emendas pela API do Portal (`emendas-api`) | implementado; aguardando a chave em `RASTRO_TRANSPARENCIA_CHAVE` |
| Eleitos 2026 (governador, senadores, deputados federais e estaduais) | coletado (arquivo gerado pelo TSE em 05/10/2026); **publicação travada** até depois do 2º turno |

**Travas de publicação** (`rastro.config.Settings`, valem para a API e para o site
exportado a partir dela):

| Trava | Padrão | Variável que sobrepõe |
|---|---|---|
| `pol_publicar_tse` | ligada | `RASTRO_POL_PUBLICAR_TSE` |
| `pol_publicar_tse_2026` | desligada | `RASTRO_POL_PUBLICAR_TSE_2026` |
| `pol_publicar_emendas` | desligada | `RASTRO_POL_PUBLICAR_EMENDAS` |

## Como coletar

```bash
uv run alembic upgrade head
uv run rastro coletar ibge-municipios                          # pré-requisito
uv run rastro politicos --uf SP --anos 2023-2026 --fontes camara senado
uv run rastro politicos --uf SP --anos 2023-2026 --fontes emendas   # arquivo em lote, sem chave
uv run rastro politicos --fontes tse                           # eleitos 2022 e 2024
uv run rastro politicos --fontes tse --eleicoes 2024           # só um ano
uv run rastro redigir-respostas    # uma vez, em bancos coletados antes da redação LGPD
```

**Coleta e auditoria.**
- Cada fonte vira uma execução na tabela `coleta`: `pol-camara`, `pol-senado`,
  `pol-emendas` e `pol-tse`.
- Toda resposta recebida fica no arquivo de respostas brutas, e cada linha das tabelas
  `pol_*` guarda o `resposta_id` de onde saiu.
- Uma falha em um deputado ou ano não interrompe os demais: a coleta fica `parcial`,
  com os erros registrados.
- O limite é de 1 requisição por segundo.

**Tempos medidos em 06/10/2026, SP:**
- Câmara (com cota) e Senado, ano de 2025, numa só execução: 3 min 10 s. Foram 90
  deputados, 8.884 proposições, 24.565 votos, 14.936 presenças e 25.844 lançamentos de
  cota.
- TSE 2022 e 2024: 31 s.
- Emendas: 8 s.

## Fontes

| Dado | Fonte oficial | Tabela |
|---|---|---|
| Deputados da legislatura 57 | `GET dadosabertos.camara.leg.br/api/v2/deputados?siglaUf=SP&idLegislatura=57` | `pol_politico` |
| Em exercício e partido atual | `GET .../api/v2/deputados?siglaUf=SP` | `pol_politico` |
| Proposições | `GET .../api/v2/proposicoes?idDeputadoAutor={id}&ano={ano}` | `pol_proposicao` |
| Votos nominais | arquivos `dadosabertos.camara.leg.br/arquivos/votacoesVotos/csv/votacoesVotos-{ano}.csv` e `votacoes-{ano}.csv` | `pol_votacao` |
| Presenças | arquivo `.../arquivos/eventosPresencaDeputados/csv/eventosPresencaDeputados-{ano}.csv` | `pol_presenca` |
| Cota parlamentar | arquivo `www.camara.leg.br/cotas/Ano-{ano}.csv.zip` | `pol_despesa_cota` |
| Senadores em exercício | `GET legis.senado.leg.br/dadosabertos/senador/lista/atual.json` | `pol_politico` |
| Matérias | `GET .../dadosabertos/processo?codigoParlamentarAutor={cod}&ano={ano}` | `pol_proposicao` |
| Votações | `GET .../dadosabertos/votacao?codigoParlamentar={cod}&dataInicio=&dataFim=` | `pol_votacao` |
| Comissões | `GET .../dadosabertos/senador/{cod}/comissoes.json` | `pol_comissao` |
| Eleitos (TSE) | `cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip` | `pol_politico`, `pol_pendencia` |
| Código TSE ↔ IBGE | `cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip` | (usado na carga) |
| Emendas (arquivo) | `portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO` → `EmendasParlamentares.csv` | `pol_emenda` |
| Emendas (API) | `GET api.portaldatransparencia.gov.br/api-de-dados/emendas` (cabeçalho `chave-api-dados`) | `pol_emenda` |

### TSE: eleitos e cruzamento TSE ↔ IBGE

**Colunas.** O arquivo `consulta_cand_{ano}_SP.csv` tem 50 colunas, conferidas em 2024 e
2022, no layout da tabela abaixo (`;`, Latin-1).

| Uso | Colunas |
|---|---|
| Usadas | `ANO_ELEICAO`, `CD_TIPO_ELEICAO`, `NR_TURNO`, `CD_ELEICAO`, `DS_ELEICAO`, `DT_ELEICAO`, `SG_UF`, `SG_UE`, `NM_UE`, `DS_CARGO`, `SQ_CANDIDATO`, `NM_URNA_CANDIDATO`, `SG_PARTIDO`, `DS_SIT_TOT_TURNO` |
| **Removidas (LGPD), também do arquivo bruto** | `NM_CANDIDATO`, `NM_SOCIAL_CANDIDATO`, `NR_CPF_CANDIDATO`, `DS_EMAIL`, `SG_UF_NASCIMENTO`, `DT_NASCIMENTO`, `NR_TITULO_ELEITORAL_CANDIDATO`, `CD_GENERO`, `DS_GENERO`, `CD_GRAU_INSTRUCAO`, `DS_GRAU_INSTRUCAO`, `CD_ESTADO_CIVIL`, `DS_ESTADO_CIVIL`, `CD_COR_RACA`, `DS_COR_RACA`, `CD_OCUPACAO`, `DS_OCUPACAO` |
| Mantidas no arquivo bruto, não usadas | demais colunas (geração, tipo de eleição, partido, federação, coligação, situação da candidatura) |

**Cruzamento.** Usa a tabela oficial do TSE "Códigos oficiais de UF e municípios segundo o
TSE e o IBGE", de 04/10/2026:
- 645 municípios de SP, todos com par único nos dois sentidos;
- todos os 645 códigos da API de Localidades do IBGE estão na tabela;
- os 645 `SG_UE` do arquivo de 2024 têm par;
- único nome que difere: São Luís do Paraitinga (TSE) e São Luiz do Paraitinga (IBGE),
  o mesmo município (código 3550001).

A carga falha sem gravar nada se o par não for único ou se faltar algum município.

**Regra de eleitos.**
- Por município (ou UF) e cargo, vale a eleição mais recente do arquivo que tem eleitos:
  a ordinária ou uma suplementar.
- Contam como eleitos os candidatos com situação ELEITO, ELEITO POR QP ou ELEITO POR
  MÉDIA; no 2º turno, vale a linha do 2º turno.
- Se houver suplementar posterior ainda sem resultado, o cargo fica **pendente**, com o
  motivo.

**Resultado 2024:**
- 641 prefeitos, sendo 630 da eleição ordinária e 11 de suplementares: Bocaina, Brejo
  Alegre, Eldorado, Guará, Guatapará, Mongaguá, Neves Paulista, Panorama, Reginópolis,
  Sales Oliveira e Tuiuti.
- 7.047 vereadores, nos 645 municípios.
- 4 pendências, com texto neutro e link para o arquivo de origem:
  - Macedônia, Martinópolis e Narandiba: "Não consta prefeito eleito no arquivo do TSE.
    Suplementar de … marcada para 25/10/2026, ainda sem resultado no arquivo.";
  - Sarutaiá: "Não consta prefeito eleito no arquivo do TSE."

**Resultado 2022:**
- Governador: Tarcísio (REPUBLICANOS), eleito no 2º turno.
- 94 deputados estaduais.

**Fora desta carga:**
- Senador e deputados federais vêm da Câmara e do Senado, porque mostram quem está em
  exercício.
- Vice-prefeito, vice-governador e suplentes de senador estão fora do escopo.

**2026** (mesmo coletor, mesma redação). Arquivo gerado pelo TSE em 05/10/2026 10:14:11.
Traz 1 governador (Tarcísio, ELEITO no 1º turno), 2 senadores (André do Prado e Guilherme
Derrite), 70 deputados federais e 94 estaduais. A situação de cada candidatura é gravada
como está no arquivo:
- `DS_SIT_TOT_TURNO`: ELEITO, ELEITO POR QP ou ELEITO POR MÉDIA;
- `DS_SITUACAO_CANDIDATURA`: em 05/10/2026, "#NE" em todas as linhas, ou seja, o arquivo
  ainda não traz a situação jurídica (sub judice etc.).

Quando a trava for ligada, a tela mostra a seção "Eleitos em 2026 por SP — resultado
divulgado pelo TSE em 05/10/2026, mandato a partir de 2027". O cruzamento TSE ↔ IBGE não
se aplica a 2026, porque são cargos estaduais e federais, sem município.

`data_divulgacao` é o `DT_GERACAO` do arquivo, ou seja, quando o TSE gerou aquele arquivo.
Os arquivos de 2022 e 2024 são regerados diariamente.

**Limites do dado:** são os eleitos segundo o TSE. Posse, cassação ou substituição
posteriores não aparecem nesse arquivo.

### Emendas: arquivo em lote, com código IBGE oficial

O arquivo `EmendasParlamentares.csv` (94.627 linhas em 06/10/2026, de 2014 a 2026) traz,
além do texto `Localidade de aplicação do recurso`, a coluna oficial **`Código Município
IBGE`**. O município de destino vem dessa coluna, não do texto.

**Linhas com destino em SP, de 2023 em diante: 2.922.**
- 536 com código de município (todos válidos no IBGE).
- 1.296 marcadas "MÚLTIPLO" (vários municípios, sem código).
- 1.090 marcadas "SÃO PAULO (UF)".

As linhas sem código não entram em "emendas recebidas" de nenhum município.

**Cruzamento só pelo texto, comparado com o código oficial:** 518 de 536 (96,64%) iguais,
nenhum par divergente e 18 sem par:
- "EMBU" (17 linhas), nome antigo de Embu das Artes;
- "SÃO LUÍS DO PARAITINGA" (1 linha).

Com o código oficial, 100% das linhas com código ficam resolvidas.

**Autor → parlamentar: só com vínculo confirmado** (`politicos/vinculo.py`). Uma emenda
só aparece ligada à página de um político quando:
1. o nome do autor, sem o sufixo "(EX-PARLAMENTAR ...)", é igual (normalizado) ao de
   exatamente **um** parlamentar federal da legislatura 57, de qualquer UF (901 nomes da
   Câmara e do Senado);
2. esse parlamentar é de SP;
3. o ano da emenda cai no mandato: o orçamento do ano Y é votado em Y-1;
4. todas as emendas ligadas a ele têm o mesmo "Código do Autor".

Nos demais casos, o autor aparece exatamente como está na fonte, sem link.

Resultado em 06/10/2026:
- 2.505 das 3.375 linhas ligadas, a 78 parlamentares de SP;
- nenhum código de autor ambíguo;
- as emendas de 2023 (orçamento votado em 2022) ficam sem link.

Antes da regra acima, o cruzamento era só pelo nome:
- 77 dos 93 parlamentares de SP têm emendas de 2024 em diante no arquivo.
- Em exercício sem par: Paulo Teixeira, Marina Silva, Sônia Guajajara, Milton Vieira e
  Paulo Soares. Não há, no arquivo, autor com esses nomes.
- Emendas de ex-deputados (legislatura anterior: o "Ano da Emenda" 2023 é o orçamento
  votado em 2022), de bancadas, de comissões e de parlamentares de outros estados ficam
  sem `politico_id`, com o nome do autor como está no arquivo.

**Transferências especiais:** tipo "Emenda Individual - Transferências Especiais".

**Valores:** em formato brasileiro (`6353916,00`). Totais por ano e tipo: empenhado →
liquidado → pago.

**API.** O coletor `emendas-api` funciona nos dois modos de chave: com a variável
`RASTRO_TRANSPARENCIA_CHAVE` ou com o cabeçalho injetado pelo proxy do ambiente. Faz uma
consulta de teste antes e falha com a mensagem da API em caso de 401. Em 06/10/2026, com a
credencial do ambiente, a API respondeu `"Chave de API inválida!"` em todos os endpoints
testados; antes da credencial, a resposta era `"Chave de API não informada!"`.

### Cota parlamentar

O arquivo anual tem 32 colunas e 209.080 linhas em 2025, das quais 25.844 de SP.

**Dados pessoais retirados, também do arquivo bruto:**
- colunas `cpf`, `nuCarteiraParlamentar` e `txtPassageiro`;
- em linhas de fornecedor **pessoa física** (11 dígitos em `txtCNPJCPF`), o CPF e o nome
  do fornecedor: 191 linhas em SP, 2025;
- CPF dentro do nome do fornecedor, como na razão social de MEI ("NOME 12345678901"):
  trocado por "[CPF removido]" em 75 linhas. O CNPJ (14 dígitos) é mantido. Sequências de
  11 dígitos em `txtNumero` (número do documento fiscal) não são CPF e ficam.

**Carga.**
- O arquivo não tem chave única por linha: há linhas idênticas, como débitos mensais de
  telefonia com `ideDocumento` 0.
- Cada carga substitui o ano inteiro, e `linha` guarda a posição no arquivo original.
- O valor mostrado é `vlrLiquido`.
- A API `/deputados/{id}/despesas` continua devolvendo lista vazia (testado de 2023 a
  2026).

## LGPD: o que não é guardado

O arquivo de respostas brutas tem **modo de redação** (ver Metodologia): o original não é
guardado. Grava-se a versão sem os campos pessoais, com o SHA-256 do original, o SHA-256
da versão gravada e a lista de campos removidos. A conferência é baixar de novo a URL
pública e comparar com `sha256_original`.

| Fonte | O que é removido |
|---|---|
| TSE, candidatos | as 17 colunas da tabela acima; só as linhas de SP |
| Câmara, cota | `cpf`, `nuCarteiraParlamentar`, `txtPassageiro`; CPF e nome de fornecedor pessoa física |
| Câmara, listas de deputados | `email` (e-mail de gabinete) |
| Senado, lista de senadores | `EmailParlamentar` |
| Câmara `/deputados/{id}` e Senado `/senador/{cod}` | não são consultados (CPF, data de nascimento, endereço) |

Testes varrem todas as tabelas e todos os payloads procurando e-mails, nomes de campos
pessoais e marcadores de teste colocados nas colunas pessoais. As fixtures do TSE e da
cota estão no repositório **já sem** os dados pessoais.

## API

- `GET /api/politicos?uf=&cargo=&municipio=&nome=&em_exercicio=`: ordem alfabética.
- `GET /api/politicos/{id}`: mandato e contagens por ano (proposições, votos por tipo,
  presenças, cota), cada uma com as respostas oficiais de onde saiu.
- `GET /api/politicos/{id}/proposicoes|votacoes|presencas|cota|emendas?ano=`.
- `GET /api/municipios/{codigo}/representantes`: seções "Eleitos em {município}",
  "Governador e deputados estaduais eleitos por SP — representam todo o estado" e
  "Senadores e deputados federais eleitos por SP — representam todo o estado".
- `GET /api/municipios/{codigo}/emendas`: emendas com destino ao município e
  "Parlamentares que destinaram emendas a este município".

## Verificação contra a fonte (06/10/2026)

Sorteios conferidos por um script independente do código do portal, sem divergência:

| Item | Resultado |
|---|---|
| Câmara e Senado (PR anterior) | 6 parlamentares, todos os números iguais |
| TSE 2024 | Monteiro Lobato, Taquarituba e Ribeirão Preto: prefeito e vereadores iguais (9, 11 e 22) |
| Emendas | Caraguatatuba, Rincão e Itapetininga: quantidade e empenhado/liquidado/pago iguais |
| Cota 2025 | Vitor Lippi (862 lançamentos, R$ 508.869,60), Paulinho da Força (262, R$ 424.028,55) e Alexandre Padilha (1, R$ 0,03): iguais |
| Hashes | `sha256_original` das respostas redigidas = `sha256sum` de downloads novos (TSE 2022 e 2024, emendas, lista do Senado) |

## Próximas etapas

1. Decidir e carregar os eleitos de 2026 (mandatos a partir de 2027).
2. Validar a chave da API do Portal (hoje recusada).
3. Usar o arquivo de favorecidos do Portal para ligar transferências especiais ao
   município que recebeu.
4. Assembleia Legislativa de SP (ALESP).
5. Câmaras municipais (SAPL).
6. LexML (normas e proposições).
7. Análise de matérias estranhas ao objeto das proposições.
8. Cruzamento com doadores de campanha (TSE, prestação de contas).
