# ADR-0018: Prefeitos eleitos em cada exercício do ranking, como registrados pelo TSE

- **Status:** Proposto
- **Data:** 2026-10-09
- **Autor:** sessão de políticos
- **Decisor:** Fabio (regras aprovadas em 09/10/2026; merge e publicação dependem de nova aprovação)

## Contexto

A nota do Ranking Fiscal é a média dos exercícios 2023 a 2025 (metodologia v1.1). Essa
janela sempre atravessa a troca de mandato de 01/01/2025, e em alguns municípios houve
eleição suplementar no meio do mandato. Sem dizer quem foi eleito para cada exercício, o
leitor pode atribuir a um prefeito resultados de outra gestão.

O que a fonte registra (arquivos `consulta_cand_2020` e `consulta_cand_2024` do TSE,
baixados em 09/10/2026):

- As eleições suplementares estão no arquivo da eleição original: o de 2020 traz 24 de SP
  (de 2021 a abril de 2024), o de 2024 traz 14 (de 2025 a outubro de 2026). Não existem
  arquivos de 2021, 2023 nem 2025.
- O TSE registra quem foi **eleito**, não quem exerceu o cargo. Em São Paulo, o arquivo
  traz Bruno Covas (PSDB) para 2021–2024; o vice eleito, Ricardo Nunes (MDB), assumiu
  em maio de 2021, após a morte do titular ([Câmara Municipal de São Paulo, 01/01/2025](https://www.saopaulo.sp.leg.br/blog/camara-de-sp-empossa-o-prefeito-ricardo-nunes/)).
  Renúncia, morte, afastamento e interinidade não aparecem.
- Na cassação ou no indeferimento, o TSE **reescreve** o resultado original: o vencedor
  passa a "INAPTO / NÃO ELEITO" e a eleição ordinária fica sem eleito. Não há datas de
  posse nem de afastamento (o conjunto "motivo de cassação" também não tem datas).
- O vice-prefeito eleito tem o mesmo número de candidatura do titular, na mesma eleição e
  turno: o par é único em todas as eleições com eleito de SP (645 em 2020, 641 em 2024).
- O nome de urna da mesma pessoa pode mudar entre eleições ("DARIO SAADI" em 2020,
  "DÁRIO SAADI" em 2024) e o CPF não é guardado (LGPD).

## Opções consideradas

- Mostrar "quem governou": descartada; nenhuma fonte oficial estruturada registra quem
  exerceu o cargo.
- Atribuir os anos anteriores à suplementar ao eleito original cassado: descartada; o
  arquivo atual do TSE não o registra como eleito.
- Juntar a mesma pessoa entre mandatos pelo nome: descartada; o nome muda e o CPF não pode
  ser guardado.

## Decisão

1. **Fonte:** prefeito (cargo 11) e vice-prefeito (cargo 12) de `consulta_cand_2020` (mandato
   2021–2024) e `consulta_cand_2024` (mandato 2025–2028), ordinária e suplementares, com o
   cruzamento oficial TSE↔IBGE validado em 100% por UF e a mesma redação LGPD da coleta de
   eleitos. Partido = o da eleição, como registrado no TSE.
2. **Regra por mandato:** vale a eleição mais recente com eleito. Se for a ordinária, ela
   vale para o mandato inteiro. Se for uma suplementar na data D, os exercícios anteriores
   ao ano de D ficam "sem eleito válido no arquivo atual do TSE"; o ano de D e os seguintes
   recebem "sem eleito válido no arquivo atual do TSE; a eleição suplementar de D elegeu
   NOME (PARTIDO)". O eleito original cassado não é nomeado e o motivo não é citado.
   Mandato sem eleito em nenhuma eleição: "sem eleito válido no arquivo atual do TSE".
3. **Vice:** aparece ao lado do titular ("NOME (PARTIDO), vice NOME (PARTIDO)"). Nada é
   inferido sobre quem exerceu o cargo.
4. **Onde aparece:** só na página do município, com o rótulo "eleito(a) para o mandato":
   linha do tempo por mandato e, nos indicadores, o texto do exercício selecionado. A mesma
   pessoa não é ligada entre mandatos.
5. **Ranking sem nomes (opção C, decidida em 09/10/2026):** a tabela, o `ranking.json` e o
   `ranking.csv` não trazem prefeitos, com qualquer trava; cada município ganha só um link
   discreto "ver gestões" para a seção da página do município. Na mesma linha da nota, o
   nome da pessoa pareceria uma nota para ela. `verificar()` recusa ranking com prefeitos.
6. **Partido só como texto ao lado do nome:** sem média, ranking, filtro, agrupamento ou
   cor por partido, e nenhum texto que compare partidos.
7. **Publicação:** trava `pol_publicar_gestoes`, desligada por padrão. Só é ligada depois
   do 2º turno de 25/10/2026, com nova aprovação do Fabio.

## Consequências

- Mais fácil: o leitor vê que a nota pode cobrir mais de uma gestão e de qual eleição veio
  cada nome, com link para o arquivo do TSE.
- Mais difícil: quando o eleito não exerceu o cargo (morte, afastamento), o site mostra o
  eleito; a Metodologia explica o limite, com o exemplo de São Paulo.
- Mudança de formato: campo `prefeitos` em `municipios/{cod}.json`, só com a trava ligada.
  Desligada, a exportação sai idêntica à anterior; o ranking não muda em nenhum caso.
