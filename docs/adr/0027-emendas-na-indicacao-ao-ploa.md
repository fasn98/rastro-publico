# ADR-0027: Emendas na fase de indicação ao PLOA (apresentada → aprovada → empenhada → paga)

- **Status:** Proposto
- **Data:** 2026-11-26
- **Autor:** sessão principal
- **Decisor:** Fabio

## Contexto

O Fabio pediu em 26/11/2026 uma proposta só de pesquisa e ADR, sem código, para as emendas na
fase de indicação ao PLOA 2027. Os pedidos foram:

1. achar a fonte oficial das emendas apresentadas e descrevê-la: formato, licença, campos,
   frequência de atualização e dado pessoal;
2. propor como ligar indicação → empenho → pagamento da mesma emenda nas duas fontes, e o
   que fazer quando não houver correspondência;
3. fazer um teste de leitura, só em memória, com as emendas do senador Flávio Bolsonaro (RJ);
4. manter o RJ fora do site. Nada é publicado.

Hoje o site só mostra a execução das emendas, a partir do arquivo do Portal da Transparência
(`politicos/transparencia.py`, ADRs 0023 e 0024). Esse arquivo começa no empenho: a emenda
que foi apresentada e não foi aprovada, ou que foi aprovada e nunca empenhada, não aparece.

**Como o levantamento foi feito:** leitura das páginas e dos arquivos oficiais em 26/11/2026,
sem contornar nenhum bloqueio. O que não foi lido na fonte oficial está marcado como **não
verificado**.

## A fonte oficial

A fonte é a **Comissão Mista de Planos, Orçamentos Públicos e Fiscalização (CMO)**. Os dados
vêm do sistema de emendas do Congresso (Lexor), publicados pela Câmara e pelo Congresso
Nacional.

| Item | O que foi lido |
|---|---|
| Página do PLOA 2027 | `https://www.congressonacional.leg.br/web/orcamento/acompanhe/orcamento-anual/-/loa/2027/etapas/apresentacao-emendas`: aponta para a pesquisa abaixo e para os espelhos em PDF (despesa e texto). Na tramitação da LOA 2027 consta: "Encerrado o prazo regimental, foram apresentadas 8.262 (oito mil duzentos e sessenta e duas) emendas." |
| Pesquisa de emendas à despesa | `https://www.camara.leg.br/orcamento-da-uniao/loa/emendas?ano=2027`: página HTML. O resultado sai em `emendas-loa__resultado?ano=2027&codPL=203&numMomento=10&autor=<codAutor>&pagina=N`, com um botão para baixar em PDF. |
| Listas auxiliares (JSON) | `emendas-loa/momentos?ano=`, `autores?codPL=`, `partidos`, `UFs`, `localidades`, `orgaos` e `uos`, no mesmo caminho. Para o PLOA 2027 (`codPL=203`), elas trazem 664 autores. São as listas que a própria página usa e **não têm documentação publicada**. |
| Avulso por autor (PDF) | `https://www.camara.leg.br/internet/comissao/index/mista/orca/orcamento/OR2027/emendas/despesa/00306761181_AV_LOA_AUTOR_<codAutor>.pdf`. O de 9219 tem Last-Modified de 25/11/2026 15:41:22 GMT e 142.264 bytes. A listagem da pasta responde 403. |

- **Formato:** não há arquivo de dados abertos (CSV, XLSX ou ZIP) com todas as emendas
  apresentadas. Não achei esse arquivo nas páginas do Congresso, da Câmara nem da CMO. A
  leitura possível é por autor: o HTML da pesquisa, uma página por autor, ou o PDF avulso. O
  SIGA Brasil (Senado) também tem emendas, mas **não foi verificado** se ele exporta as
  emendas apresentadas em arquivo.
- **Licença:** nenhuma das páginas lidas declara uma licença. São dados públicos do
  Legislativo, mas a licença **não foi verificada**. Antes da publicação, é preciso
  confirmá-la com a Câmara ou a CMO ou citar a política de uso do portal.
- **Campos da pesquisa:**
  - autor (nome abreviado, partido e UF) e código do autor na CMO;
  - número da emenda;
  - programática completa: função, subfunção, programa, ação e localizador;
  - título e subtítulo, com o destino em texto ("No Município de Duque de Caxias - RJ", "No
    Estado do Rio de Janeiro", "Nacional");
  - GND, modalidade de aplicação (MA), resultado primário (RP; 6 é emenda individual), fonte e
    valor.
  - Uma emenda pode ter mais de uma linha, uma por GND.
  - O PDF avulso traz também a justificativa, que **não deve ser lida** (ver LGPD).
- **Município e UF de destino:** só em texto, e o código do localizador não é o código do
  IBGE (exemplos: 3284, Bom Jesus do Itabapoana; 0033, RJ; 0035, SP; 0001, Nacional). Na fase
  "Emendas Apresentadas" o localizador pode vir vazio: em 2024 a emenda 4102 0011 aparece com
  "2E90." e só no autógrafo com "2E90.0035".
- **Frequência:** a página não segue um calendário. Ela muda a cada fase da tramitação
  (`momentos`). Em 2025 e 2026 as fases foram:
  - 10 Emendas Apresentadas;
  - 20 Fase Relatoria Setorial;
  - 30 Fase Relatoria Geral;
  - 60 Redação Final - Autógrafo.

  Em 2027 só existe a fase 10 até agora. A data de votação (17/12, segundo notícia
  republicada) **não foi verificada** na pauta oficial.
- **Dado pessoal:** os campos estruturados não trazem CPF, nascimento, título, e-mail nem
  endereço. O autor é o parlamentar no exercício do cargo, e esses dados são públicos. A
  justificativa (texto livre no PDF) pode citar pessoas e entidades, por isso fica fora da
  leitura. Nada dela é gravado.

## Teste de leitura (Flávio Bolsonaro, PLOA 2027)

- Pesquisa da Câmara, PLOA 2027 (`codPL=203`), fase 10 (Emendas Apresentadas), autor 9219
  (lista `autores`: "Flávio Bolsonaro").
- Leitura de 26/11/2026 18:09:21 UTC, só em memória: a resposta foi lida direto da rede,
  sem passar por arquivo. Ela tinha 65.826 bytes, com SHA-256
  `8863077779e7f784fb2ab33f1746d1e6415b08ce998e9d5425ab1983e88f30f9`.
  - Numa consulta anterior, no mesmo dia, a página foi gravada no scratchpad e apagada em
    seguida. Ela tinha o mesmo SHA-256, mas não entra na contagem.
- Resultado: **15 linhas, 14 emendas distintas e R$ 79.382.048,00**.
- Isso confere com o número noticiado: 14 emendas e R$ 79,382 milhões.
- Nada foi gravado no banco nem no arquivo bruto, porque o teste foi só de leitura. Para
  refazer, basta consultar a mesma URL e conferir o SHA-256. A página pode mudar nas
  próximas fases.
- Este número **não é exibido** no site. Quando o dado for coletado, cada número vai para o
  arquivo bruto com o SHA-256 da resposta, como as outras fontes.

## Ligação indicação → empenho → pagamento

**Chave: o código da emenda**, formado por ano (4), código do autor na CMO (4) e número da
emenda (4).

- O arquivo do Portal da Transparência já traz essa chave, nos campos "Código da Emenda",
  "Código do Autor da Emenda" e "Número da emenda".
- Conferido com uma emenda que já está nos testes: `202441020011` no Portal corresponde, na
  pesquisa da Câmara de 2024 (`codPL=97`), ao autor 4102 ("Helio Lopes"), emenda 0011, de
  R$ 2.247.000,00. Ela aparece tanto em "Emendas Apresentadas" quanto em "Redação Final -
  Autógrafo".
- Para o PLOA 2027, a emenda 0001 do autor 9219 seria `202792190001` no Portal, quando for
  executada.

Proposta, para aprovação:

1. **Etapas, cada uma da sua fonte oficial e com a data da coleta:**
   - *apresentada*: valor na fase 10 da CMO;
   - *aprovada*: valor no autógrafo (fase 60) da CMO;
   - *empenhada / liquidada / paga*: arquivo do Portal, como hoje.

   O valor apresentado e o aprovado podem ser diferentes. Os dois aparecem, cada um com a
   sua fonte, sem cálculo de "corte".
2. **A ligação é só pela chave completa** (ano + autor + número). Nunca por nome, valor ou
   destino. O número da emenda recomeça em 0001 para cada autor, então ano + número sozinho
   não identifica a emenda.
   - Nas duas fontes, as linhas são somadas por chave para comparar e exibir: na CMO, uma
     linha por GND; no Portal, uma linha por localidade ou ação.
   - As linhas de origem continuam guardadas.
3. **Sem correspondência**, a página diz a situação em rótulo neutro e com a data de cada
   fonte, sem atribuir causa:
   - "Apresentada; não consta no autógrafo" (só depois que o autógrafo existir);
   - "Aprovada; sem empenho no Portal da Transparência até dd/mm/aaaa";
   - "Consta no Portal da Transparência; não encontrada na pesquisa da CMO". É o caso de
     emendas de relator, comissão ou bancada com outra numeração, que não entram por
     enquanto.
4. **Mesma chave com nome de autor diferente** nas duas fontes: como o código do autor faz
   parte da chave, só o nome pode divergir.
   - A ligação não é feita, a emenda vai para a lista de divergências do portão e o caso
     volta ao Fabio.
   - Não há correção automática.
5. **Vínculo com o parlamentar:** pelas mesmas regras das emendas do Portal (ADR-0023,
   `politicos/vinculo.py`), sem regra nova. Só é gravado para UF publicada.
6. **Município de destino:** o localizador da CMO não tem código do IBGE.
   - Proposta: casar o texto "No Município de X - UF" com a lista de municípios do IBGE, por
     nome normalizado e UF, só quando o resultado for exato e único. Qualquer outro caso fica
     "sem município".
   - Isso é um mapeamento e precisa de aprovação própria antes do código. Na fase
     "aprovada/executada", vale o código do IBGE do Portal.
7. **Escopo inicial:** só emendas individuais (RP 6) de parlamentares de UF publicada.
   Bancada, comissão e relator ficam para outro ADR.

## Coleta (para quando houver código)

- Uma leitura por fase (10, 20, 30, 60), quando a fase aparecer em `momentos`. Não há
  agendamento diário.
- **Só autores de UF publicada** (SP e as UFs de `RASTRO_POL_UFS_LIBERADAS`), como na
  coleta pela API (ADR-0023, item 3). Autor de UF não liberada não é consultado nem vai para
  o arquivo bruto.
- **Paginação:** são 20 linhas por página. Em 2024, o autor 4102 tem 29 linhas, em duas
  páginas.
  - A leitura segue `pagina=1, 2, …` até cobrir o total de linhas que a página anuncia
    ("Exibindo resultados de X a Y de N encontrados").
  - O total anunciado conta linhas, não emendas distintas. O portão compara linhas lidas com
    linhas anunciadas, por autor, e barra o autor e a fase se não bater.
- Cada resposta vai para o arquivo bruto (`/api/bruto/{sha256}`), como as outras fontes, com
  limite de taxa.
- O ponto fraco é que as listas JSON e o HTML do resultado não têm documentação e podem mudar
  de formato. O portão também barra a fase se não conseguir ler o total anunciado.
- Antes do código, perguntar à CMO e à Câmara se existe um arquivo oficial com todas as
  emendas (CSV ou planilha). Se existir, ele substitui a leitura por autor.

## Decisão (proposta)

- Aprovar a CMO (pesquisa de emendas da Câmara) como fonte das fases "apresentada" e
  "aprovada", com a chave ano + autor + número para ligar ao Portal da Transparência e os
  rótulos de "sem correspondência" acima.
- Ficam para aprovações separadas: o mapeamento localizador → município (item 6), a
  confirmação da licença e a publicação.

## Fora do escopo

- Nada é publicado: nenhuma tela nova, nenhuma exportação, nenhuma trava ligada.
- O RJ continua fora do site até ser liberado (`RASTRO_POL_UFS_LIBERADAS`, T-016). O teste
  com o senador do RJ foi só de leitura, em memória.
- Sem código e sem migração neste ADR.
