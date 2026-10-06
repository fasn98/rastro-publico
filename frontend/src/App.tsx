import { useEffect, useState } from "react";
import Metodologia from "./Metodologia";
import Municipios from "./Municipios";
import RankingPagina from "./Ranking";

type Rota = { pagina: "municipios" | "ranking" | "metodologia"; cod: number | null };

function lerRota(): Rota {
  const h = location.hash;
  const m = h.match(/^#\/municipio\/(\d+)/);
  if (m) return { pagina: "municipios", cod: Number(m[1]) };
  if (h.startsWith("#/ranking")) return { pagina: "ranking", cod: null };
  if (h.startsWith("#/metodologia")) return { pagina: "metodologia", cod: null };
  return { pagina: "municipios", cod: null };
}

const LINKS = [
  ["municipios", "#/", "Municípios"],
  ["ranking", "#/ranking", "Ranking Fiscal"],
  ["metodologia", "#/metodologia", "Metodologia"],
] as const;

export default function App() {
  const [rota, setRota] = useState(lerRota);

  useEffect(() => {
    const mudou = () => {
      setRota(lerRota());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", mudou);
    return () => window.removeEventListener("hashchange", mudou);
  }, []);

  return (
    <main>
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
      {rota.pagina === "ranking" && <RankingPagina />}
      {rota.pagina === "metodologia" && <Metodologia />}
    </main>
  );
}
