# ADR-0010: A auditoria é servida por uma API separada, só de leitura

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `3b3e921`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

As respostas brutas não cabem no site estático, e a verificação do SHA-256 precisa reler o
banco. Ao mesmo tempo, o banco não deve ficar exposto além do necessário.

## Opções consideradas

Não registradas na época.

## Decisão

`rastro.api.auditoria:app` expõe só `/api/respostas/{id}`, `/api/respostas/{id}/bruto`,
`/api/demonstrativos/{id}/respostas` e `/api/bruto/{sha256}`. Roda no Replit (app
`rastro-auditoria`, Autoscale) com `RASTRO_PAPEL=auditoria`, CORS restrito a
`RASTRO_CORS_ORIGENS`, cache de 1 ano e `ETag` igual ao SHA-256. Usuário de banco só de
leitura via `rastro criar-usuario-auditoria`.

## Consequências

- Mais fácil: o site continua estático; a auditoria escala sozinha e o banco só acorda
  quando alguém audita.
- Mais difícil: depende de o Replit permitir o usuário só de leitura. O resultado do passo
  7 ainda não está anotado em "Riscos aceitos" (`docs/deploy-replit.md`).
- Proibido: rota de escrita na API de auditoria.

## Como revisitar

Se o Replit deixar de ser usado (ver ADR-0016), ou se o custo do Autoscale crescer.
