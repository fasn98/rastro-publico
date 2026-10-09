import { useEffect, useMemo, useState } from "react";

type Geometria =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };
type Feicao = { properties: { codarea: string }; geometry: Geometria };

// malha mínima do IBGE de cada UF (public/geo/{UF}.json; ver scripts/baixar-malha.sh)
const malhas = new Map<string, Promise<Feicao[]>>();
const carregarMalha = (uf: string) => {
  if (!malhas.has(uf))
    malhas.set(
      uf,
      fetch(`${import.meta.env.BASE_URL}geo/${uf}.json`)
        .then((r) => r.json())
        .then((g) => g.features as Feicao[]),
    );
  return malhas.get(uf)!;
};

const L = 800;

// 5 classes iguais de nota; cores da rampa sequencial azul (CSS: --seq-1 a --seq-5)
export const CLASSES = [
  { de: 0, ate: 0.2 },
  { de: 0.2, ate: 0.4 },
  { de: 0.4, ate: 0.6 },
  { de: 0.6, ate: 0.8 },
  { de: 0.8, ate: 1 },
];
const classe = (nota: number) => Math.min(4, Math.floor(nota * 5));
const fmt = (v: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export default function Mapa({
  uf,
  nomeUf,
  notas,
  nomes,
  visiveis,
  aoClicar,
}: {
  uf: string;
  nomeUf: string;
  notas: Map<number, number | null>;
  nomes: Map<number, string>;
  visiveis: Set<number> | null; // null = todos; os demais ficam esmaecidos
  aoClicar: (cod: number) => void;
}) {
  const [feicoes, setFeicoes] = useState<Feicao[] | null>(null);
  const [dica, setDica] = useState<{ x: number; y: number; cod: number } | null>(null);

  useEffect(() => {
    setFeicoes(null);
    carregarMalha(uf).then(setFeicoes);
  }, [uf]);

  const desenho = useMemo(() => {
    if (!feicoes) return null;
    let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
    const aneis = (g: Geometria) => (g.type === "Polygon" ? g.coordinates : g.coordinates.flat());
    for (const f of feicoes)
      for (const anel of aneis(f.geometry))
        for (const [lon, lat] of anel) {
          x0 = Math.min(x0, lon); x1 = Math.max(x1, lon);
          y0 = Math.min(y0, lat); y1 = Math.max(y1, lat);
        }
    // equirretangular corrigida pela latitude média: suficiente na escala de um estado
    const kx = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
    const escala = L / ((x1 - x0) * kx);
    const altura = (y1 - y0) * escala;
    const ponto = ([lon, lat]: number[]) =>
      `${((lon - x0) * kx * escala).toFixed(1)},${((y1 - lat) * escala).toFixed(1)}`;
    const caminhos = feicoes.map((f) => ({
      cod: Number(f.properties.codarea),
      d: aneis(f.geometry).map((a) => `M${a.map(ponto).join("L")}Z`).join(""),
    }));
    return { caminhos, altura };
  }, [feicoes]);

  if (!desenho) return <p className="sub">Carregando mapa…</p>;

  // municípios da tabela sem desenho na malha mínima do IBGE (ex.: Boa Esperança do Norte/MT)
  const desenhados = new Set(desenho.caminhos.map((c) => c.cod));
  const semDesenho = [...nomes].filter(([cod]) => !desenhados.has(cod)).map(([, n]) => n);

  const notaDica = dica ? notas.get(dica.cod) : undefined;
  return (
    <div className="mapa">
      <svg
        viewBox={`0 0 ${L} ${desenho.altura.toFixed(0)}`}
        role="img"
        aria-label={`Mapa dos municípios de ${nomeUf} colorido pela nota do Ranking Fiscal. A tabela abaixo traz os mesmos dados.`}
        onMouseLeave={() => setDica(null)}
      >
        {desenho.caminhos.map(({ cod, d }) => {
          const nota = notas.get(cod);
          const cls = nota === null || nota === undefined ? "sem-nota" : `seq-${classe(nota) + 1}`;
          const apagado = visiveis && !visiveis.has(cod) ? " apagado" : "";
          return (
            <path
              key={cod}
              d={d}
              className={`mun ${cls}${apagado}${dica?.cod === cod ? " foco" : ""}`}
              onMouseMove={(e) => {
                const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                setDica({ x: e.clientX - r.left, y: e.clientY - r.top, cod });
              }}
              onClick={() => aoClicar(cod)}
            />
          );
        })}
      </svg>
      {dica && (
        <div className="mapa-dica" style={{ left: dica.x, top: dica.y }}>
          <strong>{nomes.get(dica.cod) ?? dica.cod}</strong>
          <span>
            {notaDica === null || notaDica === undefined ? "sem nota (não reportado)" : `nota ${fmt(notaDica * 10)}`}
          </span>
        </div>
      )}
      <div className="mapa-legenda" aria-hidden="true">
        {CLASSES.map((c, i) => (
          <span key={i}>
            <i className={`seq-${i + 1}`} />
            {fmt(c.de * 10)}–{fmt(c.ate * 10)}
          </span>
        ))}
        <span>
          <i className="sem-nota" />
          sem nota
        </span>
      </div>
      {semDesenho.length > 0 && (
        <p className="sub">
          Fora do mapa (sem desenho na malha mínima do IBGE): {semDesenho.join(", ")}. Aparece
          normalmente na tabela.
        </p>
      )}
    </div>
  );
}
