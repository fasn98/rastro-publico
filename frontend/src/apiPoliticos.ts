// Cliente da API do módulo de políticos (/api/politicos, /api/municipios/{cod}/representantes)

export type Fonte = { url: string; recebido_em: string; resposta_id: number };

export type Politico = {
  id: number;
  fonte: "camara" | "senado" | "tse";
  id_fonte: string;
  nome: string;
  partido: string | null;
  cargo: string;
  uf: string;
  cod_ibge: number | null;
  situacao: string | null;
  em_exercicio: boolean | null;
  legislatura: number | null;
  mandato_inicio: string | null;
  mandato_fim: string | null;
  eleicao_ano: number | null;
  url_fonte: string;
  url_pagina: string | null;
  resposta_id: number | null;
  atualizado_em: string;
};

export type Contagem = { ano: number; quantidade: number; fontes: Fonte[] };
export type ContagemVotos = Contagem & { por_voto: Record<string, number> };

export type Comissao = {
  sigla: string;
  nome: string;
  casa: string | null;
  participacao: string | null;
  data_inicio: string | null;
  data_fim: string | null;
  url_fonte: string;
  resposta_id: number | null;
};

export type PoliticoDetalhe = Politico & {
  fonte_registro: Fonte | null;
  proposicoes: Contagem[];
  votacoes: ContagemVotos[];
  presencas: Contagem[];
  comissoes: Comissao[];
  descricao_votos: Record<string, string>;
};

export type Proposicao = {
  id_fonte: string;
  sigla_tipo: string | null;
  numero: string | null;
  ano: number;
  ementa: string | null;
  data_apresentacao: string | null;
  autoria: string | null;
  url_fonte: string;
  url_pagina: string | null;
  resposta_id: number | null;
};

export type Votacao = {
  id_votacao: string;
  data: string;
  voto: string;
  voto_descricao: string | null;
  orgao: string | null;
  materia: string | null;
  descricao: string | null;
  url_fonte: string;
  resposta_id: number | null;
};

export type Presenca = {
  id_evento: string;
  data_hora_inicio: string;
  url_fonte: string;
  resposta_id: number | null;
};

export type Emenda = {
  codigo_emenda: string;
  ano: number;
  tipo_emenda: string | null;
  transferencia_especial: boolean;
  nome_autor: string | null;
  numero_emenda: string | null;
  localidade_gasto: string | null;
  cod_ibge_destino: number | null;
  funcao: string | null;
  subfuncao: string | null;
  valor_empenhado: string | null;
  valor_liquidado: string | null;
  valor_pago: string | null;
  url_fonte: string;
  resposta_id: number | null;
};

export type TotalEmendas = {
  ano: number;
  transferencia_especial: boolean;
  quantidade: number;
  valor_empenhado: string;
  valor_liquidado: string;
  valor_pago: string;
};

export type EmendasPorParlamentar = {
  politico_id: number | null;
  nome_autor: string | null;
  partido: string | null;
  cargo: string | null;
  quantidade: number;
  valor_empenhado: string;
  valor_liquidado: string;
  valor_pago: string;
};

export type Emendas = {
  coletadas: boolean;
  publicadas: boolean;
  aviso: string | null;
  totais: TotalEmendas[];
  por_parlamentar: EmendasPorParlamentar[];
  itens: Emenda[];
};

export type GrupoRepresentantes = { cargo: string; politicos: Politico[]; pendente: string | null };

export type Representantes = {
  municipio: { cod_ibge: number; nome: string; uf: string };
  secoes: { titulo: string; nota: string | null; grupos: GrupoRepresentantes[] }[];
};

export type Pagina<T> = { total: number; itens: T[] };

async function get<T>(caminho: string, params: Record<string, string> = {}): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== ""));
  const resp = await fetch(`/api${caminho}${qs.size ? `?${qs}` : ""}`);
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar ${caminho}`);
  return resp.json();
}

const ano = (a: number | null) => (a ? String(a) : "");

export const obterRepresentantes = (cod: number) =>
  get<Representantes>(`/municipios/${cod}/representantes`);
export const obterPolitico = (id: number) => get<PoliticoDetalhe>(`/politicos/${id}`);
export const listarProposicoes = (id: number, a: number | null) =>
  get<Pagina<Proposicao>>(`/politicos/${id}/proposicoes`, { ano: ano(a), limite: "500" });
export const listarVotacoes = (id: number, a: number | null) =>
  get<Pagina<Votacao>>(`/politicos/${id}/votacoes`, { ano: ano(a), limite: "500" });
export const listarPresencas = (id: number, a: number | null) =>
  get<Pagina<Presenca>>(`/politicos/${id}/presencas`, { ano: ano(a), limite: "500" });
export const obterEmendas = (id: number, a: number | null) =>
  get<Emendas>(`/politicos/${id}/emendas`, { ano: ano(a) });
export const obterEmendasMunicipio = (cod: number) => get<Emendas>(`/municipios/${cod}/emendas`);

export const CARGOS: Record<string, string> = {
  prefeito: "Prefeito(a)",
  vereador: "Vereador(a)",
  governador: "Governador(a)",
  senador: "Senador(a)",
  deputado_federal: "Deputado(a) federal",
  deputado_estadual: "Deputado(a) estadual",
};

export const FONTES: Record<string, string> = {
  camara: "Câmara dos Deputados",
  senado: "Senado Federal",
  tse: "Tribunal Superior Eleitoral",
};
