# Módulo de políticos (v1 — estado de SP)

Quem ocupa cada cargo e os fatos registrados nas fontes oficiais sobre sua atuação.

**Princípios.** Somente fatos verificáveis de fontes oficiais, cada um com link para a
fonte, período e data da coleta. Nenhuma nota, ranking, adjetivo ou juízo sobre
políticos. Ordenação neutra: alfabética nas listas de pessoas e cronológica nas listas de
atos. Toda página de político tem o link **"Contestar um dado"**, que abre uma issue
pública no repositório já com o endereço da página.

## Situação

| Item | Situação |
|---|---|
| Deputados federais por SP (Câmara): mandato, proposições, votos nominais, presenças | **feito** |
| Senadores por SP (Senado): mandato, matérias, votações, comissões | **feito** |
| Emendas parlamentares (Portal da Transparência) | implementado, **desligado** (sem chave) |
| Cota parlamentar (CEAP) da Câmara | **pendente**: a API devolve lista vazia (ver Limitações) |
| Eleitos 2024 (prefeitos e vereadores) e 2022 (governador, deputados estaduais) — TSE | **pendente**: host do TSE bloqueado no ambiente |
| Eleitos 2026 | **pendente**: carregar quando o TSE publicar os eleitos |

## Como coletar

```bash
uv run alembic upgrade head
uv run rastro coletar ibge-municipios                 # pré-requisito (nomes dos municípios)
uv run rastro politicos --uf SP --anos 2023-2026      # câmara, senado e emendas
uv run rastro politicos --uf SP --anos 2026 --fontes senado
RASTRO_TRANSPARENCIA_CHAVE=... uv run rastro politicos --uf SP --anos 2025 --fontes emendas
```

Cada fonte vira uma execução na tabela `coleta` (`pol-camara`, `pol-senado`,
`pol-emendas`). Toda resposta recebida fica no arquivo de respostas brutas
(`resposta_bruta`/`payload_bruto`), e cada linha das tabelas `pol_*` guarda o
`resposta_id` de onde saiu. Uma falha em um deputado ou ano não interrompe os demais: a
coleta fica `parcial`, com os erros registrados. O limite global é de 1 requisição por
segundo.

**Medido em 06/10/2026, SP, ano de 2025:**
- Câmara: 2 min 53 s. Foram 90 deputados, 8.884 proposições, 24.565 votos e 14.936
  presenças, em 144 respostas (83 MB brutos, cerca de 7 MB comprimidos no arquivo).
- Senado: 17 s para 2025 e 2026.

## Fontes

| Dado | Fonte oficial | Tabela |
|---|---|---|
| Deputados da legislatura 57 | `GET dadosabertos.camara.leg.br/api/v2/deputados?siglaUf=SP&idLegislatura=57` | `pol_politico` |
| Em exercício e partido atual | `GET .../api/v2/deputados?siglaUf=SP` | `pol_politico` |
| Proposições | `GET .../api/v2/proposicoes?idDeputadoAutor={id}&ano={ano}` | `pol_proposicao` |
| Votos nominais | arquivos `dadosabertos.camara.leg.br/arquivos/votacoesVotos/csv/votacoesVotos-{ano}.csv` e `votacoes-{ano}.csv` | `pol_votacao` |
| Presenças | arquivo `.../arquivos/eventosPresencaDeputados/csv/eventosPresencaDeputados-{ano}.csv` | `pol_presenca` |
| Senadores em exercício | `GET legis.senado.leg.br/dadosabertos/senador/lista/atual.json` | `pol_politico` |
| Matérias | `GET .../dadosabertos/processo?codigoParlamentarAutor={cod}&ano={ano}` | `pol_proposicao` |
| Votações | `GET .../dadosabertos/votacao?codigoParlamentar={cod}&dataInicio=&dataFim=` | `pol_votacao` |
| Comissões | `GET .../dadosabertos/senador/{cod}/comissoes.json` | `pol_comissao` |
| Emendas | `GET api.portaldatransparencia.gov.br/api-de-dados/emendas?nomeAutor=&ano=&pagina=` (cabeçalho `chave-api-dados`) | `pol_emenda` |

Os endpoints e campos foram conferidos na documentação e em respostas reais em
06/10/2026:
- Câmara: [Swagger](https://dadosabertos.camara.leg.br/swagger/api.html).
- Senado: [documentação](https://legis.senado.leg.br/dadosabertos/docs/). Os endpoints
  antigos `/senador/{cod}/autorias` e `/senador/{cod}/votacoes` vêm marcados pela própria
  fonte como descontinuados; usamos os substitutos indicados por ela (`/processo` e
  `/votacao`).
- Portal da Transparência: [OpenAPI v3](https://api.portaldatransparencia.gov.br/v3/api-docs).

## API

- `GET /api/politicos?uf=&cargo=&municipio=&nome=&em_exercicio=`: ordem alfabética.
  Com `municipio`, traz os cargos do município e os do estado.
- `GET /api/politicos/{id}`: dados do mandato, contagens por ano (proposições, votos por
  tipo, presenças), cada uma com as respostas oficiais de onde saiu (URL, data da coleta,
  `resposta_id`), mais as comissões e a descrição dos códigos de voto quando a fonte a dá.
- `GET /api/politicos/{id}/proposicoes|votacoes|presencas?ano=`: listas.
- `GET /api/politicos/{id}/emendas?ano=`: emendas, com totais por ano empenhado → liquidado
  → pago, separando as transferências especiais.
- `GET /api/municipios/{codigo}/representantes`: prefeito, vereadores, governador,
  senadores, deputados federais e estaduais. Cargos sem dados vêm com o motivo em
  `pendente`.
- `GET /api/municipios/{codigo}/emendas`: emendas com destino ao município.

## LGPD: o que não é guardado

O arquivo de respostas brutas guarda **tudo** o que chega de cada chamada. Por isso, a
regra deste módulo é **não chamar** endpoints que devolvem dados pessoais:

| Fonte | Não consultado | Motivo |
|---|---|---|
| Câmara `/deputados/{id}` | sim | traz `cpf`, `dataNascimento`, `municipioNascimento`, `nomeCivil`, `escolaridade`, `sexo` |
| Senado `/senador/{cod}` | sim | traz `DataNascimento`, `Naturalidade`, `EnderecoParlamentar` |

Um teste garante que os coletores não chamam esses endpoints. Outro garante que nenhuma
tabela `pol_*` tem coluna de CPF, nascimento, endereço, e-mail ou título de eleitor.

Campos que vêm nas respostas consultadas e **não são gravados nas tabelas**:

| Fonte | Campos não gravados |
|---|---|
| Câmara, lista de deputados | `email`, `urlFoto` |
| Câmara, `votacoesVotos` | `deputado_urlFoto`, `deputado_uriPartido` |
| Senado, lista de senadores | `NomeCompletoParlamentar`, `SexoParlamentar`, `Telefones`, `EmailParlamentar`, `UrlFotoParlamentar` |
| Senado, votações | `sexoParlamentar` |

São dados institucionais publicados pelas próprias casas (telefone e e-mail de gabinete,
nome completo). Eles continuam no arquivo bruto, como chegaram, porque o arquivo prova o
que a fonte entregou.

**TSE (pendente).** Os arquivos de candidatos (`consulta_cand_AAAA`) trazem CPF, data de
nascimento, título de eleitor e e-mail. Para manter o arquivo bruto sem esses dados, o
core precisa de uma opção para gravar só um recorte do arquivo (ou não arquivá-lo) e
guardar o SHA-256 do original. **Decisão necessária antes de ligar a carga do TSE.** As
colunas a manter seriam: ano, turno, UF, unidade eleitoral, cargo, número sequencial do
candidato, número, nome de urna, partido e situação de totalização. Isso ainda precisa
ser conferido no arquivo real.

## Limitações conhecidas (verificadas em 06/10/2026)

- **Cota parlamentar:** `GET /api/v2/deputados/{id}/despesas` devolve `"dados": []` para
  qualquer ano de 2023 a 2026 e para mais de um deputado. O arquivo anual da cota
  (`www.camara.leg.br/cotas/Ano-AAAA.csv.zip`) está em um host bloqueado no ambiente de
  coleta.
- **TSE:** `dadosabertos.tse.jus.br` e `cdn.tse.jus.br` estão bloqueados no ambiente de
  coleta. Por isso, prefeitos, vereadores, governador e deputados estaduais aparecem como
  pendentes na tela "Quem representa você".
- **Partido:** a lista da legislatura repete o deputado uma vez por partido pelo qual
  passou, sem data. Para quem está em exercício, vale o partido da lista atual. Para os
  demais, mostram-se todos os partidos registrados (ex.: `SOLIDARIEDADE / S.PART. / PSB`,
  em que `S.PART.` é como a fonte escreve "sem partido").
- **Presenças:** o arquivo lista as presenças registradas em eventos (sessões, reuniões),
  não o total de eventos de que o deputado deveria participar. O portal mostra a
  quantidade registrada, não um percentual.
- **Proposições:** são as que a Câmara/Senado devolvem para o deputado/senador como
  autor. O Senado inclui as de coautoria e publica a lista completa de autores (campo
  `autoria`).
- **Votos:** gravados exatamente como na fonte. A Câmara tem votos com valor vazio
  (49 em 2025 para os deputados de SP) e `Artigo 17`. O Senado usa códigos, com descrição
  quando a fonte a fornece (`AP` = "Atividade parlamentar", `NCom` = "Não Compareceu",
  `P-NRV` = "Presente – Não registrou voto"). Em votação secreta o voto aparece como
  `Votou`.
- **Senadores:** só os que estão em exercício (lista `atual`), inclusive suplentes no
  exercício do mandato (ex.: Giordano, "1º Suplente").
- **Emendas, não validadas com resposta real** (não havia chave): o formato dos valores
  em texto, o de `localidadeDoGasto` (usado para ligar ao código IBGE só quando há
  correspondência exata "MUNICÍPIO - UF"), os valores de `tipoEmenda` (transferência
  especial = tipo que contém "especial") e a forma do nome aceita em `nomeAutor`. Tudo
  isso precisa ser conferido na primeira coleta com chave, antes de exibir os valores.
  A API não tem filtro por município de destino. "Emendas recebidas" por um município
  inclui só as dos parlamentares coletados.

## Verificação contra a fonte (06/10/2026)

Seis políticos, sorteados em dois sorteios de três. Cada número da tela foi comparado
com uma consulta nova à fonte oficial, feita por um script independente do código do
portal. Nenhuma divergência:

| Político | Conferido | Resultado |
|---|---|---|
| Adilson Barroso (dep. fed.) | partido; 94 proposições; 339 votos por tipo; 151 presenças (2025) | igual |
| Daniel José (dep. fed., fora de exercício) | 0 / 0 / 0 em 2025 | igual |
| Baleia Rossi (dep. fed.) | partido; 19 proposições; 272 votos por tipo; 133 presenças (2025) | igual |
| Coronel Telhada (dep. fed., fora de exercício) | 0 / 0 / 0 em 2025 | igual |
| Astronauta Marcos Pontes (senador) | 158 e 98 matérias; 128 e 59 votações por tipo (2025 e 2026); 61 comissões | igual |
| Mara Gabrilli (senadora) | 165 e 63 matérias; 128 e 59 votações por tipo; 90 comissões | igual |

## Próximas etapas (fora do escopo da v1)

1. Eleitos do TSE: 2024 (prefeitos e vereadores dos 645 municípios) e 2022 (governador,
   deputados estaduais), depois de liberar o host e decidir a gravação do recorte no
   arquivo bruto (LGPD). Eleitos de 2026, quando publicados. O modelo já tem
   `cod_ibge`, `eleicao_ano` e os cargos municipais e estaduais.
2. Cota parlamentar da Câmara: pelo arquivo anual, quando o host for liberado, ou pela
   API, se voltar a devolver dados.
3. Emendas: ligar o coletor com chave, validar os formatos, usar o arquivo de download
   do Portal (que traz o código do município) para "emendas recebidas".
4. Assembleia Legislativa de SP (ALESP).
5. Câmaras municipais (SAPL).
6. LexML (normas e proposições).
7. Análise de matérias estranhas ao objeto das proposições.
8. Cruzamento com doadores de campanha (TSE, prestação de contas).
