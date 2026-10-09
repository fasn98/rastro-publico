# ADR-0006: Toda resposta HTTP das fontes é arquivada antes do processamento, endereçada pelo SHA-256

- **Status:** Aceito retroativo
- **Data:** 2026-10-08
- **Decidido em:** 2026-10-06 (commits `5a84833` e `093a6a1`)
- **Autor:** registro retroativo na migração para o squad
- **Decisor:** Fabio

## Contexto

Princípio do portal: todo número exibido precisa ser auditável até a resposta original da
fonte.

## Opções consideradas

Não registradas na época.

## Decisão

`backend/src/rastro/coletores/arquivo.py`: todo coletor que usa `novo_cliente()` grava cada
resposta (inclusive erros e novas tentativas) em transação própria, **antes** de processar.
`resposta_bruta` guarda os metadados (URL, status, data, SHA-256, coleta); `payload_bruto`
guarda os bytes com gzip, deduplicados pelo SHA-256. Cada linha de dado tem `resposta_id`.
O site aponta para `/api/bruto/{sha256}` com a data do primeiro recebimento.

## Consequências

- Mais fácil: qualquer número tem link para a resposta bruta; `rastro verificar-respostas`
  confere a integridade; o armazenamento enxuto reconstrói dados do bruto (ADR-0008).
- Mais difícil: o banco cresce com o bruto (~0,35 GB para SP em 2022–2025, README).
- Proibido: coletor que faça HTTP sem `novo_cliente()`; dado publicado sem `resposta_id`.

## Como revisitar

Se o custo do armazenamento do bruto passar a limitar a expansão para o Brasil.
