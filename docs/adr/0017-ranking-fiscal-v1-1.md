# ADR-0017: Ranking Fiscal v1.1: leitura corrigida, teto da autonomia 7, transparência como multiplicador e população do IBGE

- **Status:** Aceito
- **Data:** 2026-10-09
- **Decidido em:** 2026-10-09 (aprovação do Fabio às decisões D1 a D7 da proposta)
- **Autor:** sessão de deploy
- **Decisor:** Fabio

## Contexto

A primeira coleta completa de SP (645 municípios, 2023–2025, publicada em 08/10/2026 como
`site-20261008-223829`) permitiu revisar os limites provisórios da v1.0 (ADR-0012). A
revisão encontrou também dois erros de leitura. Proposta, dados e simulação reproduzível:
`docs/metodologia-v1.1/` (`PROPOSTA.md`, `simulacao.md`, `simular.py`).

## Opções consideradas

Estão na proposta, com o efeito de cada uma: transparência com peso 1, peso 0,5, fora da
nota, como multiplicador ou com a MSC; teto da autonomia 10 ou 7; pessoal acima de 100% da
RCL excluído ou mantido como declarado; per capita dentro ou fora da nota.

## Decisão

- **D1:** os indicadores usam o relatório da Prefeitura, nunca o de um consórcio entregue
  com o código do município (`indicadores._prioridade`).
- **D2:** RGF Anexo 5 sem a linha (I): I = IV − II − III. Mapeamento de contas v2.
- **D3:** teto da autonomia 10 → 7 (percentil 95 de SP = 6,94).
- **D4:** transparência como multiplicador da média dos 4 indicadores fiscais.
- **D5:** faixas pela estimativa mais recente do IBGE (SIDRA 6579).
- **D6:** valores por habitante com a população oficial do IBGE mais recente até o ano
  (6579; Censo 2022, tabela 4709, para 2023), fora da nota.
- **D7:** gasto com pessoal acima de 100% da RCL fica como declarado, com aviso no site.

Arquivo `backend/src/rastro/ranking/metodologia_v1_1.toml`, versão `1.1.0`. A v1.0 continua
em `metodologia_v1.toml`.

## Consequências

- Mais fácil: notas mais fiéis aos relatórios (Votuporanga passa a ter nota; 11
  município-anos de liquidez deixam de ser "não reportado").
- Mais difícil: as notas da v1.1 são, em geral, mais baixas que as da v1.0 (mediana 5,3 →
  4,4), porque sai o componente de transparência que valia 10 para quase todos. A página
  Metodologia explica a mudança.
- Proibido: ler o relatório de um consórcio como se fosse o do município.

## Como revisitar

Quando a transparência tiver uma medida que diferencie os municípios (por exemplo, uma
data de entrega original), ou com a coleta de outra UF.
