# Coleta pelo GitHub Actions (só manual, para diagnóstico)

> **Decisão (ADR-0016, 09/10/2026): a coleta oficial é a do Replit.** O workflow "Coleta"
> (`.github/workflows/coleta.yml`) fica **só com disparo manual**, sem agendamento, para
> diagnóstico. **Não rode o workflow enquanto houver coleta no Replit** (confira a aba
> Schedule do rastro-coleta antes). A trava no banco impede as duas ao mesmo tempo, mas a
> que chegar depois sai sem coletar; a do Actions segura a trava por horas e pode fazer a
> coleta agendada do Replit daquele dia não acontecer.

## Resultado do teste (08–09/10/2026)

- O banco do Replit (Neon) aceitou a conexão, e as fontes responderam.
- A etapa de RREO/RGF levou 4h02 (no Replit, cerca de 54 min); o ranking ainda rodava 1 h
  depois, e a execução foi encerrada pelo limite de 350 min. Causa provável: as milhares de
  consultas ao banco, que fica em São Paulo, a partir das máquinas do GitHub.

O workflow roda o mesmo script da coleta (`backend/scripts/coleta_sp.sh`), com a mesma
trava, contra o mesmo banco de produção. Por padrão não publica (`RASTRO_SIMULAR=1`).

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
| `RASTRO_URL_AUDITORIA` | a URL da API de auditoria (a mesma do Secret do Replit) |

A `RASTRO_URL_AUDITORIA` não é sigilosa: também pode ficar na aba **Variables**. O workflow
lê das duas formas (a variável, se existir; senão, o secret).

O `DATABASE_URL` não aparece nos Secrets do Replit: copie em **Database → Production
Database → Settings → Connection string** (botão de copiar, sem revelar a senha).

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

## 4. Troca definitiva: descartada

A troca (agendamento no Actions, Replit desligado, token fine-grained revogado) não será
feita (ADR-0016). Se o banco mudar de região ou a coleta reduzir as idas ao banco, um novo
teste pode reabrir a decisão.

## Operação

| Situação | O que fazer |
|---|---|
| Ver uma execução | **Actions → Coleta** → a execução → o passo "Coleta, verificação e publicação" |
| Rodar fora do horário | **Run workflow** (marque **publicar** para publicar o site) |
| Execução falhou | O log mostra `ERRO: a etapa "..." terminou com código N`. Nada é publicado quando algo falha; o site continua como estava. |
| Uma fonte fora do ar | Igual ao Replit: novas tentativas com espera e, se continuar falhando, publicação com os dados anteriores e `AVISO` no fim do log |
| Cancelar uma execução | **Cancel workflow** na página da execução. A trava no banco se solta sozinha. |
