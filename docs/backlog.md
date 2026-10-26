# Backlog — Rastro Público

> Atualizado em 2026-10-16 (antes: 2026-10-10). Ordem aprovada pelo Fabio em
> 2026-10-08. Nenhuma implementação começa até o Fabio liberar a tarefa. Prioridade: P1 (agora), P2 (próximo), P3 (depois).

## Aguardando aprovação do Fabio
- [ ] Lançamento: tirar o site da prévia (`RASTRO_PREVIA` padrão `0` em `backend/scripts/coleta_sp.sh`) — depende de T-003

## P1
- [x] T-004 Registrar o resultado do usuário só de leitura da auditoria em "Riscos aceitos" (`docs/deploy-replit.md`, passo 7) — `lexicon` — feito em 10/10/2026: usuário criado e auditoria testada

## P2
- [ ] T-006 Atualizar documentação desatualizada: o README diz que `/api/bruto/{sha256}` está "em implementação" (já existe desde `093a6a1`); "Próximas etapas" do módulo de políticos ainda lista "decidir e carregar os eleitos de 2026", já publicados — `lexicon`
- [ ] T-007 Transferências especiais: ligar ao município que recebeu pelo arquivo de favorecidos do Portal — `keystone` (ADR de cruzamento) → `node-runner` — regra de cruzamento exige aprovação
- [ ] T-008 Testes do frontend: hoje o CI só compila (`tsc -b` + `vite build`) — `keystone` (ADR da ferramenta) → `scalpel`

## P3: fontes novas (cada uma exige ADR e aprovação para publicar)
- [ ] T-009 Assembleia Legislativa de SP (ALESP)
- [ ] T-010 Câmaras municipais (SAPL)
- [ ] T-011 LexML: normas e proposições
- [ ] T-012 Análise de matérias estranhas ao objeto das proposições
- [ ] T-013 Doadores de campanha (TSE, prestação de contas)
- [ ] T-014 Expandir além de SP — **em andamento** (ADR-0020, aceito em 2026-10-09). Em 2026-10-10, a parte fiscal de 11 UFs passou no portão e está no site (AC, AL, AM, AP, DF, ES, MS, RJ, RO, RR, SE); as demais seguem nas execuções diárias.
- [x] T-015 Portão de qualidade dos políticos por UF (`ufs.{UF}.politicos` no manifesto) — sessão de políticos — PR #55, aprovado pelo Fabio, mesclado em 2026-10-15
- [ ] T-016 Publicar os políticos das UFs além de SP — **aguardando aprovação do Fabio** (publicação de dado novo). PR #56 em rascunho até depois de 25/10/2026; antes do merge, o relatório de SC com dados de produção passa pelo Fabio
- [ ] T-017 DF: onde ficam os representantes e as emendas de Brasília — **aguardando decisão do Fabio, depois de 25/10/2026** (mudança de formato). O DF não tem município no SICONFI, então a exportação não grava `municipios/5300108.json`. Com o DF liberado, sairiam as páginas dos políticos e os eleitos, mas "Quem representa você" não teria Brasília. Opções: (a) arquivo de Brasília só com representantes e emendas; (b) essas seções na página do DF. **Até a decisão, o DF não entra em `RASTRO_POL_UFS_LIBERADAS`** (Fabio, 16/10/2026) — sessão de políticos

## Pronto (antes do squad; ver o git log e os READMEs)
- [x] Coleta SICONFI (RREO, RGF, extrato), IBGE e lote retomável
- [x] Arquivo bruto por SHA-256, redação LGPD e armazenamento enxuto
- [x] Indicadores fiscais e Ranking Fiscal v1.0
- [x] Políticos de SP: Câmara, Senado, cota, TSE 2022/2024/2026, emendas com vínculo confirmado, linha do tempo do mandato
- [x] Site estático formato 3 com exportação incremental, publicação verificada e reversão
- [x] API de auditoria separada
- [x] Trava de coleta única, tolerância a falha de fonte e modo prévia
- [x] Workflow de coleta no Actions (fase de teste, só manual)
- [x] T-000 Migração para o fluxo do squad — PR #25
- [x] T-001 Teste da coleta no Actions: o Neon aceita conexão externa e as fontes respondem, mas a coleta foi cerca de 4,5 vezes mais lenta e não terminou em 5h50 (ADR-0016)
- [x] ADR-0016 Coleta oficial no Replit; Actions só manual; aviso de código atrasado no início da coleta (T-002 cancelada) — 2026-10-09
- [x] T-005 Chave do Portal da Transparência: era posta num cliente HTTP descartado, e as consultas saíam sem o cabeçalho `chave-api-dados` ("Chave de API não informada"); corrigido com teste pelo caminho da coleta — 2026-10-09. Falta conferir na próxima coleta que `pol-emendas` pela API deixa de falhar. As emendas da API não aparecem no site enquanto houver as do arquivo (`api/politicos.py`).
- [x] T-003 Ranking Fiscal v1.1 (D1 a D7): ADR-0017, `metodologia_v1_1.toml`, código, testes e página Metodologia — PR #24, aprovado pelo Fabio em 2026-10-09
- [x] Políticos em várias UFs: passada única da Câmara, reaproveitamento, limite de tempo, partido longo (migração 0020) e DF sem eleição municipal — PR #40, aprovado pelo Fabio em 2026-10-09, mesclado em 2026-10-10
- [x] CI: PostgreSQL 16 pelo espelho oficial no ECR Public, sem o limite de downloads do Docker Hub — PR #41, aprovado pelo Fabio em 2026-10-10
- [x] Busca nacional: municípios de SP continuam na busca com a situação "arquivos de sempre" enquanto SP não passa no portão — PR #42, 2026-10-10
- [x] Cargo deputado(a) distrital para os eleitos do DF (cargo 8 do TSE; 24 em 2022 e 24 em 2026) — PR #43, aprovado pelo Fabio em 2026-10-10
