# Painel analítico (BI) de parlamentares e governantes

Painel privado no claude.ai (Artifact do tipo Dashboard):
https://claude.ai/artifact/JdJpWjfR2ZBAhVXMCxUDcB

- `gerar_bases.py` transforma a exportação publicada no branch `gh-pages`
  (`dados/`) nas tabelas de fatos que o painel lê: atividade parlamentar por ano,
  emendas, cota por categoria e eleitos do TSE, todas com a dimensão UF.
- Uma rotina semanal do Claude Code (claude.ai, Routines) baixa o `gh-pages`, roda o
  script e, quando a exportação é mais nova que a do painel, troca os arquivos dele.
- Nada aqui altera o site, a API, o banco ou a metodologia. Fica fora do `main`
  (congelamento até 25/10/2026, ADR-0019).

Rodar à mão:

```sh
git fetch origin gh-pages --depth 1
mkdir -p /tmp/gh /tmp/bases && git archive FETCH_HEAD dados | tar -x -C /tmp/gh
python3 -I ferramentas/painel-bi/gerar_bases.py /tmp/gh/dados /tmp/bases
```
