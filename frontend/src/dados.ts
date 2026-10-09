// Acesso aos dados do site. O site publicado é estático: tudo vem de arquivos JSON gerados
// por `rastro exportar-site` (pasta dados/). Só a auditoria (resposta bruta e verificação
// do SHA-256) usa a API, em VITE_API_AUDITORIA.

const BASE = `${import.meta.env.BASE_URL}dados/`;

export const API_AUDITORIA = ((import.meta.env.VITE_API_AUDITORIA as string | undefined) ?? "").replace(
  /\/$/,
  "",
);

/**
 * Prévia (VITE_PREVIA=1): faixa "Prévia — dados em validação" em todas as páginas e
 * `noindex` (fora dos buscadores) até o lançamento ser aprovado. Não esconde nenhum dado.
 */
export const PREVIA = import.meta.env.VITE_PREVIA === "1";
/** Links de "resposta original"/"cópia arquivada" só quando há API de auditoria configurada. */
export const AUDITORIA_ATIVA = API_AUDITORIA !== "";

/** URL de um endpoint da API de auditoria (ex.: "/api/respostas/12/bruto"). */
export const urlAuditoria = (caminho: string) => `${API_AUDITORIA}${caminho}`;

export const urlDados = (caminho: string) => `${BASE}${caminho}`;

const cache = new Map<string, Promise<unknown>>();

/** Lê um JSON de dados/. Com `opcional`, devolve null quando o arquivo não existe. */
export function lerJson<T>(caminho: string, opcional: true): Promise<T | null>;
export function lerJson<T>(caminho: string, opcional?: false): Promise<T>;
export function lerJson<T>(caminho: string, opcional = false): Promise<T | null> {
  const chave = `${opcional}:${caminho}`;
  if (!cache.has(chave)) {
    const p = fetch(urlDados(caminho)).then(async (r) => {
      if (r.status === 404 && opcional) return null;
      if (!r.ok) throw new Error(`Erro ${r.status} ao carregar ${caminho}`);
      return r.json();
    });
    p.catch(() => cache.delete(chave)); // erro de rede não fica guardado
    cache.set(chave, p);
  }
  return cache.get(chave) as Promise<T | null>;
}

/** Busca sem acento e sem diferença de maiúsculas. */
export const normalizar = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export type SituacaoFonte = {
  fonte: string;
  nome: string;
  ultima_atualizacao: string | null;
  tentada_nesta_coleta: boolean;
  atualizada_nesta_coleta: boolean;
  disponivel: boolean;
  falha: string | null;
};

export type Manifesto = {
  gerado_em: string;
  ultima_coleta: string | null;
  uf: string;
  codigo: string | null;
  metodologia: { versao: string; hash: string };
  mapeamento: { versao: number; hash: string };
  contagens: Record<string, number>;
  fontes?: SituacaoFonte[];
  /** travas de publicação no momento da exportação (Settings.pol_publicar_*) */
  travas?: Record<string, boolean>;
};

export const obterManifesto = () => lerJson<Manifesto>("manifesto.json", true);
