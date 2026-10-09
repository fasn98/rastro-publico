export type Municipio = {
  cod_ibge: number;
  nome: string;
  uf: string;
  regiao: string;
  regiao_imediata: string | null;
  regiao_intermediaria: string | null;
  // só na lista da busca (municipios.json): estimativa do IBGE, para ordenar sugestões
  populacao?: number | null;
};

export type Ente = {
  cod_ibge: number;
  nome: string;
  esfera: string;
  uf: string | null;
  capital: boolean;
  populacao: number | null;
  cnpj: string | null;
  exercicio: number;
};

export type PopulacaoIbge = {
  ano: number;
  populacao: number;
  fonte: string;
  url_fonte: string | null;
  resposta_id: number | null;
};

export type MunicipioDetalhe = Municipio & {
  populacao_ibge: PopulacaoIbge | null;
  ente_siconfi: Ente | null;
};

export type Pagina<T> = { total: number; itens: T[] };

import type { Representantes } from "./apiPoliticos";
import { expandir, lerJson, normalizar, urlDados, type Compacto } from "./dados";

/** Arquivo estático de um município: detalhe, série, nota, representantes, emendas. */
export type ArquivoMunicipio = {
  detalhe: MunicipioDetalhe;
  serie: IndicadoresAno[];
  nota: DetalheRanking | null;
  /** null fora da UF dos políticos: representantes ainda não coletados (ADR-0020) */
  representantes: {
    municipio: Representantes["municipio"];
    // seção inteira, ou referência ao arquivo de uma seção repetida entre municípios
    secoes: (Representantes["secoes"][number] | { ref: string })[];
  } | null;
  emendas: unknown;
  /** prefeitos eleitos por mandato e exercício (ADR-0018); ausente em exportações antigas */
  prefeitos?: unknown;
};

export const arquivoMunicipio = (cod: number) =>
  lerJson<ArquivoMunicipio>(`municipios/${cod}.json`);

const listaMunicipios = () => lerJson<Municipio[]>("municipios.json");

export const NOME_UF: Record<string, string> = {
  AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia", CE: "Ceará",
  DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão",
  MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso", PA: "Pará", PB: "Paraíba",
  PE: "Pernambuco", PI: "Piauí", PR: "Paraná", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte",
  RO: "Rondônia", RR: "Roraima", RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe",
  SP: "São Paulo", TO: "Tocantins",
};

const SIGLA_POR_CODIGO: Record<string, string> = {
  "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
  "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
  "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
  "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
};
/** UF de um código IBGE (os dois primeiros dígitos). */
export const ufDoCodigo = (cod: number) => SIGLA_POR_CODIGO[String(cod).slice(0, 2)] ?? "";

// "do Acre", "da Bahia", "de São Paulo": a preposição que cada nome pede
const PREPOSICAO: Record<string, string> = {
  AC: "do", AL: "de", AM: "do", AP: "do", BA: "da", CE: "do", DF: "do", ES: "do", GO: "de",
  MA: "do", MG: "de", MS: "de", MT: "de", PA: "do", PB: "da", PE: "de", PI: "do", PR: "do",
  RJ: "do", RN: "do", RO: "de", RR: "de", RS: "do", SC: "de", SE: "de", SP: "de", TO: "do",
};
/** "do Acre", "de São Paulo" (para "municípios do Acre"). */
export const daUf = (uf: string) => `${PREPOSICAO[uf] ?? "de"} ${NOME_UF[uf] ?? uf}`;

/** Item da busca nacional (busca.json, ADR-0020). */
export type ItemBusca = Municipio & {
  tipo: "municipio" | "estado" | "distrito_federal" | "ver_df" | "distrito_estadual";
};

/** Para onde leva cada item da busca. */
export const linkBusca = (b: ItemBusca) =>
  b.tipo === "municipio"
    ? `#/municipio/${b.cod_ibge}`
    : b.tipo === "distrito_estadual"
      ? `#/estado/${b.uf}/noronha`
      : `#/estado/${b.uf}`;

let busca: Promise<{ ufs: string[]; nacional: boolean; itens: ItemBusca[] }> | null = null;
/** Busca nacional; sem busca.json (exportação só de SP), a lista de municipios.json. */
const listaBusca = () =>
  (busca ??= lerJson<Compacto & { ufs: string[] }>("busca.json", true).then(async (b) =>
    b
      ? { ufs: b.ufs, nacional: true, itens: expandir<ItemBusca>(b) }
      : {
          ufs: ["SP"],
          nacional: false,
          itens: (await listaMunicipios()).map((m) => ({ ...m, tipo: "municipio" as const })),
        },
  ));

/** UFs com a parte fiscal no site (aprovadas no portão de qualidade) e se há os arquivos
 * nacionais (busca e ranking do Brasil). */
export const ufsNoSite = async () => {
  const { ufs, nacional } = await listaBusca();
  return { ufs, nacional };
};

export const ufsDisponiveis = async () =>
  [...new Set((await listaMunicipios()).map((m) => m.uf))].sort();

export async function buscarMunicipios(uf: string, nome: string): Promise<Pagina<Municipio>> {
  const termo = normalizar(nome);
  const todos = (await listaMunicipios()).filter(
    (m) => (!uf || m.uf === uf) && (!termo || normalizar(m.nome).includes(termo)),
  );
  return { total: todos.length, itens: todos.slice(0, 100) };
}

/** Sugestões para a busca: sem diferenciar acentos e maiúsculas; quem começa com o termo
 * vem primeiro, depois quem tem uma palavra começando com ele, depois quem o contém. */
export async function sugerirMunicipios(texto: string, limite = 10): Promise<ItemBusca[]> {
  const termo = normalizar(texto.trim());
  if (!termo) return [];
  const pontuados: [number, ItemBusca][] = [];
  for (const m of (await listaBusca()).itens) {
    const nome = normalizar(m.nome);
    const i = nome.indexOf(termo);
    if (i < 0) continue;
    const inicioPalavra = i === 0 || /[\s'-]/.test(nome[i - 1]);
    pontuados.push([i === 0 ? 0 : inicioPalavra ? 1 : 2, m]);
  }
  // empate: o mais populoso primeiro (estimativa do IBGE), depois a ordem alfabética
  pontuados.sort(
    (a, b) =>
      a[0] - b[0] ||
      (b[1].populacao ?? 0) - (a[1].populacao ?? 0) ||
      a[1].nome.localeCompare(b[1].nome, "pt-BR"),
  );
  return pontuados.slice(0, limite).map(([, m]) => m);
}

export const todosMunicipios = () => listaMunicipios();

/** Todos os itens da busca nacional (ou os municípios de SP, sem busca.json). */
export const todosDaBusca = async () => (await listaBusca()).itens;

export const obterMunicipio = async (cod: number) => (await arquivoMunicipio(cod)).detalhe;

type Referencia = {
  demonstrativo_id: number;
  demonstrativo: string;
  periodicidade: "B" | "Q" | "S";
  periodo: number;
  periodo_final: boolean;
  /** instituição que entregou o relatório (desde a v1.1, a Prefeitura quando houver) */
  instituicao?: string | null;
};

export type Situacao = "regular" | "acima_alerta" | "acima_prudencial" | "acima_maximo";

// valores monetários e percentuais chegam como texto (Decimal) para não perder precisão
export type Pessoal = Referencia & {
  poder: string | null;
  nome_poder: string | null;
  instituicao: string | null;
  despesa_total_pessoal: string | null;
  rcl_ajustada: string | null;
  percentual: string | null;
  limite_alerta: string | null;
  limite_prudencial: string | null;
  limite_maximo: string | null;
  situacao: Situacao | null;
};

export type Divida = Referencia & {
  divida_consolidada_liquida: string | null;
  rcl_ajustada: string | null;
  percentual: string | null;
  limite_alerta: string | null;
  limite_maximo: string | null;
  situacao: Situacao | null;
};

export type Execucao = Referencia & {
  receita_prevista: string | null;
  receita_realizada: string | null;
  despesa_dotacao: string | null;
  despesa_empenhada: string | null;
  despesa_liquidada: string | null;
  despesa_paga: string | null;
  resultado: string | null;
  superavit_financeiro_utilizado: string | null;
};

export type Autonomia = Referencia & {
  receita_tributaria: string | null;
  cota_icms: string | null;
  cota_ipva: string | null;
  cota_itr: string | null;
  despesa_administracao: string | null;
  despesa_legislativa: string | null;
  receita_local: string | null;
  custo_estrutura: string | null;
  razao: string | null;
};

export type Liquidez = Referencia & {
  caixa_liquido_nao_vinculado: string | null;
  caixa_liquido_vinculado: string | null;
  rcl: string | null;
  percentual: string | null;
  percentual_com_vinculados: string | null;
  /** a linha (I) não veio na API; calculada como IV − II − III (metodologia v1.1) */
  nao_vinculados_derivado?: boolean;
};

export type Investimento = Referencia & {
  liquidado: string | null;
  empenhado: string | null;
  restos_a_pagar_nao_processados: string | null;
  receita_realizada: string | null;
  percentual: string | null;
};

export type Transparencia = {
  exercicio: number;
  periodicidade_rgf: "Q" | "S";
  blocos: Record<"rreo" | "rgf_executivo" | "rgf_legislativo" | "dca", { disponiveis: number; esperados: number }>;
  indice: string;
  provisorio: boolean;
};

/** Valores por habitante, com a população oficial do IBGE do ano (contexto, fora da nota). */
export type PerCapita = {
  populacao: number;
  ano_populacao: number;
  fonte_populacao: string | null;
  resposta_id_populacao: number | null;
  receita_local: string | null;
  investimento_liquidado: string | null;
};

export type Indicadores = {
  cod_ibge: number;
  exercicio: number;
  exercicios_disponiveis: number[];
  pessoal: Pessoal[];
  divida: Divida | null;
  execucao: Execucao | null;
  autonomia: Autonomia | null;
  liquidez: Liquidez | null;
  investimento: Investimento | null;
  transparencia: Transparencia | null;
  per_capita?: PerCapita | null;
};

/** Devolve null quando o ente ainda não tem RREO/RGF coletado (404). */
export type IndicadoresAno = Omit<Indicadores, "exercicios_disponiveis">;

/** Indicadores do exercício pedido (padrão: o mais recente); null se não há RREO/RGF. */
export async function obterIndicadores(cod: number, exercicio?: number): Promise<Indicadores | null> {
  const { serie } = await arquivoMunicipio(cod);
  if (!serie.length) return null;
  const anos = serie.map((a) => a.exercicio).sort((a, b) => b - a);
  const alvo = exercicio ?? anos[0];
  const ano = serie.find((a) => a.exercicio === alvo) ?? serie[serie.length - 1];
  return { ...ano, exercicios_disponiveis: anos };
}

export const obterSerie = async (cod: number) => (await arquivoMunicipio(cod)).serie;

export const INDICADORES_RANKING = [
  "autonomia",
  "pessoal",
  "liquidez",
  "investimento",
  "transparencia",
] as const;
export type IndicadorRanking = (typeof INDICADORES_RANKING)[number];

export type ItemRanking = {
  cod_ibge: number;
  nome: string;
  populacao: number | null;
  ano_populacao?: number | null;
  faixa: string | null;
  nota: string | null;
  indicadores_faltantes: number;
  posicao_geral: number | null;
  posicao_faixa: number | null;
  notas: Partial<Record<IndicadorRanking, number | null>>;
};

export type Ranking = {
  versao: string;
  hash_metodologia: string;
  calculado_em?: string;
  exercicios: string;
  /** só no ranking do Brasil: as UFs incluídas */
  ufs?: string[];
  itens: (ItemRanking & { uf?: string; posicao_uf?: number | null })[];
};

type Componente = {
  nota: number | null;
  anos_com_dado: number;
  /** null: o indicador multiplica a nota (transparência, desde a v1.1) */
  peso: number | null;
  anos: Record<string, { valor: number | null; nota: number | null }>;
};

export type DetalheRanking = {
  cod_ibge: number;
  versao: string;
  hash_metodologia: string;
  exercicios: string;
  populacao?: number | null;
  ano_populacao?: number | null;
  faixa: string | null;
  nota: string | null;
  indicadores_faltantes: number;
  posicao_geral: number | null;
  posicao_faixa: number | null;
  total_com_nota: number;
  total_faixa: number;
  componentes: Record<IndicadorRanking, Componente>;
};

export type RegraIndicador = {
  nome: string;
  /** ausente quando o indicador é multiplicador */
  peso?: number;
  multiplicador?: boolean;
  unidade: string;
  pior: number;
  melhor: number;
  relativo_ao_limite_maximo?: boolean;
  penaliza_ausencia?: boolean;
};

export type Metodologia = {
  versao: string;
  titulo: string;
  hash: string;
  exercicios: number[];
  ultimo_exercicio: number;
  janela_exercicios: number;
  minimo_indicadores_fiscais: number;
  /** "ibge": faixas pela estimativa do IBGE (v1.1); ausente: cadastro do SICONFI (v1.0) */
  populacao?: string;
  faixas: { nome: string; ate?: number }[];
  indicadores: Record<IndicadorRanking, RegraIndicador>;
};

/** Item do ranking nacional (ranking/BR.json): posições no país, na UF e na faixa. */
export type ItemRankingBR = Omit<ItemRanking, "posicao_geral" | "posicao_faixa"> & {
  uf: string;
  posicao_nacional: number | null;
  posicao_faixa_nacional: number | null;
  posicao_uf: number | null;
  posicao_faixa_uf: number | null;
};

const rankings = new Map<string, Promise<Ranking>>();
/** Ranking de uma UF (ranking/{UF}.json) ou do Brasil (uf = "BR"); para SP, sem o arquivo
 * por UF (exportação antiga), o ranking.json. As posições do Brasil vão em posicao_geral e
 * posicao_faixa, para a mesma tabela servir aos dois. */
const rankingCompleto = (uf: string) => {
  if (!rankings.has(uf)) {
    const p =
      uf === "BR"
        ? lerJson<Compacto & Omit<Ranking, "itens">>("ranking/BR.json").then((r) => ({
            ...r,
            itens: expandir<ItemRankingBR>(r).map((i) => ({
              ...i,
              posicao_geral: i.posicao_nacional,
              posicao_faixa: i.posicao_faixa_nacional,
            })),
          }))
        : lerJson<Ranking>(`ranking/${uf}.json`, true).then(
            (r) => r ?? (uf === "SP" ? lerJson<Ranking>("ranking.json") : Promise.reject(new Error(`Sem ranking publicado para ${uf}`))),
          );
    rankings.set(uf, p);
  }
  return rankings.get(uf)!;
};

export async function buscarRanking(f: { uf: string; faixa: string; busca: string }): Promise<Ranking> {
  const r = await rankingCompleto(f.uf);
  const termo = normalizar(f.busca);
  return {
    ...r,
    itens: r.itens.filter(
      (i) => (!f.faixa || i.faixa === f.faixa) && (!termo || normalizar(i.nome).includes(termo)),
    ),
  };
}

/** CSV do ranking: o arquivo completo publicado, filtrado para os municípios mostrados. */
export async function baixarCsvRanking(cods: Set<number> | null, nomeArquivo: string) {
  const texto = await (await fetch(urlDados("ranking.csv"))).text();
  const [cabecalho, ...linhas] = texto.replace(/^\uFEFF/, "").trimEnd().split("\n");
  const col = cabecalho.split(";").indexOf("cod_ibge");
  const filtradas = cods ? linhas.filter((l) => cods.has(Number(l.split(";")[col]))) : linhas;
  const blob = new Blob(["\uFEFF" + [cabecalho, ...filtradas].join("\n") + "\n"], {
    type: "text/csv;charset=utf-8",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nomeArquivo;
  a.click();
  URL.revokeObjectURL(a.href);
}

export const obterNota = async (cod: number) => (await arquivoMunicipio(cod)).nota;

export const obterMetodologia = () => lerJson<Metodologia>("metodologia.json");

/** Estado ou DF (estados/{UF}.json, ADR-0020): pessoal, liquidez e investimento, sem
 * autonomia (fórmula municipal) e sem ranking. */
export type ArquivoEstado = {
  ente: { cod_ibge: number; nome: string; uf: string; esfera: "E" | "D" };
  serie: { exercicio: number; pessoal: Pessoal[]; liquidez: Liquidez | null; investimento: Investimento | null }[];
};

export const obterEstado = (uf: string) => lerJson<ArquivoEstado>(`estados/${uf}.json`, true);

/** CSV de um ranking por UF ou do Brasil, montado no navegador a partir do JSON publicado
 * (as mesmas colunas do ranking.csv; para SP, o próprio ranking.csv). */
export async function baixarCsvRankingUF(uf: string, cods: Set<number> | null, nomeArquivo: string) {
  if (uf === "SP") return baixarCsvRanking(cods, nomeArquivo);
  const r = await rankingCompleto(uf);
  const cols = ["autonomia", "pessoal", "liquidez", "investimento", "transparencia"] as const;
  const esc = (v: unknown) => (v === null || v === undefined ? "" : String(v).replace(/;/g, ","));
  const linhas = r.itens
    .filter((i) => !cods || cods.has(i.cod_ibge))
    .map((i) =>
      [
        i.posicao_geral, i.posicao_faixa, ...(uf === "BR" ? [i.uf, i.posicao_uf] : []), i.cod_ibge,
        i.nome, i.populacao, i.faixa, i.nota, i.indicadores_faltantes,
        ...cols.map((c) => i.notas[c]), r.versao, r.hash_metodologia, r.exercicios,
      ].map(esc).join(";"),
    );
  const cabecalho = [
    "posicao_geral", "posicao_faixa", ...(uf === "BR" ? ["uf", "posicao_uf"] : []), "cod_ibge",
    "municipio", "populacao", "faixa", "nota", "indicadores_faltantes",
    ...cols.map((c) => `nota_${c}`), "versao_metodologia", "hash_metodologia", "exercicios",
  ].join(";");
  const blob = new Blob(["\uFEFF" + [cabecalho, ...linhas].join("\n") + "\n"], {
    type: "text/csv;charset=utf-8",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nomeArquivo;
  a.click();
  URL.revokeObjectURL(a.href);
}
