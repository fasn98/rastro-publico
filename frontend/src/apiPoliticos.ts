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

export type Emendas = {
  coletadas: boolean;
  aviso: string | null;
  totais: TotalEmendas[];
  itens: Emenda[];
};

export type Representantes = {
  municipio: { cod_ibge: number; nome: string; uf: string };
  grupos: { cargo: string; politicos: Politico[]; pendente: string | null }[];
};

export type Pagina<T> = { total: number; itens: T[] };

// Dados estáticos (gerados por `rastro exportar-site`): nada aqui chama a API.
import { arquivoMunicipio } from "./api";
import { lerJson } from "./dados";

const vazia = <T,>(): Pagina<T> => ({ total: 0, itens: [] });
const semEmendas: Emendas = { coletadas: false, aviso: null, totais: [], itens: [] };
const pasta = (a: number | null) => (a ? String(a) : "todos");

export async function obterRepresentantes(cod: number): Promise<Representantes> {
  const { representantes } = await arquivoMunicipio(cod);
  const grupos = await lerJson<Representantes["grupos"]>(representantes.grupos_ref);
  return { municipio: representantes.municipio as Representantes["municipio"], grupos };
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
