// Dados do módulo de políticos (arquivos estáticos do site)

// Fonte: URL oficial + SHA-256 da cópia arquivada (aberta em /api/bruto/{sha256} na API de
// auditoria) + data em que aquele conteúdo foi recebido pela primeira vez.
export type Fonte = { url: string; recebido_em: string | null; sha256: string | null };

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
  sha256: string | null;
};

/** Político como aparece na lista de representantes; `eleito` = arquivo do TSE. */
export type PoliticoResumo = { id: number; nome: string; partido: string | null; eleito?: string };

export const hrefPolitico = (p: { id: number; eleito?: string }) =>
  p.eleito ? `#/eleito/${p.eleito}/${p.id}` : `#/politico/${p.id}`;

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
  sha256: string | null;
};

export type ContagemValor = Contagem & { valor_liquido: string };

export type PeriodoMandato = {
  inicio: string;
  fim: string | null;
  situacao: string | null;
  condicao_eleitoral: string | null;
  descricao_status: string | null;
  partido: string | null;
  url_fonte: string;
  sha256: string | null;
};

export type PoliticoDetalhe = Politico & {
  fonte_registro: Fonte | null;
  proposicoes: Contagem[];
  votacoes: ContagemVotos[];
  presencas: Contagem[];
  cota: ContagemValor[];
  comissoes: Comissao[];
  descricao_votos: Record<string, string>;
  linha_do_tempo: PeriodoMandato[];
  emendas?: { coletadas: boolean; publicadas: boolean; aviso: string | null; anos: number[] };
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
  sha256: string | null;
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
  sha256: string | null;
};

export type Presenca = {
  id_evento: string;
  data_hora_inicio: string;
  url_fonte: string;
  sha256: string | null;
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
  politico_id: number | null;
  vinculo: string | null;
  nota_vinculo: string | null;
  url_fonte: string;
  sha256: string | null;
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
  nome_fonte: string | null;
  nota_vinculo: string | null;
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
  politicos: PoliticoResumo[];
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
  sha256: string | null;
};

export type CategoriaCota = { categoria: string; quantidade: number; valor_liquido: string };

/** Cabeçalho da cota de um ano: totais por categoria; item a item só nos anos recentes. */
export type CotaAno = {
  ano: number;
  total: number;
  por_categoria: CategoriaCota[];
  detalhada: boolean;
  paginas: number;
  aviso: string | null;
  url_oficial: string;
  url_busca_detalhada: string;
};

export type Cota = { por_categoria: CategoriaCota[]; anos: CotaAno[]; despesas: Lista<Despesa> };

/** Lista lida em páginas de 500: `mais` = há páginas ainda não carregadas. */
export type Lista<T> = Pagina<T> & { mais: boolean };

// Dados estáticos (gerados por `rastro exportar-site`): nada aqui chama a API.
// O que uma trava de publicação (Settings.pol_publicar_*) deixa de fora não é exportado:
// o arquivo traz o mesmo aviso que a API daria, ou não existe.
import { arquivoMunicipio } from "./api";
import { lerJson } from "./dados";

type Secao = Representantes["secoes"][number];

/** Lista compacta: campos iguais em todos os itens em `comum`; textos repetidos em
 * `indices` (o item guarda a posição). Ver rastro/site.py. */
type Compacto = {
  comum?: Record<string, unknown>;
  indices?: Record<string, unknown[]>;
  itens: Record<string, unknown>[];
};

export function expandir<T>(c: Compacto): T[] {
  const indices = Object.entries(c.indices ?? {});
  return c.itens.map((x) => {
    const y: Record<string, unknown> = { ...c.comum, ...x };
    for (const [campo, lista] of indices) y[campo] = lista[x[campo] as number];
    return y as T;
  });
}

const TAM_PAGINA = 500;
const semEmendas: Emendas = {
  coletadas: false,
  publicadas: false,
  aviso: null,
  totais: [],
  por_parlamentar: [],
  itens: [],
};

export async function obterRepresentantes(cod: number): Promise<Representantes> {
  const { representantes } = await arquivoMunicipio(cod);
  // seções iguais em todos os municípios (estado, federal) ficam num arquivo só
  const secoes = await Promise.all(
    representantes.secoes.map((s) => ("ref" in s ? lerJson<Secao>(s.ref) : Promise.resolve(s))),
  );
  return { municipio: representantes.municipio, secoes };
}

// campos que o arquivo omite quando vazios (eleitos do TSE)
const VAZIO: Omit<PoliticoDetalhe, "id" | "fonte" | "id_fonte" | "nome" | "cargo" | "uf" | "url_fonte"> = {
  partido: null,
  cod_ibge: null,
  situacao: null,
  em_exercicio: null,
  legislatura: null,
  mandato_inicio: null,
  mandato_fim: null,
  eleicao_ano: null,
  situacao_candidatura: null,
  data_divulgacao: null,
  url_pagina: null,
  sha256: null,
  fonte_registro: null,
  proposicoes: [],
  votacoes: [],
  presencas: [],
  cota: [],
  comissoes: [],
  descricao_votos: {},
  linha_do_tempo: [],
};

export const obterPolitico = async (id: number) => ({
  ...VAZIO,
  ...(await lerJson<PoliticoDetalhe>(`politicos/${id}.json`)),
});

/** Eleito do TSE: os eleitos ficam num arquivo por município ou por UF e eleição. */
export async function obterEleito(chave: string, id: number): Promise<PoliticoDetalhe> {
  const arquivo = await lerJson<Compacto>(`eleitos/${chave}.json`);
  const p = expandir<PoliticoDetalhe>(arquivo).find((x) => x.id === id);
  if (!p) throw new Error("Político não encontrado");
  return { ...VAZIO, ...p };
}

type ListaPolitico = "proposicoes" | "votacoes" | "presencas" | "cota";
type PaginaArquivo = Compacto & { ano: number; pagina: number; paginas: number; total: number };

// páginas de um ano estão em politicos/{id}/{lista}/{ano}-{n}.json; o seletor "todos os
// anos" percorre os anos do mais recente ao mais antigo
function sequencia(anos: { ano: number; total: number }[], ano: number | null) {
  return anos
    .filter((c) => ano === null || c.ano === ano)
    .sort((a, b) => b.ano - a.ano)
    .flatMap((c) =>
      Array.from({ length: Math.ceil(c.total / TAM_PAGINA) }, (_, i) => ({ ano: c.ano, n: i + 1 })),
    );
}

async function lerPaginas<T>(
  id: number,
  lista: ListaPolitico,
  seq: { ano: number; n: number }[],
  paginas: number,
  total: number,
  completar?: (ano: number, itens: T[]) => Promise<T[]>,
): Promise<Lista<T>> {
  const lidas = await Promise.all(
    seq.slice(0, paginas).map(async ({ ano, n }) => {
      const itens = expandir<T>(await lerJson<PaginaArquivo>(`politicos/${id}/${lista}/${ano}-${n}.json`));
      return completar ? completar(ano, itens) : itens;
    }),
  );
  return { total, itens: lidas.flat(), mais: paginas < seq.length };
}

// votações e presenças: data, órgão, matéria e fonte vêm do catálogo do ano (iguais para
// todos os parlamentares); o arquivo do político guarda o id e o voto
function comCatalogo<T>(lista: "votacoes" | "presencas", casa: string, chave: string) {
  return async (ano: number, itens: T[]) => {
    const cat = await lerJson<Compacto>(`catalogos/${lista}/${casa}/${ano}.json`, true);
    if (!cat) return itens;
    const mapa = new Map(expandir<Record<string, unknown>>(cat).map((x) => [x[chave], x]));
    return itens.map((x) => ({ ...mapa.get((x as Record<string, unknown>)[chave]), ...x }) as T);
  };
}

const contagens = (lista: Contagem[]) => lista.map((c) => ({ ano: c.ano, total: c.quantidade }));
const soma = (lista: Contagem[], ano: number | null) =>
  lista.filter((c) => ano === null || c.ano === ano).reduce((s, c) => s + c.quantidade, 0);

export const listarProposicoes = (p: PoliticoDetalhe, ano: number | null, paginas: number) =>
  lerPaginas<Proposicao>(p.id, "proposicoes", sequencia(contagens(p.proposicoes), ano), paginas, soma(p.proposicoes, ano));
export const listarVotacoes = (p: PoliticoDetalhe, ano: number | null, paginas: number) =>
  lerPaginas<Votacao>(
    p.id,
    "votacoes",
    sequencia(contagens(p.votacoes), ano),
    paginas,
    soma(p.votacoes, ano),
    comCatalogo<Votacao>("votacoes", p.fonte, "id_votacao"),
  );
export const listarPresencas = (p: PoliticoDetalhe, ano: number | null, paginas: number) =>
  lerPaginas<Presenca>(
    p.id,
    "presencas",
    sequencia(contagens(p.presencas), ano),
    paginas,
    soma(p.presencas, ano),
    comCatalogo<Presenca>("presencas", p.fonte, "id_evento"),
  );

const centavos = (v: string) => Math.round(Number(v) * 100);

export async function obterCota(p: PoliticoDetalhe, ano: number | null, paginas: number): Promise<Cota> {
  const anos = await Promise.all(
    p.cota
      .filter((c) => ano === null || c.ano === ano)
      .sort((a, b) => b.ano - a.ano)
      .map((c) => lerJson<CotaAno>(`politicos/${p.id}/cota/${c.ano}.json`)),
  );
  // totais por categoria somados em centavos (sem erro de arredondamento)
  const cats = new Map<string, { quantidade: number; centavos: number }>();
  for (const a of anos)
    for (const c of a.por_categoria) {
      const x = cats.get(c.categoria) ?? { quantidade: 0, centavos: 0 };
      cats.set(c.categoria, { quantidade: x.quantidade + c.quantidade, centavos: x.centavos + centavos(c.valor_liquido) });
    }
  const detalhadas = anos.filter((a) => a.detalhada);
  const despesas = await lerPaginas<Despesa>(
    p.id,
    "cota",
    sequencia(detalhadas.map((a) => ({ ano: a.ano, total: a.total })), null),
    paginas,
    detalhadas.reduce((s, a) => s + a.total, 0),
  );
  return {
    // um ano: a ordem do arquivo (alfabética, como na API); vários: alfabética em pt-BR
    por_categoria: anos.length === 1 ? anos[0].por_categoria : [...cats.entries()]
      .sort(([a], [b]) => a.localeCompare(b, "pt-BR"))
      .map(([categoria, x]) => ({ categoria, quantidade: x.quantidade, valor_liquido: (x.centavos / 100).toFixed(2) })),
    anos,
    despesas,
  };
}

export async function obterEmendas(p: PoliticoDetalhe, ano: number | null): Promise<Emendas> {
  const meta = p.emendas;
  if (!meta?.publicadas) return { ...semEmendas, coletadas: meta?.coletadas ?? false, aviso: meta?.aviso ?? null };
  const arquivos = await Promise.all(
    meta.anos
      .filter((a) => ano === null || a === ano)
      .map((a) => lerJson<Emendas>(`politicos/${p.id}/emendas/${a}.json`)),
  );
  return {
    ...semEmendas,
    coletadas: true,
    publicadas: true,
    totais: arquivos.flatMap((x) => x.totais),
    itens: arquivos.flatMap((x) => x.itens),
  };
}

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
