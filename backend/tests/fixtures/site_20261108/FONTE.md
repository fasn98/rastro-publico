# Site publicado em 08/11/2026 (recorte)

Arquivos do site em vigor de 08/11 a 21/11/2026: branch `gh-pages` do repositório
`fasn98/rastro-publico`, commit `723d73ed`, tag `site-20261108-140446`. São arquivos
públicos do site (nomes de urna, partido e situação de eleitos, sem dado pessoal).

| Arquivo | Origem | SHA-256 |
|---|---|---|
| `eleitos/m-3512308.json` (Conchas/SP) | `dados/eleitos/m-3512308.json`, sem alteração | `c854aef3c082871bd9c1e8e840fbf210f2eadc0645d4e4ed50c63d85c294afe2` |
| `eleitos/m-3518404.json` (Guaratinguetá/SP) | `dados/eleitos/m-3518404.json`, sem alteração | `dfa5ff97d8a49b3579ad81c3e9c6059bea6ccc22b8dbc4bfc7a449696f2ef0c3` |
| `eleitos/m-3525300.json` (Jaú/SP) | `dados/eleitos/m-3525300.json`, sem alteração | `3196270254c238808570ce4662ee91e3a431255ac03b2a8d44c1473baf697422` |
| `politicos/15991.json` (Sônia Guajajara, deputada federal/SP, Câmara 220643) | `dados/politicos/15991.json`, sem alteração | `c3c83030881b49cda0906230ffc6a8073dd3e037f1017ac08d3f71550c027b6e` |
| `politicos/15991/cota/2026.json` | `dados/politicos/15991/cota/2026.json`, sem alteração (subpasta da página: não é político) | `c62ded8bdb658aac635a86d35f2098baf42633ecf3e5ca9de1e1f32def0ebe38` |
| `municipios.json` | as 3 entradas destes municípios em `dados/municipios.json` (SHA-256 do arquivo inteiro: `6066f22a9ce229f0b7c7007a131a00c6ca49b14b6d4cf328286091d428c37c21`) | — |

## Arquivo do TSE de 21/11/2026 (recorte)

`tse_consulta_cand_2024_SP_recorte.csv`: as 530 linhas de Conchas (SG_UE 63479), Jaú
(66079) e Guaratinguetá (64696), cargos PREFEITO e VEREADOR, do `consulta_cand_2024_SP.csv`
de https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip
(Last-Modified Sat, 21 Nov 2026 05:27:55 GMT; ETag "4af7e47-660c29f72edd6"; 78.609.991
bytes; SHA-256 do zip `37231ceb2d23715908be1ce878859d3f94799ba19e480b4caf09e78c56bf44b3`).
Só colunas públicas, nenhuma de `tse.COLUNAS_PESSOAIS`: SG_UF, SG_UE, NM_UE, CD_ELEICAO,
DS_ELEICAO, DT_ELEICAO, CD_TIPO_ELEICAO, NR_TURNO, DS_CARGO, SQ_CANDIDATO,
NM_URNA_CANDIDATO, SG_PARTIDO, DS_SIT_TOT_TURNO, DS_SITUACAO_CANDIDATURA, DT_GERACAO. Os
valores são os do arquivo, sem alteração; o texto foi gravado em UTF-8 (o original é
latin-1). SHA-256 do recorte:
`6030fd6e5313ca955c33cc7cb9b296d935a751330bba71d770b4d46ba4838fb6`.

Os testes montam a versão nova aplicando a esse recorte a regra de sempre
(`tse.selecionar_eleitos`). O que o arquivo diz desses municípios:

- Conchas: "Eleição Suplementar de Conchas" marcada para 06/12/2026, sem resultado; o
  prefeito Paulo Nunes (PDT, SQ_CANDIDATO 250002180907) deixa de constar como eleito pela
  regra de `tse.selecionar_eleitos`.
- Jaú: Dani Rodrigueiro (PDT, 250002243197) e Marcos Brasil Despachante (UNIÃO,
  250001959675) passaram a "SUPLENTE"; Willian Oliveira (AVANTE, 250001903239) e Guto
  Machado (PT, 250002243398) passaram a "ELEITO POR MÉDIA".
- Guaratinguetá: Pedro Sannini (PL, 250001948460) passou a "NÃO ELEITO"; Marcos
  Evangelista (PL, 250001948465) passou a "ELEITO POR MÉDIA".
