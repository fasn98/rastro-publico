# Proposta: módulo "Rastro do dinheiro das emendas"

- **Status:** proposta para decisão do Fabio. Sem código e sem publicação. A ADR vem só depois
  da aprovação.
- **Data do levantamento:** 27/10/2026, consultas feitas entre 13h30 e 15h (UTC).
- **Autor:** sessão de políticos (Claude).

O módulo responde a uma pergunta só: **para onde foi o dinheiro de cada emenda**. A cadeia é
emenda → documentos de despesa → favorecido → (quando houver convênio) pagamentos do convenente a
fornecedores → dados cadastrais abertos das empresas.

## 0. Amostra usada

Três emendas de SC de 2024, escolhidas por regra fixa e sem olhar o conteúdo. Para cada tipo,
ficou a de **menor código** que atendia ao critério. Os autores foram excluídos à medida que
saíam, para não concentrar a amostra num parlamentar. Nenhuma é caso sob investigação conhecido.

| # | Código | Tipo | Critério |
|---|---|---|---|
| 1 | 202422100015 | Transferência especial ("emenda Pix") | primeira com favorecido |
| 2 | 202428550005 | Finalidade definida, com convênio | primeira com convênio e favorecido |
| 3 | 202439290008 | Finalidade definida, execução direta | primeira com favorecido "Sociedade Empresária Limitada" |

Fonte: arquivo único de emendas do Portal da Transparência,
[`download-de-dados/emendas-parlamentares/UNICO`](https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO).
Versão lida: `EmendasParlamentares.zip`, Last-Modified 27/10/2026 01:44:53 GMT, 32.530.367
bytes, SHA-256 `cee4e775534c6338ad294e8d4aae7851ee32072e7d7edf5b1f36a5a41738aebc`.

## 1. Emenda → favorecido (Portal da Transparência)

### 1.1 Caminho pela API (exige chave)

Especificação oficial: <https://api.portaldatransparencia.gov.br/v3/api-docs>, lida em
27/10/2026.

| Passo | Endpoint | O que traz |
|---|---|---|
| Emenda | `GET /api-de-dados/emendas?codigoEmenda=…` | valores empenhado, liquidado e pago |
| Emenda → documentos | `GET /api-de-dados/emendas/documentos/{codigo}` | `DocumentoRelacionadoEmendaDTO`: data, fase, `codigoDocumento`, espécie. **Não traz o favorecido** |
| Documento → favorecido | `GET /api-de-dados/despesas/documentos/{codigo}` | `DespesasPorDocumentoDTO`: `codigoFavorecido` (CNPJ), `nomeFavorecido`, valor, UG, ação, plano orçamentário, `autor`, `favorecidoIntermediario` |
| Encadeamento das fases | `GET /despesas/documentos-relacionados?codigoDocumento=…&fase=…` e `GET /despesas/empenhos-impactados` | empenho ↔ liquidação ↔ pagamento |
| Favorecido final | `GET /despesas/favorecidos-finais-por-documento?codigoDocumento=…` | pagamentos em lista: favorecido final de cada item |
| Busca inversa por CNPJ | `GET /despesas/documentos-por-favorecido?codigoPessoa=CNPJ&fase=1\|2\|3&ano=AAAA&pagina=N` | todos os empenhos, liquidações ou pagamentos de um favorecido no ano |

**A chave atual não funcionou neste ambiente.**
- A consulta de teste (`/emendas?ano=2024&pagina=1`) respondeu **401 "Chave de API inválida!"**.
- A mensagem não é "não informada", então havia uma chave no cabeçalho, e ela foi recusada.
- A chave do Replit (`RASTRO_TRANSPARENCIA_CHAVE`) não pôde ser testada daqui.
- **Pendente:** testar no Replit, ou renovar a chave no
  [cadastro](https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email).

**Limite de requisições:** não confirmado em fonte oficial nesta pesquisa (o site do Portal
recusa acesso automatizado deste ambiente).
- Fonte secundária ([guizsantos/portaldatransparencia](https://github.com/guizsantos/portaldatransparencia)),
  citando a página de cadastro:
  - 400 requisições/min das 6h à meia-noite;
  - 700/min da meia-noite às 6h;
  - 180/min nas APIs "restritas";
  - estouro suspende a chave por 8 h.
- **Proposta:** coletor com teto de 60/min, configurável, e pausa ao primeiro 429 ou 401.

### 1.2 Caminho pelos arquivos (sem chave): testado

O Portal publica, sem chave:
- **`EmendasParlamentares_PorFavorecido.csv`** (no zip de emendas): emenda → favorecido, com
  CNPJ, natureza jurídica e valor recebido por mês. As pessoas físicas vêm com o CPF mascarado
  (`***.999.999-**`).
- **`EmendasParlamentares_Convenios.csv`**: emenda → número do convênio, convenente, objeto e
  valor.
- **Arquivos diários de despesas**
  ([`download-de-dados/despesas/AAAAMMDD`](https://portaldatransparencia.gov.br/download-de-dados/despesas/20250115)):
  - empenho, liquidação e pagamento, com `Código Favorecido`;
  - `Pagamento_EmpenhosImpactados` (pagamento → empenho);
  - `Pagamento_FavorecidosFinais`;
  - no empenho, `Autor Emenda` no formato "NOME / EMENDA N" e `Código Convênio`.

**Resultado nas 3 emendas:**

1. **202422100015 (Pix).** O arquivo por favorecido traz um único favorecido: CNPJ
   01.608.820/0001-23 (Município de Painel), R$ 500.000,00, em 07/2024. O rastro federal termina
   aí; ver 2.2.
2. **202428550005 (convênio).** O favorecido é o CNPJ 85.223.022/0001-73 (cooperativa), R$
   750.000,00, em 04/2025. O arquivo de convênios liga a emenda ao **convênio 958835**, publicado
   em 16/01/2025; ver 2.1.
3. **202439290008 (execução direta pelo Hospital Universitário da UFSC).** São 6 linhas no
   arquivo por favorecido, para 3 empresas. Nos arquivos diários de 11/2024 a 01/2025 (92
   arquivos, 585 MB), a cadeia fecha com valores exatos:

   | Pagamento (OB) | Data | UG | Favorecido (CNPJ) | Valor | Empenho |
   |---|---|---|---|---:|---|
   | 155913264432024OB006267 | 05/12/2024 | 155913 (HU-UFSC) | 02.988.857/0001-97 | 209.672,05 | 155913264432024NE002897 |
   | 155913264432024OB006268 | 05/12/2024 | 155913 (HU-UFSC) | 05.897.011/0001-30 | 21.936,95 | 155913264432024NE002896 |

   - Os dois pagamentos têm o plano orçamentário "Reestruturação e modernização dos Hospitais
     Universitários Federais", a mesma ação da emenda.
   - Os valores são iguais aos do arquivo por favorecido para 12/2024.
   - O empenho (com o campo `Autor Emenda`) foi emitido antes de 11/2024 e não estava nos
     arquivos varridos. Pela API, `emendas/documentos/{codigo}` fecha esse elo sem varredura.

**Busca inversa por CNPJ, sem chave:** dá para fazer, varrendo os arquivos diários. Mas as mesmas
empresas recebem de outras UGs sem emenda. Na varredura, foram 252 pagamentos e 140 empenhos para
os 3 CNPJs, e só os de UG e plano orçamentário compatíveis pertencem à emenda. Por isso o vínculo
emenda ↔ documento deve vir do documento, nunca só do CNPJ.

## 2. Favorecido → subcontratados

### 2.1 Convênios e termos de fomento (Transferegov): testado

- **API do Transferegov:** `api.transferegov.gestao.gov.br` respondeu **403 com página HTML** do
  próprio servidor. Não foi o proxy. Não testado daqui.
- **Arquivos (sem chave):** repositório
  [`repositorio.dados.gov.br/seges/detru/`](https://repositorio.dados.gov.br/seges/detru/).
  - `siconv_pagamento.csv.zip` (344 MB): `NR_CONVENIO`, `IDENTIF_FORNECEDOR` (CNPJ),
    `NOME_FORNECEDOR`, `TP_MOV_FINANCEIRA`, `DATA_PAG`, `NR_DL` e `DESC_DL` (documento de
    liquidação), `VL_PAGO`.
  - Também: `siconv_convenio`, `siconv_emenda` (proposta → número da emenda e parlamentar),
    `siconv_licitacao`, `siconv_contrato` (fornecedor contratado), `siconv_obtv_convenente`.
  - **Data da carga: 17/07/2026** (`data_carga_siconv.txt`). Em 27/10/2026, o arquivo estava há
    mais de 3 meses sem atualização. É um risco, e a tela deve mostrar essa data.
- **Teste 1, convênio 958835 (amostra #2):**
  - assinado em 26/12/2024, em execução, com OBTV, R$ 750.000,00 desembolsados;
  - `siconv_emenda` confirma a emenda 28550005 e o beneficiário pelo CNPJ;
  - até a carga de 17/07/2026, havia 25 pagamentos do convenente, todos de R$ 1.000,00, descritos
    como "DIÁRIAS", a pessoas físicas (identificação mascarada, omitida aqui);
  - não há licitação nem contrato registrados.
- **Teste 2, para mostrar fornecedores PJ** (regra: menor número de convênio de emenda de SC 2024
  com pagamento a CNPJ): **convênio 955727**, emenda 29250005, R$ 144.579,48.
  - Foram 64 pagamentos com OBTV a 10 CNPJs, entre 2025 e 2026.
  - Vários são **MEI**, cuja razão social é o nome da pessoa: ver 4.
- **Volume nacional (carga de 17/07/2026):**
  - 285.743 convênios, 141.121 ligados a emendas;
  - 7.359.136 pagamentos, 1.116.228 em convênios de emenda;
  - **90.652 CNPJs de fornecedores distintos** nos convênios de emenda;
  - 294.962 pagamentos a não-PJ.

### 2.2 Transferências especiais ("emendas Pix")

- Na esfera federal, o rastro financeiro termina no ente beneficiário: na amostra #1, o Município
  de Painel. O pagamento do município a fornecedores não está em sistema federal. Ele fica no
  portal de transparência do município e no TCE.
- O que existe de dado federal sobre o uso é o **plano de ação** e o **relatório de gestão**,
  cadastrados pelo ente no Transferegov:
  - módulo `transferenciasespeciais` da API, construída em PostgREST, com 14 tabelas segundo o
    pacote [`transferegovr`](https://cran.r-project.org/web/packages/transferegovr/index.html);
  - o plano de ação traz finalidade, metas e executor;
  - o relatório de gestão é obrigatório e declaratório
    ([apresentação do TCU, 2025](https://dialogopublico.tcu.gov.br/wp-content/uploads/sites/20/2025/10/1TCU-Waldemir-Transferencias-especiais-Dialogo-Publico-GO-2025.pdf)).
  - **Não testado:** a API respondeu 403 daqui, e não há arquivo de transferências especiais no
    repositório `detru`. Pendente: testar a partir do Replit (servidor no Brasil).
- **Proposta para a tela:** mostrar o que foi declarado no plano e no relatório, marcado como
  "declarado pelo ente". Para o gasto final, apontar o portal do município, sem completar nada.

## 3. Empresas: CNPJ da Receita e PNCP

### 3.1 Cadastro aberto de CNPJ (Receita Federal): testado

- **Onde está:** compartilhamento público oficial em
  [`arquivos.receitafederal.gov.br`](https://arquivos.receitafederal.gov.br/), pasta
  `Dados/Cadastros/CNPJ/AAAA-MM/`, listável por WebDAV. O endereço antigo `dadosabertos.rfb.gov.br`
  recusou a conexão.
- **Versão de 2026-10, publicada em 13/10/2026:** 7,8 GB compactados.
  - Empresas: 10 arquivos, 1,4 GB;
  - Estabelecimentos: 10 arquivos, 5,4 GB;
  - Sócios: 10 arquivos, 0,69 GB;
  - Simples: 0,3 GB;
  - tabelas de CNAE, municípios, naturezas e qualificações.
- **Atualização:** mensal. Há pastas mensais de 2026-07 a 2026-10.
- **Licença:** não confirmada em fonte oficial nesta pesquisa. Precisa ser conferida no
  [conjunto do dados.gov.br](https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj)
  antes da ADR.
- **Campos úteis:**
  - Empresas: razão social, natureza jurídica, capital social, porte.
  - Estabelecimentos: CNPJ completo, situação cadastral e data, data de início de atividade,
    CNAE principal e secundários, endereço.
  - Sócios: ver 4.
- **Cruzamento:** pelos 8 primeiros dígitos (CNPJ básico) para Empresas e Sócios, e pelo CNPJ
  completo para Estabelecimentos.
- **Recorte proposto:** carregar só os CNPJs que receberam dinheiro de emenda. São 59.593 no
  arquivo por favorecido e 90.652 fornecedores de convênios, sem tabela completa.
- **Inspeção de um arquivo de sócios** (`Socios1.zip`, só a forma dos campos, sem nomes):
  - 2.019.150 linhas, 11 colunas;
  - tipo 2 (pessoa física): 1.973.459;
  - CPF mascarado `***999999**`.

### 3.2 PNCP (contratos): testado

- **API pública, sem chave:** [`pncp.gov.br/api/consulta`](https://pncp.gov.br/api/consulta/v3/api-docs).
  - `/v1/contratos` filtra por data e por órgão (`cnpjOrgao`), **não por fornecedor**. O
    cruzamento por CNPJ do fornecedor (`niFornecedor`) é feito depois da coleta.
  - O contrato traz `niFornecedor`, `tipoPessoa`, `niFornecedorSubContratado`, `valorGlobal`,
    objeto, vigência e **`emendaParlamentar`**.
- **Limite:** respondeu **429 depois de cerca de 10 requisições** em sequência rápida. O coletor
  precisa de pausa e recuo.
- **Teste:**
  - Município de Painel, de 07/2024 a 06/2025: 1.325 contratos.
  - EBSERH (sede, CNPJ 15.126.437/0001-43), de 11 a 12/2024: 868 contratos.
  - EMENDA_PNCP_PAINEL: (preenchido abaixo, se a consulta paginada terminar)

## 4. LGPD

**Campos pessoais nas fontes:**

| Fonte | Campo | Natureza |
|---|---|---|
| Receita, Sócios | nome do sócio PF; CPF mascarado (6 dígitos centrais visíveis); faixa etária; data de entrada na sociedade; nome e CPF mascarado do representante legal | pessoais. O CPF mascarado continua dado pessoal: junto com o nome, identifica |
| Receita, Empresas | razão social de **MEI e empresário individual**, que é o nome da pessoa, às vezes precedido do CNPJ | pessoal |
| Receita, Estabelecimentos | endereço, telefone e e-mail; em MEI, são em geral os da residência da pessoa | pessoais (MEI) |
| Portal, por favorecido | favorecido pessoa física (CPF mascarado `***.999.999-**`) | pessoal |
| Transferegov, `siconv_pagamento` | fornecedor pessoa física (`***99999***`) | pessoal |
| Transferegov, `siconv_obtv_convenente` | **CPF completo, sem máscara**: 34.065 ocorrências nas primeiras 2 milhões de linhas | pessoal; nunca pode ser gravado |

**Proposta de regra, para o parecer:**
1. **Nenhum CPF**, nem mascarado, nem parcial, em tabela, arquivo bruto ou tela. O CPF é
   descartado na leitura, como já se faz em `coletores/redacao.py`.
2. **Pessoa física como favorecida ou fornecedora:** aparece só como "pessoa física", com valor e
   data, sem nome.
3. **MEI e empresário individual:** a razão social não é exibida, porque é o nome da pessoa.
   - Mostrar o CNPJ, a natureza jurídica, o CNAE, o município (sem endereço) e as datas.
   - Pendente para o parecer: se até o CNPJ do MEI deve ser omitido.
4. **Sócios:**
   - só de empresas (não MEI) que receberam dinheiro de emenda;
   - só nome e qualificação ("sócio-administrador");
   - sem CPF, sem faixa etária e sem representante legal;
   - opção mais restritiva para o parecer escolher: mostrar só sócios pessoa jurídica.
5. **Endereço:** só o de empresas (não MEI), e só município e UF na lista. O endereço completo
   fica na ficha da empresa.
6. **Arquivo bruto:** a redação vale antes de arquivar, como no módulo de políticos.
7. **Teste** que falha se aparecer número de 11 dígitos ou nome de pessoa física em arquivo
   gerado.

## 5. Neutralidade: proposta de tela

**Ficha da emenda:**
- código, autor, tipo, função e ação;
- valores empenhado, liquidado e pago, com fonte e data da carga.

**Linha do tempo de documentos:**
- data, fase (empenho, liquidação, pagamento), UG e valor;
- favorecido (CNPJ e razão social; pessoa física e MEI conforme 4);
- código do documento, com link para o Portal e para o bruto (SHA-256).

**Quando houver convênio:**
- número e situação do convênio;
- pagamentos do convenente: data, fornecedor e valor, com a data da carga do Transferegov
  destacada.

**Ficha da empresa:** só fatos com fonte.
- data de abertura, CNAE, situação e natureza jurídica;
- município;
- outras emendas e documentos em que o CNPJ aparece, com os vínculos documentados.

**O que não entra:**
- nenhuma pontuação, risco, cor de alerta ou ordenação por "suspeita";
- nenhum rótulo como "empresa nova", "fachada" ou "laranja";
- nenhuma frase que relacione datas, como "empresa aberta X dias antes". A data de abertura e a
  data do pagamento aparecem lado a lado, sem cálculo.

**Avisos fixos:**
- "Os dados mostram registros oficiais de pagamento. Não indicam irregularidade."
- Nas emendas Pix: "o uso final é declarado pelo ente e não é verificado aqui".

## 6. Volume e tempo de coleta (Brasil)

| Fonte | Volume | Tempo estimado |
|---|---|---|
| Portal: emendas, por favorecido, convênios | 32,5 MB compactados (256 MB em CSV). 94.747 emendas (2014–2026), 828.478 linhas por favorecido, 85.403 linhas de convênio | segundos |
| Portal: arquivos diários de despesas | ~6,4 MB/dia compactados (média medida: 92 dias = 585 MB). De 2019 a 2026, ~18 GB | ~1,5–2 h. A varredura medida fez 92 dias em ~3 min, ≈3 MB/s com leitura |
| Portal: API `emendas/documentos` e `despesas/documentos/{codigo}` | 1 req por página por emenda, mais 1 por documento; centenas de milhares a milhões de requisições | dias, com teto de 60/min. Usar a API só para fechar elos, e os arquivos diários para o volume |
| Transferegov (`detru`) | ~516 MB compactados nos 6 arquivos usados. `siconv_pagamento` tem 1,07 GB em CSV e 7,36 M linhas | minutos. Atualização irregular (carga de 17/07/2026) |
| Receita CNPJ | 7,8 GB compactados por mês | ~1 h de download e filtro em streaming, só para os ~150 mil CNPJs de interesse |
| PNCP | por órgão e por data, com limite 429 | lento: horas a dias. Coletar só órgãos e entes que receberam emendas |

## 7. Decisões para o Fabio

1. Aprovar a cadeia de vínculos:
   - emenda → documento: só por documento oficial (API `emendas/documentos` ou `Autor Emenda` no
     empenho);
   - documento → favorecido;
   - convênio → pagamentos do convenente;
   - CNPJ → cadastro.
2. Chave do Portal: testar no Replit ou renovar.
3. Testar a API do Transferegov (convênios e transferências especiais) a partir do Replit.
4. Levar a regra de LGPD da seção 4 ao parecer, incluindo o CPF completo encontrado em
   `siconv_obtv_convenente`.
5. Confirmar a licença dos dados do CNPJ antes da ADR.

## Limitações desta pesquisa

- Sem chave válida, não testei os endpoints da API do Portal. Para a amostra #3, o elo
  emenda ↔ empenho foi mostrado por valores, UG e plano orçamentário iguais, não pelo documento.
- O site do Portal recusa acesso automatizado deste ambiente, e não houve tentativa de contornar
  isso.
- A API do Transferegov respondeu 403 daqui.
- Os números de volume do Transferegov e da Receita são das versões lidas em 27/10/2026.
