# ADR-0009: O site publicado é estático, com JSON exportado pelas rotas da API e hospedado no GitHub Pages

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commits `3b3e921` e `775120f`, formato 3)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

O site precisa ser barato, resistente a picos de acesso e independente do banco, que dorme
após 5 minutos sem consultas no Replit.

## Opções consideradas

- Deployment estático do Replit: descartado porque só é republicado pelo botão Publish,
  sem API (`docs/deploy-replit.md`, "Pontos confirmados").

## Decisão

`rastro exportar-site` (`backend/src/rastro/site.py`) chama as rotas da API dentro do
processo e grava JSON determinístico, no formato 3 descrito na docstring do módulo. A
exportação é incremental pelo `indice.json`. `rastro publicar-site` verifica tudo antes e
publica no `gh-pages` (tudo ou nada), com tags `site-*` e as 5 últimas guardadas.

## Consequências

- Mais fácil: custo zero de hospedagem; reverter é `rastro reverter-site`.
- Mais difícil: toda tela nova exige exportação em `site.py`, teste em
  `backend/tests/test_site.py` e leitura por `lerJson` (`CLAUDE.md`).
- Proibido: tela que chame a API, exceto os links de auditoria; mudar o formato exportado
  sem aprovação do Fabio.

## Como revisitar

Se o volume do site (Brasil inteiro) passar dos limites do GitHub Pages, ou se uma
funcionalidade exigir consulta dinâmica.
