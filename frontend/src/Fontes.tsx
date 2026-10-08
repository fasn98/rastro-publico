import type { Manifesto, SituacaoFonte } from "./dados";

const data = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—");

/** Situação de uma fonte nesta coleta, em texto (nunca só cor). */
export function situacao(f: SituacaoFonte): string {
  if (f.atualizada_nesta_coleta) return "Atualizada nesta coleta";
  if (!f.tentada_nesta_coleta) return "Não coletada nesta execução";
  if (f.disponivel) return `Não atualizada nesta coleta: dados de ${data(f.ultima_atualizacao)}`;
  return "Fonte indisponível nesta coleta";
}

export const desatualizadas = (m: Manifesto | null) =>
  (m?.fontes ?? []).filter((f) => f.tentada_nesta_coleta && !f.atualizada_nesta_coleta);

/** Fonte por cargo, para marcar as seções de representantes. */
export const FONTE_DO_CARGO: Record<string, string> = {
  deputado_federal: "pol-camara",
  senador: "pol-senado",
  prefeito: "pol-tse",
  vereador: "pol-tse",
  governador: "pol-tse",
  deputado_estadual: "pol-tse",
};

/** Aviso no topo das páginas quando alguma fonte não foi atualizada nesta coleta. */
export function AvisoFontes({ manifesto }: { manifesto: Manifesto | null }) {
  const lista = desatualizadas(manifesto);
  if (!lista.length) return null;
  return (
    <p className="aviso-fontes" role="status">
      Nesta coleta, {lista.length === 1 ? "uma fonte não foi atualizada" : `${lista.length} fontes não foram atualizadas`}:{" "}
      {lista.map((f) => `${f.nome} (${situacao(f).replace(/^Não atualizada nesta coleta: /, "")})`).join("; ")}.{" "}
      <a href="#/fontes">Status das fontes</a>
    </p>
  );
}

export default function StatusFontes({ manifesto }: { manifesto: Manifesto | null }) {
  const fontes = manifesto?.fontes;
  return (
    <section>
      <h2>Status das fontes</h2>
      <p className="sub">
        Situação de cada fonte oficial na coleta que gerou este site
        {manifesto ? ` (${new Date(manifesto.gerado_em).toLocaleString("pt-BR")})` : ""}. Quando uma
        fonte falha, o site continua publicado com os dados anteriores dela; se ela nunca foi coletada,
        as seções que dependem dela aparecem como indisponíveis.
      </p>
      {!fontes?.length ? (
        <p>Esta publicação não traz a situação das fontes.</p>
      ) : (
        <div className="tabela-rolavel">
          <table>
            <thead>
              <tr>
                <th>Fonte</th>
                <th>Nesta coleta</th>
                <th>Última atualização bem-sucedida</th>
              </tr>
            </thead>
            <tbody>
              {fontes.map((f) => (
                <tr key={f.fonte}>
                  <td>{f.nome}</td>
                  <td>
                    {situacao(f)}
                    {f.falha && <div className="sub">{f.falha}</div>}
                  </td>
                  <td>{data(f.ultima_atualizacao)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
