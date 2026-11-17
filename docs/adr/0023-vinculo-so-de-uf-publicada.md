# ADR-0023: Vínculo de emenda só com autor de UF publicada

- **Status:** Aceito
- **Data:** 2026-11-17
- **Decidido em:** 2026-11-17 (Fabio: "Regra (1): vínculo só quando a UF do autor está liberada")
- **Autor:** sessão principal
- **Decisor:** Fabio

## Contexto

O vínculo entre emenda e parlamentar segue o ADR-0013. Desde o PR #75, as UFs das emendas
vêm do Secret `RASTRO_POL_EMENDAS_UFS`, para o Fabio acrescentar uma UF por vez, do Sul para
o Norte. A ideia é coletar a UF, conferir o portão de políticos e só então liberar a
publicação (`RASTRO_POL_UFS_LIBERADAS`, T-016).

O problema: com uma UF na coleta e ainda não liberada, as emendas dos parlamentares dela para
municípios publicados (SP, SC) passavam a ter vínculo. A página desses parlamentares não é
exportada, e a verificação antes de publicar ("autores de emendas nos municípios sem
página") barraria o site inteiro.

Caso real (arquivo do Portal de 13/11/2026): emenda de 2024 de Helio Lopes (RJ) para São
Paulo. Deputados de PE, PA, RJ e BA têm emendas de 2024 em diante para municípios de SP.
Nenhum parlamentar do RS da legislatura 57 tem, nesse período, emenda para município de SP
ou de SC.

Alternativa descartada: exigir também a UF do município liberada. Em 17/11/2026 isso tiraria
o vínculo de 1.672 das 3.148 emendas ligadas nas páginas de SP e SC: as sem município
("MÚLTIPLO", "Nacional", "Exterior") e 13 com destino em outras UFs.

## Decisão

1. O vínculo emenda → parlamentar só é gravado quando a UF do parlamentar está publicada:
   SP (UF da exportação) ou uma UF de `RASTRO_POL_UFS_LIBERADAS`
   (`politicos/vinculo.py`, regra 5).
2. As exceções aprovadas (`excecoes_emendas.toml`) seguem a mesma regra.
   - A linha da exceção continua no recorte do arquivo, sem vínculo.
   - O portão de uma UF ainda não liberada confere só que a linha existe. Depois da
     liberação, confere o vínculo.
3. A coleta de emendas pela API não consulta UF não liberada.
4. O destino da emenda aparece como texto na página do parlamentar, sem link para o
   município (condição do Fabio, 17/11/2026).

## Consequências

- **Mais fácil:**
  - uma UF pode ser coletada e conferida no portão sem afetar o site;
  - as páginas de SP e SC não mudam.
- **Mais difícil:** os links das emendas de uma UF só aparecem na primeira coleta depois da
  liberação, ou seja, um dia depois.
- **Testes:** `tests/test_vinculo_ufs.py` e
  `test_excecao_de_uf_nao_liberada_entra_no_arquivo_sem_vinculo`, só com respostas reais.

## Como revisitar

Se o portão passar a decidir a publicação sem a lista de UFs liberadas, a regra deve seguir
o mesmo critério da exportação.
