import { useEffect, useState } from "react";
import { daUf, NOME_UF, obterEstado, type ArquivoEstado } from "./api";
import { AUDITORIA_ATIVA, urlAuditoria } from "./dados";
import { LegendaLimites, Medidor, num, PERIODO, pct, reais, Status } from "./Indicadores";

/** Governo do estado ou DF (ADR-0020): pessoal, liquidez e investimento, sem ranking e sem
 * autonomia (a fórmula do ranking é municipal). */
export default function PaginaEstado({ uf, noronha }: { uf: string; noronha: boolean }) {
  const [dados, setDados] = useState<ArquivoEstado | null | undefined>(undefined);
  const [exercicio, setExercicio] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setDados(undefined);
    setExercicio(null);
    setErro(null);
    obterEstado(uf)
      .then(setDados)
      .catch((e: Error) => setErro(e.message));
  }, [uf]);

  const nome = NOME_UF[uf] ?? uf;
  const avisoNoronha = noronha && (
    <p className="nota">
      Fernando de Noronha é distrito estadual de Pernambuco, não município: não entrega RREO/RGF
      próprio ao SICONFI. As contas dele estão nas do estado de Pernambuco, abaixo.
    </p>
  );

  if (erro) return <p className="erro">{erro}</p>;
  if (dados === undefined) return <p className="sub">Carregando…</p>;
  if (dados === null)
    return (
      <section>
        <h2>{nome}</h2>
        {avisoNoronha}
        <p className="sub">
          Os indicadores {daUf(uf)} ainda não foram publicados: a UF entra no site depois de passar
          no portão de qualidade (coleta completa e conferência com a fonte).
        </p>
      </section>
    );

  const anos = [...dados.serie].sort((a, b) => b.exercicio - a.exercicio);
  const ano = anos.find((a) => a.exercicio === exercicio) ?? anos[0];
  const ref = ano?.pessoal[0] ?? ano?.liquidez ?? null;
  const rreo = ano?.investimento ?? null;
  const df = dados.ente.esfera === "D";

  return (
    <section className="estado">
      <h2>{df ? "Distrito Federal" : `${nome} · governo do estado`}</h2>
      {avisoNoronha}
      <p className="sub">
        Sem ranking: a metodologia do Ranking Fiscal é municipal. A autonomia também não aparece,
        porque a fórmula soma as cotas-parte que o município recebe e não é comparável para{" "}
        {df ? "o Distrito Federal" : "estados"}.
        {df
          ? " Brasília não entrega relatórios como município: as contas são as do Distrito Federal."
          : " "}
        {!df && <a href={`#/ranking/${uf}`}>Ranking dos municípios {daUf(uf)}</a>}
      </p>

      {!ano ? (
        <p className="sub">Nenhum RREO/RGF coletado para este ente.</p>
      ) : (
        <section className="indicadores">
          <div className="indicadores-topo">
            <h3>Indicadores fiscais</h3>
            {anos.length > 1 && (
              <select
                value={ano.exercicio}
                onChange={(e) => setExercicio(Number(e.target.value))}
                aria-label="Exercício"
              >
                {anos.map((a) => (
                  <option key={a.exercicio}>{a.exercicio}</option>
                ))}
              </select>
            )}
          </div>
          <p className="sub">
            Exercício {ano.exercicio}
            {ref && ` · RGF até o ${ref.periodo}º ${PERIODO[ref.periodicidade]}`}
            {rreo && ` · RREO até o ${rreo.periodo}º ${PERIODO[rreo.periodicidade]}`} · Fonte:
            SICONFI/Tesouro Nacional, valores declarados pelo ente
            {AUDITORIA_ATIVA && (ref || rreo) && " · respostas originais da API: "}
            {AUDITORIA_ATIVA && ref && (
              <a href={urlAuditoria(`/api/demonstrativos/${ref.demonstrativo_id}/respostas`)} target="_blank" rel="noreferrer">
                RGF
              </a>
            )}
            {AUDITORIA_ATIVA && ref && rreo && " · "}
            {AUDITORIA_ATIVA && rreo && (
              <a href={urlAuditoria(`/api/demonstrativos/${rreo.demonstrativo_id}/respostas`)} target="_blank" rel="noreferrer">
                RREO
              </a>
            )}
          </p>

          {ano.pessoal.length > 0 && (
            <div className="bloco">
              <h4>Despesa total com pessoal (% da Receita Corrente Líquida ajustada)</h4>
              {ano.pessoal.map((p) => {
                const limites = [
                  { nome: "alerta", valor: num(p.limite_alerta) },
                  { nome: "prudencial", valor: num(p.limite_prudencial) },
                  { nome: "máximo", valor: num(p.limite_maximo) },
                ];
                return (
                  <div className="linha-medidor" key={p.demonstrativo_id}>
                    <div className="linha-cabecalho">
                      <span>
                        <strong>{p.instituicao ?? p.nome_poder}</strong>{" "}
                        <span className="sub">({p.nome_poder})</span>
                      </span>
                      <span className="valor">
                        {pct(num(p.percentual))} <span className="sub">{reais(p.despesa_total_pessoal)}</span>
                      </span>
                    </div>
                    <Medidor
                      valor={num(p.percentual)}
                      limites={limites}
                      situacao={p.situacao}
                      rotulo="Despesa com pessoal"
                    />
                    <div className="linha-rodape">
                      <Status situacao={p.situacao} />
                      <LegendaLimites limites={limites} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="bloco">
            <h4>Liquidez e investimento</h4>
            <div className="tiles">
              <div className="tile">
                <span className="tile-rotulo">Liquidez (recursos não vinculados)</span>
                <span className="tile-valor">{pct(num(ano.liquidez?.percentual ?? null))}</span>
                <span className="sub">
                  da RCL · caixa {reais(ano.liquidez?.caixa_liquido_nao_vinculado ?? null)}
                </span>
              </div>
              <div className="tile">
                <span className="tile-rotulo">Investimento liquidado</span>
                <span className="tile-valor">{pct(num(ano.investimento?.percentual ?? null))}</span>
                <span className="sub">
                  da receita · {reais(ano.investimento?.liquidado ?? null)} liquidados; empenhados{" "}
                  {reais(ano.investimento?.empenhado ?? null)}
                </span>
              </div>
            </div>
            {ano.liquidez?.nao_vinculados_derivado && (
              <p className="nota">
                A linha “recursos não vinculados (I)” não veio na API do SICONFI, que omite linhas
                com valor zero. O valor foi calculado pelo total do próprio relatório: (I) = (IV) −
                (II) − (III).
              </p>
            )}
          </div>
        </section>
      )}
    </section>
  );
}
