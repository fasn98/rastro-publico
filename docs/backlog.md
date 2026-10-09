# Backlog — Rastro Público

> Atualizado em 2026-10-08, na migração para o fluxo do squad. Ordem aprovada pelo Fabio em
> 2026-10-08. Nenhuma implementação começa até o Fabio liberar a tarefa. Prioridade: P1 (agora), P2 (próximo), P3 (depois).

## Aguardando aprovação do Fabio
- [ ] T-000 Migração para o fluxo do squad (só documentação e `.gitignore`) — branch `chore/squad-setup`, PR aberto
- [ ] ADR-0016 Coleta agendada: GitHub Actions ou Replit — `docs/adr/0016-onde-roda-a-coleta-agendada.md` — depende de T-001
- [ ] Lançamento: tirar o site da prévia (`RASTRO_PREVIA` padrão `0` em `backend/scripts/coleta_sp.sh`) — depende de T-003

## P1
- [ ] T-001 Conferir o teste da coleta no Actions (run `37858037605`, em andamento em 2026-10-08, acompanhada por outra sessão; o Fabio traz o resultado): resultado, duração, se o Neon aceita conexão externa e se as fontes respondem aos IPs do GitHub; depois, o teste publicando (`docs/coleta-actions.md`, passos 2 e 3) — `node-runner` — a execução com publicação é do Fabio
- [ ] T-002 Troca definitiva da coleta: `schedule` no workflow e `docs/deploy-replit.md` atualizado; o Fabio desliga o Scheduled do Replit e revoga o token fine-grained — `node-runner` + `lexicon` — depende de ADR-0016 aceito
- [ ] T-004 Registrar o resultado do usuário só de leitura da auditoria em "Riscos aceitos" (`docs/deploy-replit.md`, passo 7) — `lexicon` — **pendente com o Fabio**: o resultado ainda não é conhecido

## P2
- [ ] T-005 Chave da API do Portal da Transparência: validar `RASTRO_TRANSPARENCIA_CHAVE` (recusada em 06/10) e ligar o coletor `emendas-api` à coleta — `node-runner` — depende de chave válida (Fabio); publicar exige aprovação
- [ ] T-006 Atualizar documentação desatualizada: o README diz que `/api/bruto/{sha256}` está "em implementação" (já existe desde `093a6a1`); "Próximas etapas" do módulo de políticos ainda lista "decidir e carregar os eleitos de 2026", já publicados — `lexicon`
- [ ] T-007 Transferências especiais: ligar ao município que recebeu pelo arquivo de favorecidos do Portal — `keystone` (ADR de cruzamento) → `node-runner` — regra de cruzamento exige aprovação
- [ ] T-008 Testes do frontend: hoje o CI só compila (`tsc -b` + `vite build`) — `keystone` (ADR da ferramenta) → `scalpel`

## P3: fontes novas (cada uma exige ADR e aprovação para publicar)
- [ ] T-009 Assembleia Legislativa de SP (ALESP)
- [ ] T-010 Câmaras municipais (SAPL)
- [ ] T-011 LexML: normas e proposições
- [ ] T-012 Análise de matérias estranhas ao objeto das proposições
- [ ] T-013 Doadores de campanha (TSE, prestação de contas)
- [ ] T-014 Expandir além de SP (a projeção para o Brasil está no README)

## Pronto (antes do squad; ver o git log e os READMEs)
- [x] Coleta SICONFI (RREO, RGF, extrato), IBGE e lote retomável
- [x] Arquivo bruto por SHA-256, redação LGPD e armazenamento enxuto
- [x] Indicadores fiscais e Ranking Fiscal v1.0
- [x] Políticos de SP: Câmara, Senado, cota, TSE 2022/2024/2026, emendas com vínculo confirmado, linha do tempo do mandato
- [x] Site estático formato 3 com exportação incremental, publicação verificada e reversão
- [x] API de auditoria separada
- [x] Trava de coleta única, tolerância a falha de fonte e modo prévia
- [x] Workflow de coleta no Actions (fase de teste, só manual)
- [x] T-003 Ranking Fiscal v1.1 (D1 a D7): ADR-0017, `metodologia_v1_1.toml`, código, testes e página Metodologia — PR #24, aprovado pelo Fabio em 2026-10-09
