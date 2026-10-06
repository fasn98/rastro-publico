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

import type { Representantes } from "./apiPoliticos";
import { lerJson, normalizar, urlDados } from "./dados";

/** Arquivo estático de um município: detalhe, série, nota, representantes, emendas. */
export type ArquivoMunicipio = {
  detalhe: MunicipioDetalhe;
  serie: IndicadoresAno[];
  nota: DetalheRanking | null;
  representantes: {
    municipio: Representantes["municipio"];
    // seção inteira, ou referência ao arquivo de uma seção repetida entre municípios
    secoes: (Representantes["secoes"][number] | { ref: string })[];
  };
  emendas: unknown;
};

export const arquivoMunicipio = (cod: number) =>
  lerJson<ArquivoMunicipio>(`municipios/${cod}.json`);

const listaMunicipios = () => lerJson<Municipio[]>("municipios.json");

export const ufsDisponiveis = async () =>
  [...new Set((await listaMunicipios()).map((m) => m.uf))].sort();

export async function buscarMunicipios(uf: string, nome: string): Promise<Pagina<Municipio>> {
  const termo = normalizar(nome);
  const todos = (await listaMunicipios()).filter(
    (m) => (!uf || m.uf === uf) && (!termo || normalizar(m.nome).includes(termo)),
  );
  return { total: todos.length, itens: todos.slice(0, 100) };
}

export const obterMunicipio = async (cod: number) => (await arquivoMunicipio(cod)).detalhe;

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

const rankingCompleto = () => lerJson<Ranking>("ranking.json");

export async function buscarRanking(f: { uf: string; faixa: string; busca: string }): Promise<Ranking> {
  const r = await rankingCompleto();
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
