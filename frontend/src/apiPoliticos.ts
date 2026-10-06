// Dados do módulo de políticos (arquivos estáticos do site)

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
  situacao_candidatura: string | null;
  data_divulgacao: string | null;
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

export type ContagemValor = Contagem & { valor_liquido: string };

export type PoliticoDetalhe = Politico & {
  fonte_registro: Fonte | null;
  proposicoes: Contagem[];
  votacoes: ContagemVotos[];
  presencas: Contagem[];
  cota: ContagemValor[];
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

export type GrupoRepresentantes = {
  cargo: string;
  politicos: Politico[];
  pendente: string | null;
  pendente_url: string | null;
};

export type Representantes = {
  municipio: { cod_ibge: number; nome: string; uf: string };
  secoes: { titulo: string; nota: string | null; grupos: GrupoRepresentantes[] }[];
};

export type Pagina<T> = { total: number; itens: T[] };

export type Despesa = {
  ano: number;
  mes: number;
  linha: number;
  categoria: string;
  especificacao: string | null;
  fornecedor: string | null;
  cnpj: string | null;
  pessoa_fisica: boolean;
  numero_documento: string | null;
  data_emissao: string | null;
  valor_documento: string | null;
  valor_glosa: string | null;
  valor_liquido: string | null;
  valor_restituicao: string | null;
  url_documento: string | null;
  url_fonte: string;
  resposta_id: number | null;
};

export type Cota = {
  por_categoria: { categoria: string; quantidade: number; valor_liquido: string }[];
  despesas: Pagina<Despesa>;
};

// Dados estáticos (gerados por `rastro exportar-site`): nada aqui chama a API.
// O que uma trava de publicação (Settings.pol_publicar_*) deixa de fora não é exportado:
// o arquivo traz o mesmo aviso que a API daria, ou não existe.
import { arquivoMunicipio } from "./api";
import { lerJson } from "./dados";

type Secao = Representantes["secoes"][number];

const vazia = <T,>(): Pagina<T> => ({ total: 0, itens: [] });
const semEmendas: Emendas = {
  coletadas: false,
  publicadas: false,
  aviso: null,
  totais: [],
  por_parlamentar: [],
  itens: [],
};
const pasta = (a: number | null) => (a ? String(a) : "todos");

export async function obterRepresentantes(cod: number): Promise<Representantes> {
  const { representantes } = await arquivoMunicipio(cod);
  // seções iguais em todos os municípios (estado, federal) ficam num arquivo só
  const secoes = await Promise.all(
    representantes.secoes.map((s) => ("ref" in s ? lerJson<Secao>(s.ref) : Promise.resolve(s))),
  );
  return { municipio: representantes.municipio, secoes };
}
export const obterPolitico = (id: number) => lerJson<PoliticoDetalhe>(`politicos/${id}.json`);
// sem arquivo para o ano = nada registrado naquele ano
export const listarProposicoes = async (id: number, a: number | null) =>
  (await lerJson<Pagina<Proposicao>>(`politicos/${id}/proposicoes/${pasta(a)}.json`, true)) ??
  vazia<Proposicao>();
export const listarVotacoes = async (id: number, a: number | null) =>
  (await lerJson<Pagina<Votacao>>(`politicos/${id}/votacoes/${pasta(a)}.json`, true)) ??
  vazia<Votacao>();
export const listarPresencas = async (id: number, a: number | null) =>
  (await lerJson<Pagina<Presenca>>(`politicos/${id}/presencas/${pasta(a)}.json`, true)) ??
  vazia<Presenca>();
export const obterCota = async (id: number, a: number | null) =>
  (await lerJson<Cota>(`politicos/${id}/cota/${pasta(a)}.json`, true)) ?? {
    por_categoria: [],
    despesas: vazia<Despesa>(),
  };
export const obterEmendas = async (id: number, a: number | null) =>
  (await lerJson<Emendas>(`politicos/${id}/emendas/${pasta(a)}.json`, true)) ?? semEmendas;
export const obterEmendasMunicipio = async (cod: number) =>
  (await arquivoMunicipio(cod)).emendas as Emendas;

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
