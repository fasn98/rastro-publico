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
