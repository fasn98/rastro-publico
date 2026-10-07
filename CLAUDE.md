# Rastro Público — instruções para o Claude

## Idioma

Responda sempre em **português do Brasil**: conversas, relatórios, mensagens de commit,
descrições de PR, comentários no GitHub e comentários no código.

## Princípios do projeto

- **Nenhum dado inventado, estimado ou fictício**, nem em testes. Os testes usam
  respostas reais das fontes, gravadas em `backend/tests/fixtures/`.
- **Todo número exibido** tem fonte oficial, link, período e data da coleta. A auditoria
  leva à resposta bruta arquivada, pelo SHA-256 (`/api/bruto/{sha256}`).
- **Rótulos neutros.** Nunca usar "desvio", "corrupção" ou termos parecidos sem auditoria
  ou decisão judicial citada. Nenhuma nota, ranking ou cor de "bom/ruim" para pessoas.
- **LGPD.** Nenhum CPF, data de nascimento, título de eleitor, e-mail ou endereço de
  pessoa física em nenhuma tabela nem no arquivo bruto. A redação é feita na coleta
  (`coletores/redacao.py`, `politicos/lgpd.py`).
- **O site publicado é estático.** Nenhuma tela chama a API, exceto os endpoints de
  auditoria. Toda tela nova exige:
  - exportação em `backend/src/rastro/site.py`, pelas rotas da API, para que as travas
    `Settings.pol_publicar_*` valham;
  - teste em `backend/tests/test_site.py`;
  - leitura no frontend por `lerJson` (`frontend/src/dados.ts`), com os links de
    auditoria atrás de `AUDITORIA_ATIVA`.
- **Pare e peça aprovação do Fabio antes de:**
  - mapeamentos de contas;
  - regras de cruzamento de dados;
  - exceções;
  - publicação de dados novos;
  - mudanças de formato.

## Fluxo de Git

- O `main` só recebe mudanças **por PR, um por vez, com CI verde**.
- Cada sessão trabalha no próprio branch.
- Migrações do Alembic são numeradas a partir da **última que está no `main`**.

### Merge dos próprios PRs

A sessão pode fazer o merge do PR que ela mesma abriu, **sem pedir autorização ao Fabio**,
quando o CI estiver verde no último commit e não houver conflito com o `main`.

**Exceções: pare e mostre ao Fabio antes do merge** quando o PR:
- muda dados que aparecem no site: publicar fonte nova, ligar trava, mudar regra de
  vínculo ou de cruzamento;
- muda a metodologia, as fórmulas ou os pesos do ranking;
- muda o formato dos arquivos exportados ou o pipeline de publicação;
- mexe em segurança, LGPD ou credenciais.

Na dúvida se um PR se enquadra numa exceção, trate como exceção e pare para a aprovação
do Fabio. Se o `main` mudar antes do merge, traga o `main` para o branch e espere o CI
verde de novo antes de mesclar.

## Onde ler mais

- `README.md`: visão geral, arquitetura e como rodar.
- `backend/src/rastro/politicos/README.md`: módulo de políticos (fontes, cruzamentos,
  travas de publicação, LGPD).
- `docs/deploy-replit.md`: deploy (Replit + GitHub Pages), operação e riscos aceitos.
- Página **Metodologia** do site (`frontend/src/Metodologia.tsx`, rota `#/metodologia`):
  indicadores, ranking, auditoria e fontes.
