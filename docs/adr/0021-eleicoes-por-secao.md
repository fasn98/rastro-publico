# ADR-0021: Eleições 2026, dados por seção a partir dos arquivos oficiais de urna

- **Status:** Proposto
- **Data:** 2026-10-26
- **Autor:** sessão de políticos
- **Decisor:** Fabio

## Contexto

O Fabio pediu, em 26/10/2026, a exploração de um módulo "Eleições 2026: dados por seção",
só com dados oficiais do TSE. Para cada seção: abertura, encerramento, votos computados por
hora, comparecimento, abstenção, brancos, nulos e votos por candidato. Nada é publicado
nesta fase.

No 2º turno de 25/10/2026, uma liminar do STF (RCL 101.673/BA) prorrogou o recebimento dos
votos até as 19h de Brasília. Um esclarecimento posterior restringiu a prorrogação às
urnas ainda não encerradas.

Fontes oficiais, medidas em 26/10/2026:

- **Arquivos de cada urna**, no site de resultados: BU em ASN.1 e log em zip com
  `logd.dat`. Estão em
  `resultados.tse.jus.br/oficial/ele2026/arquivo-urna/<pleito>/...`, com o pleito 3220 no
  1º turno e 3221 no 2º.
- **Os mesmos arquivos em pacote por UF**, nos Dados Abertos: o pacote
  `bu_imgbu_logjez_rdv_vscmr_2026_<turno>_<UF>.zip` (CC-BY) e o BU na web
  (`bweb_<turno>_<UF>_*.zip`, CC-BY).

Protótipo com Blumenau/SC no 2º turno: a soma dos 754 BUs confere com a totalização
oficial do TSE em aptos, comparecimento, abstenção, brancos, nulos e votos de cada
candidato. Os eventos "voto computado" do log conferem com o comparecimento do BU nas 754
seções.

**O log da urna contém o número do título de eleitor de mesários.** Isso aparece nas
linhas de registro de mesário e no título digitado no encerramento. O log também contém o
identificador do usuário que gerou a mídia.

## Decisão (proposta)

1. **Log bruto: regra permanente do módulo.** O log da urna (`log.jez` / `logd.dat`) nunca
   é armazenado nem publicado: nem no banco, nem no arquivo bruto (`payload_bruto`), nem no
   site, nem em fixtures de teste. O log é lido em memória na coleta, e só ficam:
   - as métricas extraídas: horários e contagens de eventos, sem nenhum identificador de
     pessoa;
   - a URL e o SHA-256 do arquivo oficial do TSE, para quem quiser auditar no próprio TSE.

   A auditoria deste módulo aponta para o arquivo oficial, e não para `/api/bruto/{sha256}`.
   Isso é uma exceção à regra geral de auditoria do projeto, válida só para o log da urna.
2. **Escala nacional pelos arquivos em lote.** A coleta nacional usa os pacotes por UF dos
   Dados Abertos do TSE, e não a coleta seção por seção no site de resultados:
   - o site de resultados limitou o protótipo com "429 Too Many Requests" usando 8
     conexões;
   - o pacote do 1º turno tem 95 GB.

   O acesso seção por seção fica só para protótipo e conferência pontual.
3. **Sem atribuição de causa.** Votos computados depois das 17h aparecem sempre ao lado da
   mesma métrica no 1º turno, nas mesmas seções. A regra legal da fila e os documentos
   oficiais da prorrogação vão com link e sem resumo próprio. Nenhuma frase atribui causa,
   e não há projeção do "que teria acontecido".
4. **Horário de Brasília.** O relógio da urna registra a hora local, e a votação de 2026
   abriu às 8h de Brasília em todo o país. As métricas convertem a hora local para a de
   Brasília, e o método de conversão fica documentado.
5. **Publicação só depois de parecer jurídico** e de aprovação explícita do Fabio, em local
   a definir. A proposta é um site separado do gh-pages atual.

## Consequências

- Não é possível reprocessar um log a partir do nosso arquivo. Para isso, baixa-se de novo
  o arquivo oficial, e o SHA-256 guardado confirma que é o mesmo.
- Os testes do módulo usam BUs reais, que não têm dado pessoal. Para o log, as fixtures
  usam só trechos sem linhas de mesário, ou as métricas já extraídas. Isso precisa de
  aprovação, porque um trecho do log continua sendo um recorte da fonte.
- A especificação ASN.1 do BU não pôde ser baixada deste ambiente: a página do TSE bloqueia
  acesso automatizado. O mapeamento foi validado contra os números oficiais e precisa ser
  conferido com a especificação antes de produção.
