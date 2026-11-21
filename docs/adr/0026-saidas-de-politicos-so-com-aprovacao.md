# ADR-0026: Saídas de políticos do site só com aprovação

- **Status:** Aceito
- **Data:** 2026-11-21
- **Decidido em:** 2026-11-21 (Fabio: "Proposta aprovada, com uma mudança: a verificação compara pelo id_fonte sempre, não só quando a contagem cai")
- **Autor:** sessão principal
- **Decisor:** Fabio

## Contexto

Antes de publicar, `site.verificar` comparava só a **contagem** de políticos com a do site
publicado. Se a contagem caísse, a publicação era cancelada.

De 08/11 a 21/11/2026, toda publicação foi cancelada com "politicos: 11375 na nova versão,
11376 na publicada". A causa estava no arquivo de candidatos de 2024 do TSE
(`consulta_cand_2024.zip`, versão de 21/11/2026), lido pela regra de sempre
(`tse.selecionar_eleitos`):

- **Conchas/SP:** o arquivo passou a trazer a "Eleição Suplementar de Conchas", marcada
  para 06/12/2026 e ainda sem resultado. Por isso o prefeito Paulo Nunes deixa de constar
  como eleito, e a página do município mostra a pendência.
- **Jaú/SP:** Dani Rodrigueiro e Marcos Brasil Despachante passaram a "SUPLENTE"; Willian
  Oliveira e Guto Machado passaram a "ELEITO POR MÉDIA".
- **Guaratinguetá/SP:** Pedro Sannini passou a "NÃO ELEITO"; Marcos Evangelista passou a
  "ELEITO POR MÉDIA".

Só Conchas mudava a contagem. As trocas de Jaú e Guaratinguetá passavam pela trava sem
nenhum aviso.

## Decisão

1. **Comparação um a um.** A verificação compara os políticos do site publicado com os da
   nova versão pelo par (fonte, `id_fonte`), sempre. Os políticos vêm das páginas
   (`politicos/{id}.json`) e dos arquivos de eleitos (`eleitos/*.json`). Nos arquivos de
   08/11, esses dois conjuntos somam exatamente os 11.376 do manifesto.
2. **Lista de remoções aprovadas.** Toda saída, mesmo com a contagem igual ou maior, só
   passa se estiver em `backend/src/rastro/remocoes_aprovadas.toml`. Cada entrada tem:
   - fonte e `id_fonte`;
   - nome, cargo e município;
   - o que o arquivo da fonte diz;
   - a versão do arquivo;
   - a data e "aprovado por Fabio".

   Qualquer saída fora da lista barra a publicação. Depois da publicação, a entrada fica
   só como registro, porque a base de comparação passa a ser a nova versão.
3. **Resumo sempre.** A publicação, ou a simulação, imprime quem entrou e quem saiu, com o
   município, mesmo quando passa.
4. **Entradas iniciais (21/11/2026):** Paulo Nunes (Conchas), Dani Rodrigueiro e Marcos
   Brasil Despachante (Jaú) e Pedro Sannini (Guaratinguetá).

**O que fica como era:**
- A contagem de **municípios** continua conferida.
- A contagem de políticos só vale sem a comparação um a um, isto é, sem site publicado
  com arquivos de políticos.
- As duas dispensas já existentes continuam valendo:
  - travas de publicação diferentes das da versão publicada;
  - fonte de políticos indisponível nesta coleta.

## Consequências

- **Código:**
  - `rastro/remocoes.py`;
  - `remocoes_aprovadas.toml`;
  - `site.verificar(saida, anterior, publicados)`;
  - em `publicacao.publicar`, a leitura dos arquivos de políticos do `gh-pages` por
    `git archive`.
- **Formato:** nenhum arquivo exportado muda.
- **Testes:** `backend/tests/test_remocoes.py`, com o recorte real do site de 08/11
  (`fixtures/site_20261108`) e as mudanças do arquivo do TSE de 21/11.
- **Operação:**
  - Uma saída nova barra a publicação até o Fabio aprovar e a entrada chegar ao `main` por
    PR.
  - Quando a suplementar de Conchas tiver resultado, o eleito entra sem precisar de lista.
