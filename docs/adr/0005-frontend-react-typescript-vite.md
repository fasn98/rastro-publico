# ADR-0005: O frontend é uma SPA em React, TypeScript e Vite, com rotas por hash

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `82fc84a`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

O site é servido pelo GitHub Pages (ADR-0009), que só entrega arquivos estáticos e não
reescreve rotas.

## Opções consideradas

Não registradas na época.

## Decisão

React 19 + TypeScript + Vite (`frontend/`). Navegação por `location.hash`
(`frontend/src/App.tsx`), o que funciona no GitHub Pages sem configuração de servidor. Os
dados vêm por `lerJson` (`frontend/src/dados.ts`); os links de auditoria ficam atrás de
`AUDITORIA_ATIVA`; o modo prévia vem de `VITE_PREVIA`.

## Consequências

- Mais fácil: hospedagem gratuita e sem servidor.
- Mais difícil: não há framework de testes no frontend. O CI só roda `tsc -b` e
  `vite build`.
- Proibido: `fetch` direto para a API fora dos links de auditoria.

## Como revisitar

Se o site precisar de SEO por página (as rotas por hash não são indexadas como páginas
separadas) ou de renderização no servidor.
