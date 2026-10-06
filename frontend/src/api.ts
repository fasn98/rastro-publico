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

export type Indicadores = {
  cod_ibge: number;
  exercicio: number;
  exercicios_disponiveis: number[];
  pessoal: Pessoal[];
  divida: Divida | null;
  execucao: Execucao | null;
};

/** Devolve null quando o ente ainda não tem RREO/RGF coletado (404). */
export async function obterIndicadores(cod: number, exercicio?: number) {
  const qs = exercicio ? `?exercicio=${exercicio}` : "";
  const resp = await fetch(`/api/entes/${cod}/indicadores${qs}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar indicadores`);
  return (await resp.json()) as Indicadores;
}
