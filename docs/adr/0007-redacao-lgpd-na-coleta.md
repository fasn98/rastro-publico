# ADR-0007: Os dados pessoais são retirados na coleta, antes de gravar, inclusive do arquivo bruto

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commit `3a57255`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

Fontes como o TSE e a cota parlamentar trazem CPF, data de nascimento, título de eleitor,
e-mail e outros dados pessoais. A LGPD impede guardá-los, mas o ADR-0006 exige guardar a
resposta original.

## Opções consideradas

Não registradas na época.

## Decisão

Modo de redação no arquivo bruto (`coletores/redacao.py`, `politicos/lgpd.py`): grava a
versão sem os campos pessoais, com o SHA-256 do original, o da versão gravada e a lista de
campos removidos. A auditoria baixa a URL pública de novo e compara com `sha256_original`.
Os campos removidos por fonte estão em `backend/src/rastro/politicos/README.md`.

## Consequências

- Mais fácil: nenhuma tabela nem payload tem dado pessoal; testes varrem tudo procurando
  e-mails, nomes de campos pessoais e marcadores.
- Mais difícil: a prova de origem de um payload redigido depende de a fonte continuar
  servindo o mesmo arquivo.
- Proibido: gravar CPF, data de nascimento, título de eleitor, e-mail ou endereço de
  pessoa física em qualquer tabela ou no bruto; fixture com esses dados.

## Como revisitar

Se uma fonte nova trouxer dado pessoal que não dê para separar do dado público por campo.
