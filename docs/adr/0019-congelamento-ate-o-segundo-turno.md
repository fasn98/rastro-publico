# ADR-0019: Escopo congelado na metodologia v1.1.0 até o segundo turno (25/10/2026)

- **Status:** Aceito
- **Data:** 2026-10-09
- **Decidido em:** 2026-10-09 (Fabio)
- **Autor:** sessão principal
- **Decisor:** Fabio

## Contexto

A primeira coleta de produção completa (run 6qmcl, 09/10/2026) publicou o site com a
metodologia v1.1.0 do Ranking Fiscal, em prévia. O segundo turno das eleições de 2026 é
em 25/10/2026. Até lá, o site precisa ficar estável e previsível, e o esforço vai para a
expansão nacional do que já existe para SP.

## Decisão

Texto do Fabio: "escopo congelado na metodologia v1.1.0 até o fim do segundo turno
(25/10). Até lá, nenhuma mudança de metodologia, de formato ou funcionalidade nova entra
no `main`; trabalho novo pode seguir em branches, sem merge. Exceção: correções de bugs e
a expansão nacional do escopo atual."

Até 25/10/2026, inclusive:

- **Não entra no `main`:**
  - mudança de metodologia (âncoras, pesos, fórmulas, indicadores, composição da
    transparência; o arquivo `metodologia_v1_1.toml` fica em 1.1.0);
  - mudança de formato dos arquivos exportados ou da API;
  - funcionalidade nova.
- **Pode seguir em branch, sem merge:** trabalho novo, inclusive propostas e PRs em draft.
- **Entra no `main`, pelas regras de sempre (PR, CI verde, aprovação do Fabio nas
  exceções do `CLAUDE.md`):**
  - correções de bugs;
  - a expansão nacional do escopo atual: as mesmas fontes, indicadores e metodologia
    v1.1.0, para todas as UFs (coleta, portão de qualidade, seletor de UF, busca, mapa e
    ranking por UF e nacional);
  - documentação que não muda regra nem dado publicado (guias, registros de execução,
    ADRs).
- O modo prévia continua ligado.

A partir de 26/10/2026, os branches congelados voltam à fila normal de PRs, um por vez.

## Consequências

- Mais fácil: o que estiver no ar durante a eleição é a v1.1.0, auditável e estável.
- Mais difícil: propostas prontas, como a da transparência com MSC ou pontualidade,
  esperam em branch, e branches longos podem ter conflitos com o `main` depois de 25/10.
- Na dúvida se uma mudança é correção de bug ou expansão nacional, trate como congelada e
  pergunte ao Fabio.

## Como revisitar

Só o Fabio encerra o congelamento antes de 25/10 ou o prorroga.
