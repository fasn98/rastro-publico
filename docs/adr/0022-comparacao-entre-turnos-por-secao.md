# ADR-0022: Eleições 2026, comparação entre turnos por seção

- **Status:** Aceito
- **Data:** 2026-10-27
- **Autor:** sessão de políticos
- **Decisor:** Fabio (aprovação em 27/10/2026)

## Contexto

Complementa a [ADR-0021](0021-eleicoes-por-secao.md), que trata dos dados por seção a partir dos arquivos oficiais de urna. O módulo de eleições foi para o repositório privado `fasn98/rastro-eleicoes`: carga única por pacote e por UF no GitHub Actions, sem banco. Nada dele é publicado, e o parecer jurídico continua pré-requisito.

O protótipo compara o 1º e o 2º turno:
- **cargos:** presidente; governador só nas UFs com 2º turno;
- **níveis:** Brasil, UF, município, zona e seção.

Para isso, é preciso uma regra para casar as seções dos dois turnos. Regras de cruzamento de dados exigem a aprovação do Fabio antes do código (CLAUDE.md). Ele aprovou a regra abaixo, com três condições, em 27/10/2026.

Três fatos dos arquivos oficiais pesaram na decisão:
- **Seções agregadas.** Uma seção agregada não tem urna própria: os eleitores votam na urna da seção principal, no mesmo local. O arquivo "Eleitorado – 2026", de locais de votação, traz o campo `DS_TIPO_SECAO_AGREGADA` e a seção principal.
- **Aptos que mudam.** O número de aptos no BU muda entre os turnos em parte das seções. Nos dados de teste, foram 87 de 754 em Blumenau e 913 de 5.124 em Salvador, em geral ±1. O boletim não traz o motivo.
- **Aptos por eleição.** No 1º turno, o mesmo BU pode trazer aptos diferentes na eleição federal e na estadual: 24 seções em Blumenau e 237 em Salvador. A imagem do BU separa "Originais da seção" e "Temporários na seção".

## Decisão

**Chave:** (código TSE do município, zona, seção).

**a. Agregadas.**
- Uma seção agregada em algum dos turnos é comparada pela seção principal onde os eleitores votaram, nos dois turnos.
- A principal e as agregadas (de qualquer turno) formam um grupo, e cada turno soma os boletins do grupo.
- A tela mostra quais seções formam o grupo.
- A página "Fontes e método" explica a regra.

**b. Aptos diferentes.**
- Aptos diferentes entre os turnos, ou entre a eleição federal e a estadual no mesmo BU, ficam marcados como "caso a explicar".
- Os números não são ajustados, e não se atribui motivo.

**c. Sem par.**
- Seções (ou grupos) sem boletim em um dos turnos ficam fora da comparação, numa lista própria, com a contagem por UF.
- Os totais de cada turno, conferidos com a totalização oficial, continuam somando todas as seções.

**Linguagem e apresentação** (pedidos do Fabio de 26/10/2026, mantidos):
- Usar "variação entre turnos". Nunca "migração", "transferência", "virada" ou "eleitores de X foram para Y".
- Texto fixo: "Os boletins mostram o total de cada seção em cada turno. O voto é secreto: não é possível saber como cada eleitor mudou de um turno para o outro."
- Nenhum modelo de inferência ecológica.
- Percentual dos candidatos sobre os votos válidos, pelo critério do TSE (padrão), ou sobre o comparecimento, com a base escrita em cada linha.
  - Ficam fora dos válidos: brancos, nulos, nulos técnicos e os votos de destinação "Anulado" ou "Anulado sub judice".

**Fora desta decisão:**
- O cruzamento entre cargos (ex.: seções em que um senador foi o mais votado × voto para presidente) é só proposta, para decisão futura.
- Se for implementado, terá o aviso fixo: "mostra coincidência por seção; não indica que os mesmos eleitores votaram de uma forma ou de outra".

## Consequências

- A comparação fica no nível de grupo de urna. Uma seção agregada nunca aparece com números próprios.
- Os casos a explicar ficam visíveis, sem corrigir nem esconder números. Na seção, cada caso traz o texto e a fonte.
- **Dados de teste** (Blumenau e Salvador, os dois turnos):
  - 754 e 5.124 grupos comparados, 3 e 80 deles com agregadas;
  - 0 seções sem par;
  - as somas de cada turno conferem com a totalização oficial do município (presidente nos dois turnos, governador no 1º, incluindo os votos válidos).
- **Fontes dos números de teste** (TSE, eleição de 2026; 1º turno em 04/10/2026 e 2º turno em 25/10/2026; tudo lido em 26/10/2026, horário de Brasília):
  - 1º turno, boletins por seção: pacotes [SC](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_1t_SC.zip) (Last-Modified 22/10/2026 20:37:50 GMT; SHA-256 `4223ae5b9778e593ee6c7604d0f1f35fc9d9354a2318d67d2dc9ae5d0c980197`) e [BA](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_1t_BA.zip) (Last-Modified 22/10/2026 19:49:40 GMT; o SHA-256 do pacote da BA ainda não foi registrado).
  - 2º turno, boletins por seção: [arquivos de urna](https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/) lidos um a um, com o link e o SHA-256 de cada arquivo na tela de cada seção do protótipo.
  - Totalização oficial do município (presidente, 1º e 2º turno; governador, 1º turno), SHA-256 do arquivo lido:
    - Blumenau: [`sc80470-c0001-e006257-u.json`](https://resultados.tse.jus.br/oficial/ele2026/6257/dados/sc/sc80470-c0001-e006257-u.json) `77f20d320c8e851bea80bb2cc8425136936ce56125c1cf9bcba25187e46c0a28`; [`sc80470-c0001-e006258-u.json`](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/sc/sc80470-c0001-e006258-u.json) `34f0f6704e504e1905700b3dbb639330e240b237c5f398ffb775cbd3a0b8bff2`; [`sc80470-c0003-e006259-u.json`](https://resultados.tse.jus.br/oficial/ele2026/6259/dados/sc/sc80470-c0003-e006259-u.json) `bea8a97f5e99ea4cbbd8bbdbf8f3d08a58f0f032d2576d51fb6d62fef6352658`.
    - Salvador: [`ba38490-c0001-e006257-u.json`](https://resultados.tse.jus.br/oficial/ele2026/6257/dados/ba/ba38490-c0001-e006257-u.json) `e268f25fdefe6b59a44f8a1192a23f307bcfd5fb1404155298c078f285d128fa`; [`ba38490-c0001-e006258-u.json`](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/ba/ba38490-c0001-e006258-u.json) `a2fcf366fd339260c86535fbfc996de4aaf8f505ca332173706e86b4a414b227`; [`ba38490-c0003-e006259-u.json`](https://resultados.tse.jus.br/oficial/ele2026/6259/dados/ba/ba38490-c0003-e006259-u.json) `ecd311560a76e6f35f4ff5c13ff0047a765de9267eb998b8760c5a021f8a3053`.
  - Seções agregadas: [Eleitorado – 2026, locais de votação](https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip) (Last-Modified 25/10/2026 18:32:19 GMT; SHA-256 `771ecfe5086b65c38943df9f694831dc5b94e0addd563517cd139fbd97642981`).
  - Essas versões são geradas pelo `prototipo/fontes.py` (`rastro-eleicoes`, PR #5) e aparecem na página "Fontes e método" do protótipo; pela regra do repositório, nenhum dado é commitado. O módulo não tem arquivo bruto no `/api/bruto` do rastro-publico: nada dele é publicado.
- **Pendente:** quando os pacotes do 2º turno saírem, um teste de rede vai conferir as somas por zona, município, UF e Brasil contra os arquivos oficiais de cada turno, e o % dos válidos por candidato no Brasil contra a totalização oficial.
- **Código:** `prototipo/comparar.py` no `rastro-eleicoes` (PR #5, rascunho) e `docs/comparacao-e-rankings.md`.
