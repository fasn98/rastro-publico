import { useEffect, useLayoutEffect, useState } from "react";
import { obterManifesto, PREVIA, type Manifesto } from "./dados";
import Metodologia from "./Metodologia";
import Municipios from "./Municipios";
import { PaginaPolitico, QuemRepresenta } from "./Politicos";
import RankingPagina from "./Ranking";

type Rota = {
  pagina: "municipios" | "ranking" | "metodologia" | "representantes" | "politico";
  cod: number | null;
  eleito?: string; // eleito do TSE: arquivo do município (m-{cod}) ou da UF (uf-{UF}-{ano})
};

function lerRota(): Rota {
  const h = location.hash;
  const m = h.match(/^#\/municipio\/(\d+)/);
  if (m) return { pagina: "municipios", cod: Number(m[1]) };
  const r = h.match(/^#\/representantes(?:\/(\d+))?/);
  if (r) return { pagina: "representantes", cod: r[1] ? Number(r[1]) : null };
  const p = h.match(/^#\/politico\/(\d+)/);
  if (p) return { pagina: "politico", cod: Number(p[1]) };
  const e = h.match(/^#\/eleito\/(m-\d+|uf-[A-Z]{2}-\d{4})\/(\d+)/);
  if (e) return { pagina: "politico", cod: Number(e[2]), eleito: e[1] };
  if (h.startsWith("#/ranking")) return { pagina: "ranking", cod: null };
  if (h.startsWith("#/metodologia")) return { pagina: "metodologia", cod: null };
  return { pagina: "municipios", cod: null };
}

const LINKS = [
  ["municipios", "#/", "Municípios"],
  ["ranking", "#/ranking", "Ranking Fiscal"],
  ["metodologia", "#/metodologia", "Metodologia"],
  ["representantes", "#/representantes", "Quem representa você"],
] as const;

export default function App() {
  const [rota, setRota] = useState(lerRota);
  const [manifesto, setManifesto] = useState<Manifesto | null>(null);

  useEffect(() => {
    obterManifesto().then(setManifesto).catch(() => setManifesto(null));
  }, []);

  useEffect(() => {
    // o navegador não deve restaurar a rolagem antiga ao abrir um link ou voltar
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    const mudou = () => setRota(lerRota());
    window.addEventListener("hashchange", mudou);
    return () => window.removeEventListener("hashchange", mudou);
  }, []);

  // toda troca de rota abre no topo, depois que a nova página foi desenhada
  useLayoutEffect(() => {
    window.scrollTo(0, 0);
  }, [rota.pagina, rota.cod]);

  return (
    <main>
      {PREVIA && (
        <div className="faixa-previa" role="note">
          Prévia — dados parciais em validação. Coleta completa em andamento.
        </div>
      )}
      <header className="topo">
        <div>
          <h1>Rastro Público</h1>
          <p className="sub">Dados públicos de municípios brasileiros (IBGE e Tesouro/SICONFI)</p>
        </div>
        <nav aria-label="Páginas">
          {LINKS.map(([p, href, rotulo]) => (
            <a key={p} href={href} aria-current={rota.pagina === p ? "page" : undefined}>
              {rotulo}
            </a>
          ))}
        </nav>
      </header>
      {rota.pagina === "municipios" && <Municipios cod={rota.cod} />}
      {rota.pagina === "ranking" &&
        (PREVIA ? (
          <p className="aviso-previa-ranking">Ranking disponível após a coleta completa dos 645 municípios</p>
        ) : (
          <RankingPagina />
        ))}
      {rota.pagina === "metodologia" && <Metodologia />}
      {rota.pagina === "representantes" && <QuemRepresenta cod={rota.cod} />}
      {rota.pagina === "politico" && rota.cod !== null && <PaginaPolitico id={rota.cod} eleito={rota.eleito} />}
      {manifesto && (
        <footer className="rodape">
          Dados coletados até{" "}
          {new Date(manifesto.ultima_coleta ?? manifesto.gerado_em).toLocaleDateString("pt-BR")} ·
          site gerado em {new Date(manifesto.gerado_em).toLocaleString("pt-BR")} · metodologia v
          {manifesto.metodologia.versao}
          {manifesto.codigo && (
            <>
              {" "}
              · código{" "}
              <a href={`https://github.com/fasn98/rastro-publico/commit/${manifesto.codigo}`}>
                {manifesto.codigo.slice(0, 7)}
              </a>
            </>
          )}
        </footer>
      )}
    </main>
  );
}
