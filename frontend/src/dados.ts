// Acesso aos dados do site. O site publicado é estático: tudo vem de arquivos JSON gerados
// por `rastro exportar-site` (pasta dados/). Só a auditoria (resposta bruta e verificação
// do SHA-256) usa a API, em VITE_API_AUDITORIA.

const BASE = `${import.meta.env.BASE_URL}dados/`;

export const API_AUDITORIA = ((import.meta.env.VITE_API_AUDITORIA as string | undefined) ?? "").replace(
  /\/$/,
  "",
);

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

export type Manifesto = {
  gerado_em: string;
  ultima_coleta: string | null;
  uf: string;
  codigo: string | null;
  metodologia: { versao: string; hash: string };
  mapeamento: { versao: number; hash: string };
  contagens: Record<string, number>;
};

export const obterManifesto = () => lerJson<Manifesto>("manifesto.json", true);
