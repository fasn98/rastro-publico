# Colocar o Rastro Público no ar (Replit + GitHub Pages)

Passo a passo do que precisa ser feito à mão, **na ordem**. Leva cerca de 1 hora, sem
contar a primeira coleta (~11 h, rodando sozinha).

## Como fica

| Peça | Onde | Custo |
|---|---|---|
| Site (tudo o que o visitante vê) | GitHub Pages, branch `gh-pages` | grátis |
| Coleta semanal + publicação do site | Replit, app **rastro-coleta** (Scheduled) | dentro dos créditos do Core |
| API de auditoria (resposta bruta e verificação do SHA-256) | Replit, app **rastro-auditoria** (Autoscale) | dentro dos créditos do Core |
| Banco PostgreSQL | banco de produção do app **rastro-coleta** | dentro dos créditos do Core |

O mesmo repositório vira os dois apps do Replit, porque cada app publica um único tipo de
deployment. O Secret `RASTRO_PAPEL` diz a cada um o que fazer: `coleta` ou `auditoria`.
O valor não diferencia maiúsculas e ignora espaços nas pontas (`AUDITORIA` vale). Com
qualquer outro valor, ou sem o Secret, o app termina logo ao iniciar, com a mensagem
`ERRO: RASTRO_PAPEL=... não é um papel válido. Valores aceitos: coleta, auditoria` no log.

---

## 1. Token do GitHub (para a coleta publicar o site)

1. GitHub → foto de perfil → **Settings** → **Developer settings** → **Personal access
   tokens** → **Fine-grained tokens** → **Generate new token**.
2. Preencha:
   - **Token name:** `rastro-publico-pages`
   - **Expiration:** escolha uma data. Sugestão: 90 dias.
   - **Resource owner:** `fasn98`
   - **Repository access:** *Only select repositories* → `fasn98/rastro-publico`
   - **Permissions → Repository permissions → Contents:** *Read and write*. O GitHub
     acrescenta "Metadata: Read-only" sozinho. Não marque mais nada.
3. **Generate token** e copie o valor. Ele só aparece uma vez. Não cole o token em issues,
   commits nem chats.
4. **Lembrete de renovação:** crie agora um lembrete no seu calendário para **uma semana
   antes da data de expiração**. Para renovar:
   1. no mesmo lugar, abra o token e use **Regenerate token**;
   2. atualize o Secret `RASTRO_GITHUB_TOKEN` do app rastro-coleta (passo 6);
   3. publique o app de novo.

   Se o token vencer, a coleta continua rodando, mas o site para de ser atualizado.

## 2. Replit: plano e alerta de gastos

1. Assine o **Replit Core** em Settings → Account → Billing.
2. Em **Settings → Account → Usage → Manage limits**, crie um **alerta de uso**. A
   documentação diz que os limites de uso valem para o que passar dos créditos mensais do
   plano. Então, para ser avisado perto de **US$ 30/mês no total**, use um alerta de
   **US$ 10** acima dos créditos. Confira na tela se ela mostra o valor total ou o valor
   acima dos créditos, e ajuste.
3. **Não** ative o *limite de desligamento*: ele suspende os serviços (inclusive a API de
   auditoria) quando atingido. O alerta basta para começar.

## 3. App de auditoria (primeiro, para ter a URL dela)

1. Abra **replit.com/import** → GitHub → conecte a conta → `fasn98/rastro-publico` →
   **Import**. Dê o nome **rastro-auditoria**.
2. **Publishing** → tipo **Autoscale**.
3. Em **Production app secrets**, crie:
   - `RASTRO_PAPEL` = `auditoria`
   - `RASTRO_CORS_ORIGENS` = `https://fasn98.github.io,http://localhost:5173`
4. **Publish**. Anote a URL pública, por exemplo `https://rastro-auditoria.replit.app`.
5. Abra `<URL>/api/saude`. Tem que aparecer `{"status":"ok"}`. O banco entra no passo 7.

## 4. App de coleta: importar e testar o acesso às fontes

1. Importe o repositório de novo e dê o nome **rastro-coleta**.
2. Abra o **Shell** do app e rode:

   ```bash
   bash backend/scripts/replit_build.sh
   cd backend && export PATH="$HOME/.local/bin:$PATH" && uv run rastro testar-fontes
   ```

3. Todas as linhas precisam sair **OK**. Se alguma fonte der **FALHA**, pare aqui e me
   mande a saída: a API daquela fonte pode bloquear os IPs do Replit.

## 5. App de coleta: banco de produção

1. Abra a ferramenta **Database** do rastro-coleta e crie o banco de **produção**. Se o
   Replit oferecer criá-lo só na publicação, aceite no passo 6.
2. Em **Settings** do banco, ative os **backups agendados**. No Core, guarde 7 dias.
3. **Senha do banco: forte e única.** O banco de produção do Replit vem com um usuário
   (`neondb_owner`) e uma senha gerados pelo próprio Replit. Use essa string, nunca a
   `rastro:rastro` de desenvolvimento: os dois apps **se recusam a subir** com ela
   (`rastro conferir-producao`, chamado por `scripts/replit.sh` antes de tudo).
   - Não copie essa senha para nenhum outro serviço, arquivo ou conversa.
   - Se ela vazar (aparecer num log, num print, num commit), use **regenerar as
     credenciais** do banco de produção na ferramenta Database e atualize o Secret
     `DATABASE_URL` dos dois apps.

## 6. App de coleta: publicar como Scheduled

1. **Publishing** → tipo **Scheduled**.
2. **Agendamento da primeira coleta:** a primeira vez leva ~11 h para SP, e cada execução
   agendada tem limite de 11 h. Por isso, comece **diário** (cron `20 4 * * *`, fuso
   America/Sao_Paulo). O lote retoma de onde parou se o limite de tempo interromper.
3. Em **Production app secrets**, crie:
   - `RASTRO_PAPEL` = `coleta`
   - `RASTRO_GITHUB_TOKEN` = o token do passo 1
   - `RASTRO_URL_AUDITORIA` = a URL anotada no passo 3
   - `DATABASE_URL`: o Replit cria sozinho para o banco de produção. Confira que ela aparece.
4. **Publish**.
5. Depois da **primeira publicação do site** (passo 8), mude o agendamento para
   **semanal**, por exemplo `20 4 * * 1` (segunda-feira às 4h20).

## 7. Ligar a API de auditoria ao banco

A API de auditoria deve usar um usuário **só de leitura**, que enxerga apenas as 4
tabelas de que ela precisa (`resposta_bruta`, `payload_bruto`, `demonstrativo_resposta`,
`conta_demonstrativo`) e não consegue gravar nada.

1. No **Shell** do rastro-coleta, com o `DATABASE_URL` **de produção** carregado (copie a
   connection string em Database → banco de produção → Settings):

   ```bash
   cd backend && DATABASE_URL='<connection string de produção>' uv run rastro criar-usuario-auditoria
   ```

   O comando gera uma senha forte (256 bits, aleatória, só para este usuário), cria o
   usuário `rastro_auditoria` com leitura apenas dessas 4 tabelas e com toda transação em
   modo só leitura, e imprime **uma vez** a string de conexão dele. Rodar de novo troca a
   senha.
2. **Se funcionou:** no **rastro-auditoria** → Publishing → Production app secrets, crie
   `DATABASE_URL` = a string impressa. Depois, **Publish** de novo. Apague a linha do
   histórico do Shell (`history -c`).
3. **Se o Replit não permitir** (o comando termina com `ERRO: o banco não permitiu criar
   o usuário só de leitura`): use a connection string principal no rastro-auditoria e
   anote o resultado na seção **Riscos aceitos**, abaixo, com a data e a mensagem de erro.

## 8. Primeira publicação e GitHub Pages

1. Espere a primeira execução do rastro-coleta terminar. O log aparece em Publishing →
   Logs. A última linha deve ser `Site publicado: site-AAAAMMDD-HHMMSS`.
2. No GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   branch **`gh-pages`**, pasta **`/ (root)`** → **Save**. O branch `gh-pages` só existe
   depois da primeira publicação.
3. Em alguns minutos o site fica em **https://fasn98.github.io/rastro-publico/**.
4. Confira:
   - busca de um município, ranking com mapa, página de um político e metodologia;
   - um link de **resposta original**: ele precisa abrir a API de auditoria sem erro de CORS;
   - o rodapé com a data da coleta.
5. Volte ao passo 6.5 e troque para o agendamento **semanal**.

## Operação

| Situação | O que fazer |
|---|---|
| Ver publicações guardadas | Shell do rastro-coleta: `cd backend && uv run rastro listar-publicacoes` |
| Reverter o site para a publicação anterior | `RASTRO_GITHUB_TOKEN=<token> uv run rastro reverter-site` (ou `--para site-AAAAMMDD-HHMMSS`) |
| Uma fonte fora do ar | nada a fazer: a próxima execução retoma; o site não perde dados |
| Código novo no `main` | nos dois apps: Git → **Pull**, depois **Publish** |
| Token vencendo | passo 1.4 |
| App reiniciando sem parar (*crash loop*) | Publishing → **Logs**. Se aparecer `ERRO: RASTRO_PAPEL` ou `ERRO: o Secret RASTRO_PAPEL não está definido`, corrija o Secret em Publishing → Production app secrets (`coleta` ou `auditoria`) e publique de novo. Os Secrets de produção não aparecem no Shell do editor: para testar um valor lá, rode `RASTRO_PAPEL=<valor> bash backend/scripts/replit.sh --validar-papel` |
| Forçar exportação do zero | a coleta parte do `dados/` publicado e só regrava o que mudou; para refazer tudo, rode `uv run rastro exportar-site --uf SP --saida <pasta> --completa` |

São guardadas as **5 últimas publicações** (tags `site-*` no GitHub). Uma publicação nova
apaga a mais antiga.

## Riscos aceitos

| Risco | Situação | Mitigação |
|---|---|---|
| API de auditoria com a credencial principal do banco (só se o passo 7.1 falhar) | *preencher após o passo 7: "usuário só de leitura criado em DD/MM/AAAA" ou "Replit recusou em DD/MM/AAAA: <mensagem>"* | o código da API de auditoria só faz `SELECT` (3 rotas `GET`, testadas); CORS só aceita o site; a senha fica só nos Secrets de produção; backups agendados de 7 dias (passo 5.2) |

## Pontos confirmados na documentação oficial do Replit

- O banco de produção **dorme após 5 minutos sem consultas**. A computação só é cobrada
  enquanto ele está acordado
  ([Publishing and Database Billing](https://docs.replit.com/billing/about-usage-based-billing)).
- Um **deployment estático do Replit só é republicado pelo botão Publish**. A documentação
  não traz forma automática ou API para isso
  ([Static Deployments](https://docs.replit.com/references/publishing/static-deployments),
  [Deployment and publishing](https://docs.replit.com/help/deployment-and-publishing)). Por
  isso o site fica no GitHub Pages, que a coleta atualiza sozinha com um `git push`.
- Scheduled Deployments têm **limite de 11 h por execução**
  ([Scheduled Deployments](https://docs.replit.com/references/publishing/scheduled-deployments)).
- O banco de produção **aceita conexão de outros apps** pela string de conexão
  ([Development and production databases](https://docs.replit.com/cloud-services/storage-and-databases/production-databases)).
- A string de conexão do banco do Replit tem o formato
  `postgresql://neondb_owner:<senha>@<host>.neon.tech/<banco>`, com credenciais geradas
  pelo Replit, que podem ser **regeneradas** se vazarem. Na atualização do banco, papéis
  (roles) personalizados e suas permissões são migrados, mas as senhas deles precisam ser
  redefinidas
  ([Connection details](https://docs.replit.com/features/data-and-storage/connection-details),
  [Database Upgrade](https://docs.replit.com/references/data-and-storage/database-upgrade)).
  Se isso acontecer, rode `rastro criar-usuario-auditoria` de novo.
- Os **Secrets de produção são separados** dos do editor e ficam em Publishing
  ([Secrets](https://docs.replit.com/core-concepts/project-editor/app-setup/secrets)).
- **Alertas e limites de uso** ficam em Settings → Account → Usage
  ([Managing Your Spend](https://docs.replit.com/billing/managing-spend)).

## Pontos ainda não confirmados (conferir na primeira vez)

- Os nomes dos módulos no `.replit` (`python-3.12`, `nodejs-20`). Se o Replit recusar
  algum, troque pela versão que ele oferecer.
- Se o usuário dono do banco no Replit tem permissão para criar outros usuários (passo
  7.1). A documentação cita papéis personalizados, mas não diz como criá-los; o comando
  tenta e informa o resultado.
- O uso do `uv` no Replit: o padrão dele é o poetry. O script de build instala o `uv` via
  pip se ele não existir.
