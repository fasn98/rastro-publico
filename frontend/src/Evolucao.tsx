import { useEffect, useState } from "react";
import { obterSerie, type IndicadoresAno } from "./api";

type Ponto = { ano: number; valor: number | null };
type Formato = (v: number) => string;

const pct: Formato = (v) => `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
const reais: Formato = (v) =>
  v.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    notation: "compact",
    maximumFractionDigits: 1,
  });
const n = (v: string | null | undefined) => (v === null || v === undefined ? null : Number(v));

const L = 300; // largura do viewBox
const A = 132; // altura do viewBox
const TOPO = 16;
const BASE_ROTULOS = 18; // espaço para os anos embaixo

/** Colunas por ano, com linha de referência opcional (ex.: limite legal). */
function Colunas({
  titulo,
  pontos,
  formato,
  referencia,
  sinal = false,
}: {
  titulo: string;
  pontos: Ponto[];
  formato: Formato;
  referencia?: { valor: number; rotulo: string } | null;
  sinal?: boolean; // colore negativo diferente (ex.: déficit)
}) {
  const [foco, setFoco] = useState<number | null>(null);
  const valores = pontos.flatMap((p) => (p.valor === null ? [] : [p.valor]));
  const max = Math.max(0, ...valores, referencia?.valor ?? 0);
  const min = Math.min(0, ...valores);
  const span = max - min || 1;
  const altUtil = A - TOPO - BASE_ROTULOS;
  const y = (v: number) => TOPO + ((max - v) / span) * altUtil;
  const zero = y(0);
  // com linha de referência, reserva uma margem à direita para o rótulo dela
  const largPlot = referencia ? L - 72 : L;
  const passo = largPlot / pontos.length;
  const larg = Math.min(36, passo * 0.5);
  const ultimo = pontos.length - 1;

  return (
    <figure className="evo-grafico">
      <figcaption>{titulo}</figcaption>
      <svg viewBox={`0 0 ${L} ${A}`} role="img" aria-label={`${titulo}: ${pontos
        .map((p) => `${p.ano} ${p.valor === null ? "não reportado" : formato(p.valor)}`)
        .join(", ")}`}>
        <line className="evo-base" x1={0} x2={largPlot} y1={zero} y2={zero} />
        {referencia && (
          <g className="evo-ref">
            <line x1={0} x2={largPlot} y1={y(referencia.valor)} y2={y(referencia.valor)} />
            <text x={largPlot + 4} y={y(referencia.valor) + 3}>
              {referencia.rotulo}
            </text>
          </g>
        )}
        {pontos.map((p, i) => {
          const cx = passo * i + passo / 2;
          if (p.valor === null)
            return (
              <g key={p.ano}>
                <text className="evo-nr" x={cx} y={zero - 6} textAnchor="middle">
                  n/r
                </text>
                <text className="evo-ano" x={cx} y={A - 4} textAnchor="middle">
                  {p.ano}
                </text>
              </g>
            );
          const topo = Math.min(y(p.valor), zero);
          const h = Math.max(1, Math.abs(y(p.valor) - zero));
          const negativo = p.valor < 0;
          const r = Math.min(4, h / 2);
          // canto arredondado só na ponta do dado; a base fica reta, ancorada no zero
          const d = negativo
            ? `M${cx - larg / 2},${topo} h${larg} v${h - r} q0,${r} -${r},${r} h-${larg - 2 * r} q-${r},0 -${r},-${r} Z`
            : `M${cx - larg / 2},${topo + h} v-${h - r} q0,-${r} ${r},-${r} h${larg - 2 * r} q${r},0 ${r},${r} v${h - r} Z`;
          return (
            <g
              key={p.ano}
              onMouseEnter={() => setFoco(i)}
              onMouseLeave={() => setFoco(null)}
              className={foco === i ? "evo-col foco" : "evo-col"}
            >
              {/* alvo de hover maior que a barra */}
              <rect x={cx - passo / 2} y={0} width={passo} height={A} fill="transparent" />
              <path d={d} className={sinal && negativo ? "evo-barra negativo" : "evo-barra"} />
              {(i === ultimo || foco === i) && (
                <text
                  className="evo-valor"
                  x={cx}
                  // negativo: acima do zero, para não cobrir o ano embaixo
                  y={negativo ? zero - 4 : topo - 4}
                  textAnchor="middle"
                >
                  {formato(p.valor)}
                </text>
              )}
              <text className="evo-ano" x={cx} y={A - 4} textAnchor="middle">
                {p.ano}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

export default function Evolucao({ cod }: { cod: number }) {
  const [serie, setSerie] = useState<IndicadoresAno[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    setSerie(null);
    obterSerie(cod)
      .then((s) => ativo && setSerie(s))
      .catch((e: Error) => ativo && setErro(e.message));
    return () => {
      ativo = false;
    };
  }, [cod]);

  if (erro) return <p className="erro">{erro}</p>;
  if (!serie || serie.length < 2) return null;

  const executivo = (a: IndicadoresAno) => a.pessoal.find((p) => p.poder === "E") ?? null;
  const ultimoExec = executivo(serie[serie.length - 1]);
  const ultimaDivida = serie[serie.length - 1].divida;

  const graficos = [
    {
      titulo: "Pessoal do Executivo (% da RCL)",
      formato: pct,
      pontos: serie.map((a) => ({ ano: a.exercicio, valor: n(executivo(a)?.percentual) })),
      referencia: n(ultimoExec?.limite_maximo)
        ? { valor: n(ultimoExec?.limite_maximo)!, rotulo: `máximo ${pct(n(ultimoExec?.limite_maximo)!)}` }
        : null,
    },
    {
      titulo: "Dívida consolidada líquida (% da RCL)",
      formato: pct,
      pontos: serie.map((a) => ({ ano: a.exercicio, valor: n(a.divida?.percentual) })),
      referencia: n(ultimaDivida?.limite_maximo)
        ? { valor: n(ultimaDivida?.limite_maximo)!, rotulo: `máximo ${pct(n(ultimaDivida?.limite_maximo)!)}` }
        : null,
    },
    {
      titulo: "Resultado orçamentário (receita − despesa empenhada)",
      formato: reais,
      sinal: true,
      pontos: serie.map((a) => ({ ano: a.exercicio, valor: n(a.execucao?.resultado) })),
    },
    {
      titulo: "Receita realizada (% da prevista)",
      formato: pct,
      pontos: serie.map((a) => {
        const r = n(a.execucao?.receita_realizada);
        const p = n(a.execucao?.receita_prevista);
        return { ano: a.exercicio, valor: r !== null && p ? Math.round((r / p) * 10000) / 100 : null };
      }),
    },
  ];

  return (
    <div className="bloco evolucao">
      <h4>
        Evolução {serie[0].exercicio}–{serie[serie.length - 1].exercicio}
      </h4>
      <p className="sub">
        Último período entregue de cada exercício. n/r = não reportado. No resultado
        orçamentário, barras para baixo (vermelho) indicam déficit.
      </p>
      <div className="evo-grade">
        {graficos.map((g) => (
          <Colunas key={g.titulo} {...g} />
        ))}
      </div>
      <details>
        <summary>Ver tabela</summary>
        <div className="tabela-rolagem">
          <table>
            <thead>
              <tr>
                <th>Indicador</th>
                {serie.map((a) => (
                  <th key={a.exercicio}>{a.exercicio}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {graficos.map((g) => (
                <tr key={g.titulo}>
                  <th scope="row">{g.titulo}</th>
                  {g.pontos.map((p) => (
                    <td key={p.ano}>{p.valor === null ? "n/r" : g.formato(p.valor)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
