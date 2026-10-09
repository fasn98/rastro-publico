# ADR-0016: Onde roda a coleta agendada e a publicação do site: GitHub Actions ou Replit Scheduled

- **Status:** Proposto
- **Data:** 2026-10-08
- **Autor:** registro na migração para o squad
- **Decisor:** Fabio

## Contexto

Hoje a coleta semanal de SP e a publicação do site rodam no Replit (app `rastro-coleta`,
Scheduled Deployment). O PR #21 acrescentou `.github/workflows/coleta.yml`, que roda o
mesmo `backend/scripts/coleta_sp.sh` no GitHub Actions, só por `workflow_dispatch`, sem
agendamento e sem publicar por padrão (`RASTRO_SIMULAR=1`). Guia em
`docs/coleta-actions.md`.

Em 2026-10-08 havia uma execução de teste do workflow "Coleta" em andamento no `main`
(run `37858037605`). O resultado dela ainda não foi conferido neste registro.

## Opções consideradas

### A) GitHub Actions
- Prós: roda sempre o código do `main`, sem Pull nem Republish (o Republish esquecido fez a
  coleta rodar com código antigo duas vezes em 08/10); publica com o token do próprio
  workflow, o que dispensa o token fine-grained `RASTRO_GITHUB_TOKEN`; é gratuito em
  repositório público, em máquina com 4 vCPU e 16 GB.
- Contras: limite de 6 h por execução (11 h no Replit); uma coleta do zero não cabe e
  depende da retomada do lote. Ainda não confirmado: se o Neon aceita conexão de fora do
  Replit e se as fontes respondem bem aos IPs do GitHub. O `DATABASE_URL` de produção passa
  a ficar também nos Secrets do GitHub.
- Custo de reverter: baixo. É só religar o Scheduled do Replit; o script é o mesmo.

### B) Replit Scheduled (situação atual)
- Prós: em produção e testado; limite de 11 h; o banco fica na mesma plataforma.
- Contras: exige Pull + Republish a cada mudança no `main`; 1 vCPU e 2 GiB; precisa do
  token fine-grained com renovação manual.
- Custo de reverter: baixo.

## Decisão

**Em aberto.** Depende do resultado dos testes descritos em `docs/coleta-actions.md`
(passos 2 e 3) e da aprovação do Fabio.

## Consequências

Se A for aceita, a troca definitiva é um PR próprio, com aprovação (`docs/coleta-actions.md`,
passo 4): agendamento no workflow, Scheduled do Replit desligado, token fine-grained
revogado e `docs/deploy-replit.md` atualizado. O ADR-0010 (auditoria no Replit) não muda.

## Como revisitar

Depois do teste sem publicar e do teste publicando no Actions.
