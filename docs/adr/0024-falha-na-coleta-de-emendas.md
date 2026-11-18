# ADR-0024: Falha na coleta de emendas de UF publicada

- **Status:** Aceito
- **Data:** 2026-11-18
- **Decidido em:** 2026-11-17 (Fabio: "Proposta de 07/11: aprovada, com estas condições")
- **Autor:** sessão principal
- **Decisor:** Fabio

## Contexto

As emendas vêm do arquivo em lote do Portal da Transparência, numa passada só para as UFs de
`RASTRO_POL_EMENDAS_UFS`. A gravação é uma transação: se a coleta falha, nada é apagado e as
linhas da coleta anterior continuam no banco.

Antes desta decisão, a falha gravava "falha" em `pol_coleta_uf` para todas as UFs da
passada, com três efeitos:
- o portão de políticos reprovava as UFs além de SP (hoje, SC), que saíam do site no dia;
- a nota das emendas sem município de destino sumia das páginas de SP e de SC;
- nada no site dizia de quando eram os dados.

## Decisão

Para cada UF com políticos no site, quando a coleta de emendas não é concluída:

1. **Dados anteriores.** O site continua com os dados anteriores. O portão não reprova a UF
   e a nota sem município continua. As seções de emendas (município, parlamentar e estado)
   mostram "Dados de dd/mm/aaaa; a coleta mais recente não foi concluída". A data é o fim da
   última coleta concluída.
2. **Mais de 7 dias.** Se nenhuma coleta for concluída por mais de 7 dias, contados da
   primeira falha, a UF ganha um aviso destacado de dados desatualizados. A UF não sai do
   site.
3. **Registro.** Cada falha vai para o log da coleta e para o resumo da execução, com a UF e
   o motivo reduzido ao tipo do erro (ex.: "HTTP 504 após 4 tentativas"), nunca trecho do
   conteúdo.

**Condição técnica.** Os dados anteriores só valem se a última coleta concluída do arquivo
incluiu a UF. Cada coleta concluída regrava todas as linhas, e o recorte só traz todas as
emendas das UFs daquela coleta. Se a UF ficou fora, a regra de sempre vale e o portão
reprova.

## Consequências

- **Manifesto:** ganha a chave `emendas_coleta`, com uma entrada só para as UFs com falha:
  `{dados_de, falha_desde, dados_anteriores, desatualizada}`. Os arquivos dos municípios e
  dos parlamentares não mudam.
- **Coleta (`coleta_sp.sh`):** o resumo da execução ganha a linha `Emendas por UF com falha:`
  e, quando há falha, um AVISO no fim.
- **Código:** `politicos/situacao_emendas.py`, usado pelo portão, pela API da nota sem
  município, pela exportação e pelo `rastro resumo-coleta`.
- **Testes:** `backend/tests/test_emendas_falha.py`. A coleta concluída usa o arquivo real do
  Portal de 13/11/2026; a falha é o Portal respondendo HTTP 504.
