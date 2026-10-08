# Coleta pelo GitHub Actions

A coleta de SP e a publicação do site passam a rodar no GitHub Actions
(`.github/workflows/coleta.yml`), em vez do Scheduled Deployment do Replit. O Actions roda
sempre o código que está no `main`: depois do merge de um PR, a próxima coleta já usa o
código novo, **sem Pull nem Republish**. O Replit fica só com a API de auditoria.

O script da coleta é o mesmo (`backend/scripts/coleta_sp.sh`, com a trava de uma coleta
por vez), e o banco é o mesmo (o de produção, no Neon).

## Por que

- O deployment do Replit só muda com Pull + Republish. Esquecido o Republish, a coleta roda
  com o código antigo (aconteceu duas vezes em 08/10).
- A publicação no `gh-pages` usa o token do próprio workflow: o token fine-grained
  (`RASTRO_GITHUB_TOKEN`) deixa de ser necessário.
- Repositório público: o Actions é gratuito nas máquinas padrão (4 vCPU e 16 GB de RAM,
  contra 1 vCPU e 2 GiB do Scheduled do Replit).

## Limites

- **6 horas por execução** (no Replit, 11 h). As coletas diárias levam cerca de 1h30. Uma
  coleta do zero (como a de 07/10, 11 h) não cabe numa execução, mas o RREO/RGF é
  retomável: o que faltar fica para a próxima.
- Só quem tem permissão de escrita no repositório pode rodar o workflow. Ele não roda em
  PRs, então os Secrets não ficam expostos a forks.

## 1. Cadastrar os Secrets (uma vez)

No GitHub: **Settings → Secrets and variables → Actions**.

Aba **Secrets → New repository secret**:

| Nome | Valor |
|---|---|
| `DATABASE_URL` | a do banco de produção: copie dos Secrets do app **rastro-coleta** no Replit |
| `RASTRO_TRANSPARENCIA_CHAVE` | a chave do Portal da Transparência (sem espaços nas pontas) |

Aba **Variables → New repository variable**:

| Nome | Valor |
|---|---|
| `RASTRO_URL_AUDITORIA` | a URL da API de auditoria (a mesma do Secret do Replit) |

## 2. Teste sem publicar

1. Confira no Replit (aba **Schedule** do rastro-coleta) que nenhuma coleta está rodando. Se
   estiver, a do Actions sai na hora com `AVISO: outra coleta está em andamento` (a trava no
   banco vale para as duas).
2. No GitHub: **Actions → Coleta → Run workflow**, com **publicar desmarcado**.
3. A execução coleta, exporta, compila o site e verifica contra o site publicado, mas não
   publica nada. No fim do log aparecem `Simulação: verificação ok; nada foi publicado` e
   `Duração da coleta: N s`.
4. Compare a duração com as do Replit (a coluna de duração na aba **Schedule**; em 08/10,
   entre 5.050 e 5.520 s).

A confirmar neste teste:
- se o banco do Replit (Neon) aceita conexão de fora do Replit;
- se a Câmara, o Senado, o TSE, o Tesouro e o Portal da Transparência respondem bem aos
  servidores do GitHub.

## 3. Teste publicando

**Run workflow** com **publicar marcado**. Depois, confira o site: o rodapé e a página
**Status das fontes** mostram a data da coleta. A publicação com o token do workflow deve
disparar a atualização do GitHub Pages; confirmar neste passo.

## 4. Troca definitiva (PR próprio, com aprovação)

- acrescentar o agendamento (`schedule`) ao workflow, no horário escolhido;
- desligar o Scheduled Deployment do rastro-coleta no Replit;
- revogar o token fine-grained `RASTRO_GITHUB_TOKEN` no GitHub e apagá-lo do Replit;
- atualizar o guia de deploy (`docs/deploy-replit.md`).

## Operação

| Situação | O que fazer |
|---|---|
| Ver uma execução | **Actions → Coleta** → a execução → o passo "Coleta, verificação e publicação" |
| Rodar fora do horário | **Run workflow** (marque **publicar** para publicar o site) |
| Execução falhou | O log mostra `ERRO: a etapa "..." terminou com código N`. Nada é publicado quando algo falha; o site continua como estava. |
| Uma fonte fora do ar | Igual ao Replit: novas tentativas com espera e, se continuar falhando, publicação com os dados anteriores e `AVISO` no fim do log |
| Cancelar uma execução | **Cancel workflow** na página da execução. A trava no banco se solta sozinha. |
