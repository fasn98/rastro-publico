export type Municipio = {
  cod_ibge: number;
  nome: string;
  uf: string;
  regiao: string;
  regiao_imediata: string | null;
  regiao_intermediaria: string | null;
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

export type MunicipioDetalhe = Municipio & { ente_siconfi: Ente | null };

export type Pagina<T> = { total: number; itens: T[] };

async function get<T>(caminho: string, params: Record<string, string> = {}): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== ""));
  const resp = await fetch(`/api${caminho}${qs.size ? `?${qs}` : ""}`);
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar ${caminho}`);
  return resp.json();
}

export const buscarMunicipios = (uf: string, nome: string) =>
  get<Pagina<Municipio>>("/municipios", { uf, nome, limite: "100" });

export const obterMunicipio = (cod: number) => get<MunicipioDetalhe>(`/municipios/${cod}`);

type Referencia = {
  demonstrativo_id: number;
  demonstrativo: string;
  periodicidade: "B" | "Q" | "S";
  periodo: number;
  periodo_final: boolean;
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
};

/** Devolve null quando o ente ainda não tem RREO/RGF coletado (404). */
export async function obterIndicadores(cod: number, exercicio?: number) {
  const qs = exercicio ? `?exercicio=${exercicio}` : "";
  const resp = await fetch(`/api/entes/${cod}/indicadores${qs}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar indicadores`);
  return (await resp.json()) as Indicadores;
}

export type IndicadoresAno = Omit<Indicadores, "exercicios_disponiveis">;

export async function obterSerie(cod: number) {
  const resp = await fetch(`/api/entes/${cod}/indicadores/serie`);
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar a série histórica`);
  return (await resp.json()) as IndicadoresAno[];
}

// --- Ranking Fiscal ---

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
  calculado_em: string;
  exercicios: string;
  itens: ItemRanking[];
};

type Componente = {
  nota: number | null;
  anos_com_dado: number;
  peso: number;
  anos: Record<string, { valor: number | null; nota: number | null }>;
};

export type DetalheRanking = {
  cod_ibge: number;
  versao: string;
  hash_metodologia: string;
  exercicios: string;
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
  peso: number;
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
  faixas: { nome: string; ate?: number }[];
  indicadores: Record<IndicadorRanking, RegraIndicador>;
};

const filtros = (f: Record<string, string>) =>
  new URLSearchParams(Object.entries(f).filter(([, v]) => v !== "")).toString();

export const buscarRanking = (f: { uf: string; faixa: string; busca: string }) =>
  get<Ranking>("/ranking", f);

export const urlCsvRanking = (f: { uf: string; faixa: string; busca: string }) =>
  `/api/ranking.csv?${filtros(f)}`;

/** null quando o município não tem nota calculada (404). */
export async function obterNota(cod: number) {
  const resp = await fetch(`/api/ranking/${cod}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar a nota`);
  return (await resp.json()) as DetalheRanking;
}

export const obterMetodologia = () => get<Metodologia>("/metodologia");
