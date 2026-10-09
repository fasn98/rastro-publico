import { useEffect, useMemo, useState } from "react";
import {
  baixarCsvRankingUF,
  buscarRanking,
  INDICADORES_RANKING,
  daUf,
  NOME_UF,
  obterMetodologia,
  ufsNoSite,
  type Metodologia,
  type Ranking,
} from "./api";
import { obterManifesto } from "./dados";
import Mapa from "./Mapa";

export const nota10 = (v: number | string | null | undefined) =>
  v === null || v === undefined
    ? "—"
    : (Number(v) * 10).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const ABREV: Record<string, string> = {
  autonomia: "Auton.",
  pessoal: "Pessoal",
  liquidez: "Liquidez",
  investimento: "Invest.",
  transparencia: "Transp.*",
};

export default function RankingPagina({ uf }: { uf: string }) {
  const brasil = uf === "BR";
  const nomeUf = brasil ? "Brasil" : (NOME_UF[uf] ?? uf);
  const [ufs, setUfs] = useState<{ ufs: string[]; nacional: boolean }>({ ufs: ["SP"], nacional: false });
  useEffect(() => {
    ufsNoSite().then(setUfs).catch(() => undefined);
  }, []);
  const [faixa, setFaixa] = useState("");
  const [busca, setBusca] = useState("");
  const [semNota, setSemNota] = useState(false);
  const [limite, setLimite] = useState(100);
  const [dados, setDados] = useState<Ranking | null>(null);
  const [todos, setTodos] = useState<Ranking | null>(null);
  const [met, setMet] = useState<Metodologia | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    obterMetodologia().then(setMet).catch((e: Error) => setErro(e.message));
  }, []);

  useEffect(() => {
    setTodos(null);
    setErro(null);
    setLimite(100);
    buscarRanking({ uf, faixa: "", busca: "" })
      .then(setTodos)
      .catch((e: Error) => setErro(e.message));
  }, [uf]);

  useEffect(() => {
    const t = setTimeout(() => {
      buscarRanking({ uf, faixa, busca: busca.trim() })
        .then((r) => {
          setDados(r);
          setErro(null);
        })
        .catch(() => setDados(null));
    }, 250);
    return () => clearTimeout(t);
  }, [uf, faixa, busca]);

  const { notas, nomes } = useMemo(() => {
    const notas = new Map<number, number | null>();
    const nomes = new Map<number, string>();
    for (const i of todos?.itens ?? []) {
      notas.set(i.cod_ibge, i.nota === null ? null : Number(i.nota));
      nomes.set(i.cod_ibge, i.nome);
    }
    return { notas, nomes };
  }, [todos]);

  // link "ver gestões" só quando os prefeitos eleitos estão publicados (pol_publicar_gestoes)
  const [gestoes, setGestoes] = useState(false);
  useEffect(() => {
    obterManifesto()
      .then((m) => setGestoes(!!m?.travas?.pol_publicar_gestoes))
      .catch(() => setGestoes(false));
  }, []);
  const itens = dados?.itens ?? [];
  const visiveis = useMemo(
    () => (faixa || busca ? new Set(itens.map((i) => i.cod_ibge)) : null),
    [itens, faixa, busca],
  );
  const comNota = itens.filter((i) => i.nota !== null);
  const linhas = (semNota ? itens : comNota).slice(0, limite);
  const posicao = faixa ? "posicao_faixa" : "posicao_geral";

  const seletor = (
    <select
      value={uf}
      onChange={(e) => (location.hash = `#/ranking/${e.target.value}`)}
      aria-label="Unidade da Federação"
    >
      {ufs.nacional && <option value="BR">Brasil (todas as UFs no site)</option>}
      {ufs.ufs
        .filter((u) => u !== "DF")
        .map((u) => (
          <option key={u} value={u}>
            {NOME_UF[u] ?? u}
          </option>
        ))}
    </select>
  );

  if (erro)
    return (
      <section>
        <h2>Ranking Fiscal</h2>
        <div className="filtros">{seletor}</div>
        <p className="erro">{erro}</p>
      </section>
    );

  return (
    <section>
      <h2>Ranking Fiscal — municípios {brasil ? "do Brasil" : daUf(uf)}</h2>
      {todos && (
        <p className="sub">
          Metodologia v{todos.versao} · média dos exercícios {todos.exercicios.replace(/,/g, ", ")} ·
          notas de 0 a 10 · {todos.itens.filter((i) => i.nota !== null).length} de{" "}
          {todos.itens.length} municípios com nota · <a href="#/metodologia">como a nota é calculada</a>
          {!brasil && uf !== "DF" && (
            <>
              {" · "}
              <a href={`#/estado/${uf}`}>governo do estado (indicadores, sem ranking)</a>
            </>
          )}
        </p>
      )}
      {brasil && todos?.ufs && (
        <p className="sub">
          UFs no ranking: {todos.ufs.join(", ")}. As demais ainda não passaram no portão de
          qualidade e entram quando forem aprovadas. O Distrito Federal não tem ranking municipal.
        </p>
      )}

      <div className="filtros">
        {seletor}
        <select value={faixa} onChange={(e) => setFaixa(e.target.value)} aria-label="Faixa populacional">
          <option value="">Todas as faixas populacionais</option>
          {met?.faixas.map((f) => (
            <option key={f.nome} value={f.nome}>
              {f.nome}
            </option>
          ))}
        </select>
        <input placeholder="Buscar município" value={busca} onChange={(e) => setBusca(e.target.value)} />
        <button
          className="botao"
          onClick={() =>
            baixarCsvRankingUF(
              uf,
              visiveis,
              `ranking-fiscal-${uf.toLowerCase()}${faixa ? "-" + faixa.replace(/\W+/g, "-") : ""}.csv`,
            )
          }
        >
          Exportar CSV
        </button>
      </div>

      {!brasil && (
        <Mapa
          uf={uf}
          nomeUf={nomeUf}
          notas={notas}
          nomes={nomes}
          visiveis={visiveis}
          aoClicar={(c) => (location.hash = `#/municipio/${c}`)}
        />
      )}

      <div className="ranking-cabecalho">
        <p className="total">
          {comNota.length} com nota{faixa && ` na faixa "${faixa}"`}
          {itens.length > comNota.length && `, ${itens.length - comNota.length} sem nota`}
        </p>
        <label className="sub">
          <input type="checkbox" checked={semNota} onChange={(e) => setSemNota(e.target.checked)} /> mostrar
          municípios sem nota
        </label>
      </div>

      <div className="tabela-rolagem">
        <table className="tabela-ranking">
          <thead>
            <tr>
              <th>{faixa ? (brasil ? "Pos. na faixa (Brasil)" : "Pos. na faixa") : brasil ? "Posição no Brasil" : "Posição"}</th>
              <th className="esq">Município</th>
              {brasil && <th>UF</th>}
              {brasil && <th title="posição entre os municípios da própria UF">Pos. na UF</th>}
              <th>Nota</th>
              <th className="esq">Faixa</th>
              {INDICADORES_RANKING.map((k) => (
                <th key={k} title={met?.indicadores[k]?.nome}>
                  {ABREV[k]}
                </th>
              ))}
              <th title="indicadores sem dado (não reportados)">Faltam</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((i) => (
              <tr key={i.cod_ibge}>
                <td>{i[posicao] ?? "—"}</td>
                <td className="esq">
                  <a href={`#/municipio/${i.cod_ibge}`}>{i.nome}</a>
                  {gestoes && (
                    // ADR-0018: nenhum nome de prefeito na linha da nota; só o caminho para a
                    // página do município, onde ficam os eleitos de cada mandato
                    <a className="ver-gestoes" href={`#/municipio/${i.cod_ibge}/prefeitos`}>
                      ver gestões
                    </a>
                  )}
                </td>
                {brasil && <td>{i.uf}</td>}
                {brasil && <td>{i.posicao_uf ?? "—"}</td>}
                <td className="nota-final">{i.nota === null ? "sem nota" : nota10(i.nota)}</td>
                <td className="esq">{i.faixa}</td>
                {INDICADORES_RANKING.map((k) => (
                  <td key={k}>{nota10(i.notas[k])}</td>
                ))}
                <td>{i.indicadores_faltantes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(semNota ? itens : comNota).length > limite && (
        <button className="botao" onClick={() => setLimite((l) => l + 100)}>
          Mostrar mais
        </button>
      )}
      <p className="nota-rodape">
        * Transparência: multiplica a média dos 4 indicadores fiscais. "—" = não reportado. Notas
        por indicador de 0 a 10. Faixas pela estimativa de população do IBGE.
      </p>
    </section>
  );
}
