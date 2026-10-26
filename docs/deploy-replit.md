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

1. No **Shell** do rastro-coleta, a partir da raiz do projeto (`cd ~/workspace`), use a
   connection string **de produção** (copie em Database → banco de produção → Settings).
   São dois comandos, com uma conferência no meio, no mesmo padrão do passo 2 da migração
   (ver "Passo 2, comandos", em Operação):

   a. Conferir o destino, sem gravar nada (cole a string de produção quando o `read`
      pedir; ela não aparece na tela nem no histórico):

      ```bash
      read -rs DATABASE_URL; export DATABASE_URL; unset RASTRO_DATABASE_URL; cd backend && if [ -z "$DATABASE_URL" ]; then echo "DATABASE_URL vazio: pare"; else uv run python -c "from rastro.db import get_engine; print(get_engine().url.render_as_string(hide_password=True))"; fi
      ```

   b. Só se a linha impressa for o banco de produção (host e nome do banco) e trouxer
      `sslmode=require`:

      ```bash
      uv run rastro criar-usuario-auditoria
      ```

   - **O `unset RASTRO_DATABASE_URL` é obrigatório.** Se essa variável existir,
     `config._url_do_ambiente` ignora o `DATABASE_URL`, e o usuário é criado no banco
     errado sem avisar.
   - **Não rode o comando b com o `DATABASE_URL` vazio.** Sem ele, o código cai no padrão
     `localhost`. O comando a para nesse caso.
   - Se a linha impressa não trouxer `sslmode=require`, repita o comando a com a string
     corrigida: se ela já tiver `sslmode` com outro valor (`prefer`, `disable`...), troque o
     valor por `require`; se não tiver `sslmode`, acrescente `?sslmode=require` no fim (ou
     `&sslmode=require`, se ela já tiver `?`). Nunca deixe dois `sslmode` na mesma string.
     A string do usuário de auditoria impressa pelo comando b herda esse parâmetro.

   O comando b gera uma senha forte (256 bits, aleatória, só para este usuário), cria o
   usuário `rastro_auditoria` com leitura apenas dessas 4 tabelas e com toda transação em
   modo só leitura, e imprime **uma vez** a string de conexão dele. Rodar de novo troca a
   senha.
2. **Se funcionou:** no **rastro-auditoria**, abra **Publishing → Infrastructure →
   Production environment secrets** (na tela de Republish, a seção "Production app
   secrets" → "Deployment secrets") e ponha `DATABASE_URL` = a string impressa, sem
   espaços nem aspas nas pontas. Os Secrets do editor (Tools → Secrets) **não** valem para
   o app publicado: se a string ficar só lá, a auditoria continua com a anterior ou dá
   erro 500 ao conectar (traceback em `pool ... checkout`). Depois, **Republish**. Feche o
   Shell: a string do usuário de auditoria fica impressa na tela. Teste: `…/api/respostas/1` devolve um JSON
   que começa com `{"id":1,`.
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

## Duração e execuções de referência

| Execução | Data | Resultado | Duração |
|---|---|---|---|
| 6qmcl (Run now) | 09/10/2026, início 09:11 (horário de Brasília) | **primeira execução de produção completa**: `Fontes com falha: nenhuma`; `Site publicado: site-20261009-142118` (3.058 arquivos, 645 municípios, 8.043 políticos, 1.826 regravados); sem `IdleInTransactionSessionTimeout`; emendas pela API do Portal da Transparência (1.711 registros); a Câmara respondeu HTTP 504 uma vez e passou na nova tentativa | 7.803 s (2 h 10 min) |

- **Duração de referência:** cerca de **2 h 10 min** para SP, com a base já coletada. É uma
  única medida; esta tabela é atualizada com as próximas execuções semanais. Fica perto de
  20% do limite de 11 h do Scheduled.
- A primeira coleta do zero é mais longa (passo 6.2).
- Uma fonte que falha alonga a execução em até 7 minutos de espera por tentativa
  (1, 2 e 4 minutos), além do tempo de cada tentativa.

## Operação

> **Nunca faça Republish nem Run now enquanto houver execução em andamento. Confira a aba
> Schedule antes.** Um Republish troca a versão publicada e pode encerrar a execução em
> andamento sem traceback no log; um Run now abre uma segunda execução, que sai na hora
> sem fazer nada (ver "Duas execuções em Running" abaixo).

> **Quando o `main` trouxer uma migração nova do Alembic** (um arquivo novo em
> `backend/alembic/versions/`, como a 0021), a ordem no rastro-coleta é:
> **1. Pull → 2. `alembic upgrade head` no Shell → 3. Republish**, nesta ordem, e fora de
> uma execução em andamento. No passo 2, use a string do banco **de produção** (o Shell
> carrega a do banco de desenvolvimento), na forma descrita em "Passo 2, comandos" abaixo.
> A saída do `upgrade` deve citar a migração nova
> (`Running upgrade ... -> 0021`); sem nenhuma linha "Running upgrade", o banco já estava em
> dia. A coleta também roda `alembic upgrade head` no início de cada execução, mas aplicar
> antes do Republish garante que o código novo nunca encontre o banco no formato antigo.
> Migrações só de dados levam alguns minutos no banco nacional: na medição da sessão de
> políticos (15/10/2026), a 0022 (CPF em texto livre) levou cerca de 1,5 min e a 0023 (cota:
> CPF no número do documento e e-mail do fornecedor) cerca de 2,5 min. Se não forem
> aplicadas no Shell, a primeira coleta depois do Republish as aplica e demora isso a mais.
>
> **Passo 2, comandos** (forma decidida pelo Fabio em 26/10/2026, na 0024). São dois
> comandos, com uma conferência no meio:
>
> 1. Conferir o destino, sem migrar nada, a partir da raiz do projeto (`cd ~/workspace`;
>    o comando entra em `backend`). Cole a string de produção quando o `read` pedir; ela
>    não aparece na tela nem no histórico, e o cursor fica parado até você colar e apertar
>    Enter:
>    `read -rs DATABASE_URL; export DATABASE_URL; unset RASTRO_DATABASE_URL; cd backend && if [ -z "$DATABASE_URL" ]; then echo "DATABASE_URL vazio: pare"; else uv run python -c "from rastro.db import get_engine; print(get_engine().url.render_as_string(hide_password=True))" && uv run alembic current; fi`
> 2. Só se a linha impressa for o banco de produção (host e nome do banco) e trouxer
>    `sslmode=require`: `uv run alembic upgrade head && uv run alembic current`, e depois
>    feche o Shell.
>
> - **O `unset RASTRO_DATABASE_URL` é obrigatório.** Se essa variável existir,
>   `config._url_do_ambiente` ignora o `DATABASE_URL`, e a migração roda no banco errado sem
>   avisar.
> - **Não rode o comando 2 com o `DATABASE_URL` vazio.** Sem ele, o código cai no padrão
>   `localhost`. O comando 1 para nesse caso.
> - A string do Replit (`postgres://` ou `postgresql://`) serve como está: o código troca o
>   prefixo por `postgresql+psycopg://` e mantém os parâmetros. Se a linha impressa não
>   trouxer `sslmode=require`, repita o comando 1 com a string corrigida: se ela já tiver
>   `sslmode` com outro valor (`prefer`, `disable`...), troque o valor por `require`; se não
>   tiver `sslmode`, acrescente `?sslmode=require` no fim (ou `&sslmode=require`, se ela já
>   tiver `?`). Nunca deixe dois `sslmode` na mesma string. Sem `require`, o driver aceita
>   conexão sem TLS. O `require` não valida o certificado do servidor; a troca por
>   `verify-full` está no backlog (T-019).
>
> **Nenhum Publish/Republish antes de a produção estar migrada pelo Alembic.** Vale para a
> operação, depois da instalação. Na instalação (passos 3 a 8), os primeiros Publish criam
> os apps (e o banco de produção, se o Replit só oferecer criá-lo ali, passo 5), e a
> primeira coleta cria o esquema pelo Alembic. Na operação, o passo 3 só começa depois de o
> comando 2 terminar em `(head)` com a string de produção (ou de o comando 1 já mostrar
> `(head)`). Em 26/10/2026, o Publish das 12:45 foi feito com a
> produção ainda na 0023; a 0024 foi aplicada pelo Alembic às 13:05, sem erro. Como a 0024
> usa `add_column` e `create_index` sem `IF NOT EXISTS`, isso mostra que o Publish não criou
> a coluna. Entre 12:45 e 13:05, o banco de produção não tinha `pol_emenda.uf_destino`, que
> o código do #66 usa.
>
> **Na tela de Publish/Republish, nunca aceite mudança de banco proposta pelo Replit.** As
> mudanças de esquema da produção entram só pelo Alembic, no passo 2. Com produção e
> desenvolvimento na mesma migração, a tela não deve propor nada. Se propuser, não aplique:
> pare e confira com `alembic current` nos dois bancos.
>
> **O Agent do Replit não mexe no banco de produção.** Não peça a ele, nem aceite dele,
> migração, SQL, correção de esquema ou de dados na produção, mesmo que ele proponha como
> conserto de uma diferença entre os bancos. A produção só muda pelo Alembic, no passo 2,
> pela coleta agendada ou pelo `rastro criar-usuario-auditoria` rodado por você no Shell
> (passo 7 da instalação, que cria ou renova o usuário só de leitura da auditoria).

> **No painel Git do Replit, use apenas Pull; nunca Sync Changes nem Push. Os commits locais
> do Replit são registros de publicação e configuração do app e não devem ir para o
> GitHub.** Cada Publish cria commits locais ("Published your App", "Update Replit
> configuration settings"), que aparecem como "Sync Changes N↑". Eles são de cada app: o
> rastro-coleta (Scheduled) e o rastro-auditoria (Autoscale) usam o mesmo repositório, e a
> configuração de publicação de um não serve para o outro. O `main` só recebe mudanças por PR.

| Situação | O que fazer |
|---|---|
| Ver publicações guardadas | Shell do rastro-coleta: `cd backend && uv run rastro listar-publicacoes` |
| Reverter o site para a publicação anterior | `RASTRO_GITHUB_TOKEN=<token> uv run rastro reverter-site` (ou `--para site-AAAAMMDD-HHMMSS`) |
| Uma fonte fora do ar | Nada a fazer. A fonte é tentada de novo com espera de 1, 2 e 4 minutos (`RASTRO_FONTE_ESPERAS`, em segundos). Se continuar falhando, o site é publicado com os dados anteriores dela e a execução termina com **AVISO** (não com erro). O log traz o traceback completo e a linha `Fontes com falha: pol-camara (HTTP 504 após 4 tentativas; ...)`; o site mostra um aviso no topo e a página **Status das fontes** (`#/fontes`). Se a fonte nunca tinha sido coletada, as seções dela aparecem como "fonte indisponível nesta coleta". A próxima execução tenta de novo. |
| Duas execuções em "Running" | Só uma coleta roda por vez (trava no banco). Uma execução iniciada com outra em andamento termina na hora com `AVISO: outra coleta está em andamento desde ...` e não mexe em nada. Se o processo da anterior morrer (Republish, limite de tempo, reinício), a trava se solta sozinha. Se a anterior tiver sido interrompida mas a conexão dela continuar aberta no banco (sem nenhuma consulta há mais de 10 minutos, ou aberta há mais de 12 horas), a execução seguinte encerra essa conexão, solta a trava e recomeça a coleta, com `AVISO: a coleta anterior foi interrompida sem soltar a trava (...)`. Os registros dela que ficaram "executando" passam a "interrompida". Nada fica bloqueado para sempre. |
| Prévia e lançamento | Enquanto o lançamento não for aprovado, todo build do site sai em **prévia**: faixa "Prévia — dados em validação" em todas as páginas e `<meta name="robots" content="noindex">` (fora dos buscadores). A prévia não esconde dados: ranking e links de auditoria continuam visíveis. O lançamento é um PR que troca o padrão de `RASTRO_PREVIA` para `0` em `backend/scripts/coleta_sp.sh`, com aprovação do Fabio. |
| Carga nacional do RREO/RGF (ADR-0020) | A coleta lê todas as UFs (municípios, estados e DF), UF por UF, das menores para as maiores; primeiro 2023 a 2025, depois 2026 e 2022. Cada execução para de começar itens novos depois de `RASTRO_LOTE_LIMITE_MIN` minutos (padrão 420; Secret opcional) e continua na seguinte. O log mostra `Limite de tempo atingido: N itens continuam na próxima execução`, e o resto da coleta (ranking, site) roda normalmente. **Durante a carga, agendamento diário** (`20 4 * * *`). **Volte ao semanal** (`20 4 * * 1`) quando a carga terminar (`Lote N: X/X itens concluídos`, sem a linha do limite de tempo) e duas execuções completas seguidas tiverem `Duração da coleta` abaixo de 28.800 s (8 h). Num lote novo, o exercício corrente e o anterior são relidos sempre, e os mais antigos em rodízio de 4 semanas. |
| Portão de qualidade por UF (ADR-0020) | Depois do ranking, o log lista cada UF: `AC: aprovada` ou `MG: reprovada (coleta incompleta: N ente-exercício(s) sem extrato lido ...)`, e no fim `Portão: N/27 UFs aprovadas: ...`. Durante a carga nacional, é normal a maioria estar reprovada por coleta incompleta. Só as aprovadas entram no site; uma UF reprovada que já estava no site fica com a versão anterior. O resultado de cada UF fica no `manifesto.json` publicado, em `ufs`. Reprovação por SHA-256 do bruto ou por célula diferente da fonte é problema a investigar (me mande o log). Se o próprio portão falhar, aparece `AVISO: o portão de qualidade falhou; o site sai só com SP, como antes`. |
| Políticos de todas as UFs (aprovado em 10/10/2026) | A coleta diária lê deputados, senadores e TSE das 27 UFs; as **emendas, de SP e de SC** (SC desde 15/10/2026: nenhum conteúdo de SP muda; 447 arquivos de SP mudam só no SHA-256 da auditoria). Com as emendas de todas as UFs, emendas para municípios de SP ganham vínculo com deputados de outras UFs e os arquivos de SP mudam (links para páginas de político que o site não exporta); com a divisão, a exportação de SP fica idêntica à de um banco só com SP (conferido por SHA-256 em 10/10/2026). O site só publica os políticos de SP; as outras UFs e as emendas nacionais entram com o portão de políticos e a exportação por UF. Cada chamada para depois de `RASTRO_POLITICOS_LIMITE_MIN` minutos (padrão 90; Secret opcional): o log mostra `pol-...: não coletada (limite de tempo de 90 min atingido)` e a execução termina com AVISO, sem erro; a próxima continua de onde parou. |
| Log começa com `AVISO: o código publicado (...) está N versão(ões) de código atrás do main (...)` | O Replit está rodando código antigo: faltou **Pull + Republish** no rastro-coleta. A coleta segue mesmo assim, com o código antigo, e o aviso se repete no fim do log. O primeiro hash é o do commit mais recente com o mesmo código que está no Replit; o segundo, o do `main`. `Código publicado em dia` = nada a fazer. A conferência compara os arquivos de `backend/` e `frontend/` com a API do GitHub; commits só de documentação não pedem Republish. |
| Workflow "Coleta" do GitHub Actions | Só disparo manual, para diagnóstico (ADR-0016). **Não rode enquanto houver coleta no Replit**: confira a aba Schedule antes. A do Actions é cerca de 4,5 vezes mais lenta e seguraria a trava no banco, e a coleta agendada do Replit daquele dia sairia sem coletar. |
| `IdleInTransactionSessionTimeout` (terminating connection due to idle-in-transaction timeout) | O banco de produção encerra a conexão que fica com uma transação aberta e ociosa além de `idle_in_transaction_session_timeout`; o valor aparece no início do log, na linha `Banco de produção: idle_in_transaction_session_timeout = ...` (`rastro conferir-producao`). **Em produção: `5min`** (execução 6qmcl, 09/10/2026). Nenhuma etapa pode deixar uma transação aberta e parada por 5 minutos. Em 09/10/2026 (execução 6pfw6) a exportação falhava assim, perto do fim (cerca de 5.000 a 5.500 s). Corrigido no código: a exportação lê em autocommit, e os coletores fecham a transação antes de ir à rede. **Não** se resolve aumentando o limite no servidor. Se voltar a acontecer, o traceback mostra o comando; teste novo em `tests/test_site_transacao_ociosa.py`. |
| `npm error Exit handler never called!` ou `tsc: not found` no log | A instalação das dependências do frontend quebrou. Elas são instaladas no **build** do deployment (Republish), e a coleta só reinstala se faltar algo, com até 3 tentativas; o npm pode quebrar e ainda sair com código 0, por isso o script confere se `tsc` e `vite` ficaram instalados. Nada é publicado quando isso falha (o site continua como estava). Se o erro aparecer no build, faça o Republish de novo; se aparecer na coleta, a próxima execução tenta de novo. |
| Execução terminou com erro | Só acontece quando algo crítico falha: banco, migrações, verificação do arquivo bruto, exportação ou verificação do site, ou o envio ao GitHub. Nesses casos nada é publicado e o site continua como estava; veja a última mensagem de erro no log. |
| Código novo no `main` | nos dois apps: Git → **Pull** (nunca Sync Changes nem Push); se o `main` trouxer migração nova, migre a produção pelo Alembic (ver "Quando o `main` trouxer uma migração nova", em Operação) e confira `(head)`; só depois **Publish** |
| Token vencendo | passo 1.4 |
| App reiniciando sem parar (*crash loop*) | Publishing → **Logs**. Se aparecer `ERRO: RASTRO_PAPEL` ou `ERRO: o Secret RASTRO_PAPEL não está definido`, corrija o Secret em Publishing → Production app secrets (`coleta` ou `auditoria`) e publique de novo. Os Secrets de produção não aparecem no Shell do editor: para testar um valor lá, rode `RASTRO_PAPEL=<valor> bash backend/scripts/replit.sh --validar-papel` |
| Forçar exportação do zero | a coleta parte do `dados/` publicado e só regrava o que mudou; para refazer tudo, rode `uv run rastro exportar-site --uf SP --saida <pasta> --completa` |

São guardadas as **5 últimas publicações** (tags `site-*` no GitHub). Uma publicação nova
apaga a mais antiga.

## Riscos aceitos

| Risco | Situação | Mitigação |
|---|---|---|
| API de auditoria com a credencial principal do banco (só se o passo 7.1 falhar) | **Não ocorre:** usuário só de leitura `rastro_auditoria` criado em 10/10/2026 (senha trocada no mesmo dia) e em uso no rastro-auditoria; link de auditoria testado em 10/10/2026 (`/api/demonstrativos/{id}/respostas` respondeu 200) | o código da API de auditoria só faz `SELECT` (3 rotas `GET`, testadas); CORS só aceita o site; a senha fica só nos Secrets de produção; backups agendados de 7 dias (passo 5.2) |

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
