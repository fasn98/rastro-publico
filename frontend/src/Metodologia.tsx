import { useEffect, useState } from "react";
import { INDICADORES_RANKING, obterMetodologia, type Metodologia as Met, type RegraIndicador } from "./api";
import { obterManifesto } from "./dados";

const n = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });

const FORMULA: Record<string, { formula: string; fonte: string }> = {
  autonomia: {
    formula:
      "(receita tributária própria + cotas-parte de ICMS, IPVA e ITR) ÷ (despesa empenhada nas funções Administração + Legislativa)",
    fonte:
      "RREO Anexo 1, ReceitaTributaria, coluna “Até o Bimestre (c)”; RREO Anexo 3, RREO3CotaParteDoICMS/IPVA/ITR, “TOTAL (ÚLTIMOS 12 MESES)”; RREO Anexo 2, RREO2TotalDespesas nas linhas “Administração” e “Legislativa” (exceto intraorçamentárias), “DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)”. 6º bimestre.",
  },
  pessoal: {
    formula: "Despesa total com pessoal do Executivo ÷ RCL ajustada, em %, como declarada",
    fonte:
      "RGF Anexo 1 do Poder Executivo, DespesaComPessoalTotal, coluna “% sobre a RCL Ajustada”; limite máximo da linha LimiteMaximoDespesaComPessoalTotal. Último período do ano.",
  },
  liquidez: {
    formula:
      "Disponibilidade de caixa líquida após a inscrição de restos a pagar não processados, recursos NÃO vinculados ÷ RCL, em %",
    fonte:
      "RGF Anexo 5 do Executivo, linha “TOTAL DOS RECURSOS NÃO VINCULADOS (I)”, coluna DisponibilidadeDeCaixaLiquidaAposRP (i); RCL do RGF Anexo 2. 3º quadrimestre ou 2º semestre. Quando a API não traz a linha (I) (ela omite linhas com valor zero), (I) = (IV) − (II) − (III), pelo total do próprio relatório.",
  },
  investimento: {
    formula: "Investimentos liquidados (exceto intraorçamentários) ÷ receita total realizada, em %",
    fonte:
      "RREO Anexo 1, Investimentos, “DESPESAS LIQUIDADAS ATÉ O BIMESTRE (h)”; TotalReceitas, “Até o Bimestre (c)”. 6º bimestre.",
  },
  transparencia: {
    formula:
      "Média de 4 blocos de peso igual: RREO (bimestres disponíveis ÷ 6), RGF do Executivo e RGF do Legislativo (períodos ÷ 3 quadrimestres ou 2 semestres) e DCA (entregue = 1)",
    fonte:
      "Extrato de entregas do SICONFI + presença das linhas do relatório na API de dados abertos.",
  },
};

function Regra({ chave, r }: { chave: string; r: RegraIndicador }) {
  const sentido = r.pior > r.melhor ? "menor é melhor" : "maior é melhor";
  const faixa = chave === "transparencia"
    ? r.multiplicador
      ? "o índice já vai de 0 a 1 (0% a 100% dos relatórios esperados) e multiplica a média dos indicadores fiscais"
      : "o índice já vai de 0 a 1 (0% a 100% dos relatórios esperados) e é usado diretamente"
    : r.relativo_ao_limite_maximo
    ? `nota 0 com ${n(r.pior * 100)}% do limite máximo declarado; nota 10 até ${n(r.melhor * 100)}% dele (em municípios, limite de 54%: ${n(r.pior * 54)}% e ${n(r.melhor * 54)}% da RCL)`
    : `nota 0 com ${n(r.pior)}${r.unidade.startsWith("%") ? "%" : ""} ou ${r.pior > r.melhor ? "mais" : "menos"}; nota 10 com ${n(r.melhor)}${r.unidade.startsWith("%") ? "%" : ""} ou ${r.pior > r.melhor ? "menos" : "mais"}`;
  return (
    <article className="regra">
      <h3>
        {r.nome} <span className="sub">{r.multiplicador ? "multiplicador" : `peso ${r.peso}`}</span>
      </h3>
      <p>
        <strong>Fórmula:</strong> {FORMULA[chave].formula}
      </p>
      <p className="sub">
        <strong>De onde vem:</strong> {FORMULA[chave].fonte}
      </p>
      <p>
        <strong>Normalização:</strong> linear, {r.relativo_ao_limite_maximo ? "menor é melhor" : sentido}: {faixa}.
        {r.penaliza_ausencia && " Ausência de relatório conta como 0."}
      </p>
    </article>
  );
}

export default function Metodologia() {
  const [met, setMet] = useState<Met | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [prefeitos, setPrefeitos] = useState(false);
  useEffect(() => {
    obterMetodologia().then(setMet).catch((e: Error) => setErro(e.message));
    // a explicação da coluna de prefeitos só aparece quando ela está publicada (ADR-0018)
    obterManifesto()
      .then((m) => setPrefeitos(!!m?.travas?.pol_publicar_gestoes))
      .catch(() => setPrefeitos(false));
  }, []);
  if (erro) return <p className="erro">{erro}</p>;
  if (!met) return <p className="sub">Carregando…</p>;

  return (
    <article className="metodologia">
      <h2>Metodologia do Ranking Fiscal</h2>
      <p className="sub">
        Versão {met.versao} · arquivo de regras <code>metodologia_v1_1.toml</code> (hash {met.hash}) ·
        exercícios {met.exercicios.join(", ")}
      </p>

      <h3>Princípios</h3>
      <ul>
        <li>
          Usamos o que o ente <strong>declara</strong> ao Tesouro Nacional (SICONFI). Percentuais e
          limites vêm prontos do relatório; só calculamos o que o relatório não traz.
        </li>
        <li>
          Só entram dados anuais: RREO do 6º bimestre e RGF do último período do ano.
        </li>
        <li>
          A nota mede os números declarados; <strong>não é auditoria</strong> nem substitui a análise
          do Tribunal de Contas.
        </li>
      </ul>

      <h3>Indicadores, fórmulas e normalização</h3>
      <p>
        São 4 indicadores fiscais (autonomia, gastos com pessoal, liquidez e investimento) e a
        transparência. Cada um é convertido para uma nota de 0 a 1 em cada ano (exibida de 0 a 10)
        por normalização linear entre um valor “pior” (nota 0) e um “melhor” (nota 1), com limites
        em 0 e 1.
      </p>
      {INDICADORES_RANKING.map((k) => (
        <Regra key={k} chave={k} r={met.indicadores[k]} />
      ))}

      <h3>Como a nota final é formada</h3>
      <ol>
        <li>
          Para cada indicador, média das notas anuais dos últimos {met.janela_exercicios} exercícios
          ({met.exercicios.join(", ")}) que têm dado.
        </li>
        <li>
          Média ponderada dos 4 indicadores fiscais com dado (pesos iguais nesta versão). Indicador
          sem nenhum ano com dado é <strong>não reportado</strong>: sai da média, os pesos dos demais
          são redistribuídos e a nota informa quantos faltaram.
        </li>
        <li>
          Nota final = essa média × o índice de transparência. Quem entregou todos os relatórios
          esperados (índice 1) fica com a média fiscal; quem deixou de entregar perde na mesma
          proporção. A transparência é a única que penaliza ausência: ano coletado sem relatório
          vale 0.
        </li>
        <li>
          Com menos de {met.minimo_indicadores_fiscais} dos 4 indicadores fiscais, o município fica{" "}
          <strong>sem nota</strong> (cinza no mapa), para que a transparência sozinha não gere uma
          nota.
        </li>
        <li>
          Posições por competição (empates dividem a posição), no ranking geral e por faixa
          populacional: {met.faixas.map((f) => f.nome).join("; ")}. População: estimativa mais
          recente do IBGE (SIDRA, tabela 6579); sem ela, o município fica sem faixa.
        </li>
      </ol>

      <h3>Escolhas feitas e alternativas descartadas</h3>
      <table className="tabela-escolhas">
        <thead>
          <tr>
            <th>Indicador</th>
            <th>Adotado</th>
            <th>Descartado</th>
            <th>Por quê</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Autonomia</td>
            <td>Receita tributária + cotas-parte de ICMS, IPVA e ITR</td>
            <td>Só a receita tributária própria</td>
            <td>
              As cotas-parte refletem a atividade econômica do próprio município. Usamos sempre os
              totais declarados, não a soma de partes. Como a razão não tem teto, acima de{" "}
              {n(met.indicadores.autonomia.melhor)} a nota é máxima: é o percentil 95 da coleta
              completa de SP (2023–2025, 1.931 município-anos: 6,94). Com o teto anterior (10), só
              0,9% dos casos chegavam à nota máxima.
            </td>
          </tr>
          <tr>
            <td>Liquidez</td>
            <td>Caixa líquido dos recursos não vinculados (I), só do Executivo</td>
            <td>Não vinculados + vinculados (I + II)</td>
            <td>
              Recurso vinculado não pode pagar qualquer obrigação. (I + II) aparece na página do
              município como contexto, fora da nota.
            </td>
          </tr>
          <tr>
            <td>Investimento</td>
            <td>Investimentos liquidados</td>
            <td>Investimentos empenhados</td>
            <td>
              Liquidado = obra ou bem efetivamente entregue. Empenhado e restos a pagar não
              processados aparecem como contexto.
            </td>
          </tr>
          <tr>
            <td>Transparência</td>
            <td>4 blocos (RREO, RGF Executivo, RGF Legislativo, DCA), como multiplicador da média fiscal</td>
            <td>Peso 1 ou 0,5 na média; incluir a MSC mensal; medir pontualidade</td>
            <td>
              Na coleta de SP (2023–2025), o índice vale 1 em 99,3% dos casos: com peso na média, ele
              somava quase o mesmo a todas as notas. A MSC não muda nada (todos os 645 municípios
              entregaram as 12 mensais e a de encerramento). A data do extrato muda quando o ente
              retifica, então a pontualidade não é medida com segurança, e retificações não
              penalizam.
            </td>
          </tr>
        </tbody>
      </table>

      <h3>Fora da nota, mas no painel do município</h3>
      <p>
        Dívida consolidada líquida, resultado orçamentário e execução da receita e da despesa seguem
        visíveis na página de cada município, mas não entram nesta versão do ranking.
      </p>
      <p>
        Valores por habitante (receita local e investimento liquidado) usam a população oficial do
        IBGE mais recente até o ano do exercício: estimativas da tabela 6579 para 2024 e 2025 e o
        Censo 2022 (tabela 4709) para 2023, porque o IBGE não publicou estimativa para 2022 nem
        2023. Ficam fora da nota: os 4 indicadores já são razões, que não dependem do tamanho do
        município.
      </p>

      <h3>O que mudou na versão 1.1 (aprovada em 09/10/2026)</h3>
      <ul>
        <li>
          <strong>Relatório da Prefeitura:</strong> consórcios públicos podem entregar RREO e RGF com o
          código do município-sede. Os indicadores usam sempre o relatório da Prefeitura. Na v1.0, o
          de um consórcio podia ser lido no lugar dele (em SP, só Votuporanga).
        </li>
        <li>
          <strong>Linha omitida no RGF Anexo 5:</strong> (I) = (IV) − (II) − (III) quando a API não
          traz a linha dos recursos não vinculados.
        </li>
        <li>
          <strong>Teto da autonomia:</strong> de 10 para 7.
        </li>
        <li>
          <strong>Transparência:</strong> deixa de ser um 5º indicador com peso 1 e passa a multiplicar
          a média fiscal. Por isso as notas da v1.1 são, em geral, mais baixas que as da v1.0: sai um
          componente que valia 10 para quase todos. Não é piora dos municípios.
        </li>
        <li>
          <strong>Faixas populacionais</strong> pela estimativa do IBGE (nenhum município de SP mudou
          de faixa) e <strong>valores por habitante</strong> como contexto.
        </li>
        <li>
          <strong>Gasto com pessoal acima de 100% da RCL:</strong> fica como declarado, com um aviso
          de possível erro de preenchimento na fonte.
        </li>
      </ul>
      <p className="sub">
        A v1.0 continua registrada no repositório (<code>metodologia_v1.toml</code>), com a proposta e a
        simulação da mudança em <code>docs/metodologia-v1.1/</code>.
      </p>

      <h3>A nota e as gestões municipais</h3>
      <p>
        A nota é a média de vários exercícios ({met.exercicios.join(", ")}) e pode refletir mais de
        uma gestão: o mandato municipal muda em 1º de janeiro do ano seguinte à eleição, e uma
        eleição suplementar pode trocar o prefeito no meio do mandato. Os indicadores também
        dependem de fatores fora do controle do prefeito, como transferências de outros entes, a
        economia local e compromissos assumidos por gestões anteriores. A nota descreve as contas
        do município, não o desempenho de uma pessoa ou de um partido.
      </p>
      {prefeitos && (
        <>
          <p>
            A coluna “Prefeitos eleitos no período da nota” e a página de cada município mostram o
            prefeito e o vice <strong>eleitos para o mandato</strong> de cada exercício, como estão
            no arquivo atual de candidatos do TSE (eleições de 2020 e 2024, com as suplementares).
            O TSE registra quem foi eleito, não quem exerceu o cargo: renúncia, morte, afastamento
            e interinidade não aparecem. Em São Paulo, por exemplo, o arquivo registra Bruno Covas
            (PSDB) como eleito para 2021–2024; o vice eleito, Ricardo Nunes (MDB), assumiu o cargo
            em maio de 2021, após a morte do titular (fonte:{" "}
            <a
              href="https://www.saopaulo.sp.leg.br/blog/camara-de-sp-empossa-o-prefeito-ricardo-nunes/"
              target="_blank"
              rel="noreferrer"
            >
              Câmara Municipal de São Paulo, 01/01/2025
            </a>
            ).
          </p>
          <p>
            Quando uma eleição é anulada, o TSE reescreve o resultado e ela fica sem eleito. Nesses
            casos o site mostra “sem eleito válido no arquivo atual do TSE” e, a partir do ano da
            eleição suplementar, quem ela elegeu. O partido é o da eleição, como registrado no TSE,
            e aparece só ao lado do nome: o site não agrupa, filtra, colore nem compara partidos.
          </p>
        </>
      )}

      <h3>Limitações conhecidas</h3>
      <ul>
        <li>Os dados são declarados pelos entes e podem ser retificados depois: a nota muda quando os relatórios mudam.</li>
        <li>
          Cada coleta relê os relatórios do exercício corrente e do anterior. Os exercícios mais
          antigos são relidos em rodízio de 4 semanas (um quarto dos entes por semana). Por isso,
          uma retificação de exercício antigo pode levar até 4 semanas para aparecer no site.
        </li>
        <li>A API omite linhas com valor zero; nesses casos usamos o total declarado ou tratamos a parcela ausente como zero.</li>
        <li>A liquidez considera só o Executivo; o caixa da Câmara não entra.</li>
        <li>Os limites das normalizações (“pior” e “melhor”) são escolhas desta versão, registradas no arquivo de regras.</li>
        <li>A transparência mede presença dos relatórios, não pontualidade nem qualidade: em SP, 99,3% dos casos têm 100%.</li>
        <li>Municípios ainda não coletados aparecem sem nota.</li>
      </ul>

      <h3>Auditoria: de cada número até a resposta original</h3>
      <p>
        Toda resposta recebida das APIs oficiais é guardada antes de qualquer processamento,
        inclusive respostas de erro: os bytes exatamente como chegaram, a URL completa com
        parâmetros, a data e hora e o SHA-256 dos bytes. Cada valor gravado (cada célula do
        RREO/RGF, cada município, cada entrega) aponta para a resposta de onde saiu.
      </p>
      <ul>
        <li>
          <code>GET /api/respostas/{"{id}"}/bruto</code>: os bytes originais. O cabeçalho{" "}
          <code>X-Rastro-SHA256</code> traz o hash, e quem baixar pode conferir com{" "}
          <code>sha256sum</code>.
        </li>
        <li>
          <code>GET /api/bruto/{"{sha256}"}</code>: os mesmos bytes, endereçados pelo próprio SHA-256. O
          endereço não muda entre publicações e o conteúdo nunca muda. Nas respostas com dados
          pessoais, devolve a versão gravada, com o hash do original em{" "}
          <code>X-Rastro-SHA256-Original</code>.
        </li>
        <li>
          <code>GET /api/respostas/{"{id}"}</code>: URL, data e verificação de integridade feita na hora.
        </li>
        <li>
          <code>GET /api/demonstrativos/{"{id}"}/respostas</code>: as respostas (páginas) que formam um
          relatório; <code>/api/demonstrativos/{"{id}"}/contas</code> traz o <code>resposta_id</code> de
          cada valor.
        </li>
      </ul>

      <h4>Fontes com dados pessoais (LGPD)</h4>
      <p>
        Algumas fontes devolvem dados pessoais que o portal não pode guardar: CPF, data de
        nascimento, título de eleitor, e-mail (por exemplo, os arquivos de candidatos do TSE e as
        listas de parlamentares da Câmara e do Senado, que trazem e-mails de gabinete). Nesses
        casos o original <strong>não</strong> é guardado. Grava-se só a versão sem esses campos
        (no TSE, também só as linhas de SP), junto com o SHA-256 do original, o SHA-256 da versão
        gravada e a lista de campos removidos.
      </p>
      <p>
        A conferência, nesses casos, se faz <strong>baixando de novo a URL pública da fonte</strong>{" "}
        (cabeçalho <code>X-Rastro-URL-Origem</code>) e comparando o <code>sha256sum</code> do
        arquivo com o cabeçalho <code>X-Rastro-SHA256-Original</code>. Se a fonte tiver
        atualizado o arquivo depois da coleta, o hash será outro, e a data da coleta (
        <code>X-Rastro-Recebido-Em</code>) indica qual versão foi usada. Os campos retirados
        aparecem em <code>X-Rastro-Campos-Removidos</code> e em{" "}
        <code>GET /api/respostas/{"{id}"}</code>.
      </p>

      <h3>Fontes</h3>
      <ul>
        <li>
          SICONFI / Tesouro Nacional: RREO, RGF, extrato de entregas e cadastro de entes (API de
          dados abertos, apidatalake.tesouro.gov.br).
        </li>
        <li>IBGE: malha municipal (API de Malhas v3) e cadastro de municípios (API de Localidades).</li>
        <li>
          IBGE: população (API de agregados do SIDRA): estimativas anuais (tabela 6579) e Censo
          2022 (tabela 4709).
        </li>
      </ul>
    </article>
  );
}
