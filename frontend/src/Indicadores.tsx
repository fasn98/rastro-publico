import { useEffect, useState } from "react";
import {
  obterIndicadores,
  obterNota,
  ufDoCodigo,
  type DetalheRanking,
  type Indicadores as Dados,
  type Situacao,
} from "./api";
import { AUDITORIA_ATIVA, urlAuditoria } from "./dados";
import { nota10 } from "./Ranking";
import Evolucao from "./Evolucao";
import { PrefeitoDoExercicio } from "./Politicos";

export const num = (v: string | null) => (v === null ? null : Number(v));

export const pct = (v: number | null) =>
  v === null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

export const reais = (v: string | null) =>
  v === null
    ? "—"
    : Number(v).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL",
        notation: "compact",
        maximumFractionDigits: 1,
      });

export const PERIODO = { B: "bimestre", Q: "quadrimestre", S: "semestre" } as const;

const ROTULO: Record<Situacao, { icone: string; texto: string }> = {
  regular: { icone: "✓", texto: "Dentro dos limites" },
  acima_alerta: { icone: "!", texto: "Acima do limite de alerta" },
  acima_prudencial: { icone: "!!", texto: "Acima do limite prudencial" },
  acima_maximo: { icone: "✕", texto: "Acima do limite máximo" },
};

export function Status({ situacao }: { situacao: Situacao | null }) {
  if (!situacao) return null;
  const r = ROTULO[situacao];
  return (
    <span className={`status status-${situacao}`}>
      <span className="status-icone" aria-hidden="true">
        {r.icone}
      </span>
      {r.texto}
    </span>
  );
}

type Limite = { nome: string; valor: number | null };

/** Medidor de um percentual contra os limites legais (ticks na trilha). */
export function Medidor({
  valor,
  limites,
  situacao,
  rotulo,
}: {
  valor: number | null;
  limites: Limite[];
  situacao: Situacao | null;
  rotulo: string;
}) {
  const definidos = limites.filter((l): l is { nome: string; valor: number } => l.valor !== null);
  const maxLimite = Math.max(0, ...definidos.map((l) => l.valor));
  const escala = Math.max(maxLimite * 1.1, (valor ?? 0) * 1.05, 1);
  const largura = valor === null ? 0 : Math.max(0, Math.min(100, (valor / escala) * 100));
  const descricao = `${rotulo}: ${pct(valor)}. ${definidos
    .map((l) => `Limite ${l.nome}: ${pct(l.valor)}`)
    .join(". ")}`;
  return (
    <div
      className="medidor"
      role="meter"
      aria-label={descricao}
      aria-valuenow={valor ?? undefined}
      aria-valuemin={0}
      aria-valuemax={escala}
    >
      <div className={`medidor-preenchimento sit-${situacao ?? "regular"}`} style={{ width: `${largura}%` }}>
        <span className="dica">{`${rotulo}: ${pct(valor)}`}</span>
      </div>
      {definidos.map((l) => (
        <div
          key={l.nome}
          className={`medidor-limite limite-${l.nome}`}
          style={{ left: `${(l.valor / escala) * 100}%` }}
        >
          <span className="dica">{`Limite ${l.nome}: ${pct(l.valor)}`}</span>
        </div>
      ))}
    </div>
  );
}

export function LegendaLimites({ limites }: { limites: Limite[] }) {
  return (
    <p className="legenda-limites">
      Limites da LRF:{" "}
      {limites
        .filter((l) => l.valor !== null)
        .map((l) => `${l.nome} ${pct(l.valor)}`)
        .join(" · ")}
    </p>
  );
}

const NOMES: Record<string, string> = {
  autonomia: "Autonomia",
  pessoal: "Pessoal",
  liquidez: "Liquidez",
  investimento: "Investimento",
  transparencia: "Transparência*",
};

function NotaRanking({ cod }: { cod: number }) {
  const [nota, setNota] = useState<DetalheRanking | null | undefined>(undefined);
  useEffect(() => {
    obterNota(cod)
      .then(setNota)
      .catch(() => setNota(null));
  }, [cod]);
  if (!nota) return null;
  return (
    <div className="bloco nota-ranking">
      <h4>
        Ranking Fiscal <span className="sub">v{nota.versao} · média {nota.exercicios.replace(/,/g, ", ")}</span>
      </h4>
      {nota.nota === null ? (
        <p className="sub">Sem nota: faltam dados de {nota.indicadores_faltantes} indicador(es).</p>
      ) : (
        <div className="nota-linha">
          <span className="nota-grande">{nota10(nota.nota)}</span>
          <span className="sub">
            {nota.posicao_geral}º de {nota.total_com_nota} em {ufDoCodigo(cod)} · {nota.posicao_faixa}º de {nota.total_faixa} na
            faixa “{nota.faixa}”
            {nota.ano_populacao && ` (população IBGE ${nota.ano_populacao})`}
            {nota.indicadores_faltantes > 0 && ` · ${nota.indicadores_faltantes} indicador(es) não reportado(s)`}
          </span>
        </div>
      )}
      <ul className="notas-componentes">
        {Object.entries(nota.componentes).map(([k, c]) => (
          <li key={k}>
            <span>{NOMES[k] ?? k}</span>
            <strong>{c.nota === null ? "não reportado" : nota10(c.nota)}</strong>
          </li>
        ))}
      </ul>
      <p className="sub">
        <a href={`#/ranking/${ufDoCodigo(cod)}`}>Ver ranking</a> · <a href="#/metodologia">metodologia</a> · *multiplica a
        média dos 4 indicadores fiscais
      </p>
    </div>
  );
}

export default function Indicadores({ cod }: { cod: number }) {
  const [dados, setDados] = useState<Dados | null | undefined>(undefined);
  const [exercicio, setExercicio] = useState<number | undefined>(undefined);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setExercicio(undefined);
  }, [cod]);

  useEffect(() => {
    let ativo = true;
    setErro(null);
    obterIndicadores(cod, exercicio)
      .then((d) => ativo && setDados(d))
      .catch((e: Error) => ativo && setErro(e.message));
    return () => {
      ativo = false;
    };
  }, [cod, exercicio]);

  if (erro) return <p className="erro">{erro}</p>;
  if (dados === undefined) return <p className="sub">Carregando indicadores…</p>;
  if (dados === null)
    return (
      <section className="indicadores vazio">
        <h3>Indicadores fiscais</h3>
        <p className="sub">
          Nenhum RREO/RGF coletado para este ente. Para coletar:{" "}
          <code>rastro siconfi-demonstrativos --exercicio 2025 --ente {cod}</code>
        </p>
      </section>
    );

  const { pessoal, divida, execucao, autonomia, liquidez, investimento, transparencia } = dados;
  const pc = dados.per_capita ?? null;
  const porHab = (v: string | null | undefined) =>
    pc && v != null ? `${reais(v)} por habitante` : null;
  const ref = pessoal[0] ?? divida;

  return (
    <section className="indicadores">
      <div className="indicadores-topo">
        <h3>Indicadores fiscais</h3>
        {dados.exercicios_disponiveis.length > 1 && (
          <select
            value={dados.exercicio}
            onChange={(e) => setExercicio(Number(e.target.value))}
            aria-label="Exercício"
          >
            {dados.exercicios_disponiveis.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        )}
      </div>
      <p className="sub">
        Exercício {dados.exercicio}
        {ref && ` · RGF até o ${ref.periodo}º ${PERIODO[ref.periodicidade]}`}
        {execucao && ` · RREO até o ${execucao.periodo}º ${PERIODO[execucao.periodicidade]}`} ·
        Fonte: SICONFI/Tesouro Nacional, valores declarados pelo ente
        {AUDITORIA_ATIVA && (ref || execucao) && " · respostas originais da API: "}
        {AUDITORIA_ATIVA && ref && (
          <a href={urlAuditoria(`/api/demonstrativos/${ref.demonstrativo_id}/respostas`)} target="_blank" rel="noreferrer">
            RGF
          </a>
        )}
        {AUDITORIA_ATIVA && ref && execucao && " · "}
        {AUDITORIA_ATIVA && execucao && (
          <a href={urlAuditoria(`/api/demonstrativos/${execucao.demonstrativo_id}/respostas`)} target="_blank" rel="noreferrer">
            RREO
          </a>
        )}
      </p>

      <PrefeitoDoExercicio cod={cod} exercicio={dados.exercicio} />

      <NotaRanking cod={cod} />

      {pessoal.length > 0 && (
        <div className="bloco">
          <h4>Despesa total com pessoal (% da Receita Corrente Líquida ajustada)</h4>
          {pessoal.map((p) => {
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
                    {pct(num(p.percentual))}{" "}
                    <span className="sub">{reais(p.despesa_total_pessoal)}</span>
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
                {(num(p.percentual) ?? 0) > 100 && (
                  <p className="nota">
                    Valor declarado acima de 100% da RCL ajustada: mostrado como está no relatório
                    entregue ao SICONFI; pode ser erro de preenchimento na fonte.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {divida && (
        <div className="bloco">
          <h4>Dívida consolidada líquida (% da RCL ajustada)</h4>
          <div className="linha-medidor">
            <div className="linha-cabecalho">
              <span>{reais(divida.divida_consolidada_liquida)}</span>
              <span className="valor">{pct(num(divida.percentual))}</span>
            </div>
            <Medidor
              valor={num(divida.percentual)}
              limites={[
                { nome: "alerta", valor: num(divida.limite_alerta) },
                { nome: "máximo", valor: num(divida.limite_maximo) },
              ]}
              situacao={divida.situacao}
              rotulo="Dívida consolidada líquida"
            />
            <div className="linha-rodape">
              <Status situacao={divida.situacao} />
              <LegendaLimites
                limites={[
                  { nome: "alerta", valor: num(divida.limite_alerta) },
                  { nome: "máximo", valor: num(divida.limite_maximo) },
                ]}
              />
            </div>
            {num(divida.divida_consolidada_liquida)! < 0 && (
              <p className="nota">
                Valor negativo: o caixa e os haveres financeiros superam a dívida consolidada.
              </p>
            )}
          </div>
        </div>
      )}

      {execucao && (
        <div className="bloco">
          <h4>Execução orçamentária acumulada no exercício</h4>
          <div className="tiles">
            <div className="tile">
              <span className="tile-rotulo">Receita realizada</span>
              <span className="tile-valor">{reais(execucao.receita_realizada)}</span>
              <span className="sub">
                {pct(
                  execucao.receita_realizada && execucao.receita_prevista
                    ? (Number(execucao.receita_realizada) / Number(execucao.receita_prevista)) * 100
                    : null,
                )}{" "}
                da prevista ({reais(execucao.receita_prevista)})
              </span>
            </div>
            <div className="tile">
              <span className="tile-rotulo">Despesa empenhada</span>
              <span className="tile-valor">{reais(execucao.despesa_empenhada)}</span>
              <span className="sub">de {reais(execucao.despesa_dotacao)} autorizados</span>
            </div>
            <div className="tile">
              <span className="tile-rotulo">Despesa paga</span>
              <span className="tile-valor">{reais(execucao.despesa_paga)}</span>
              <span className="sub">liquidada: {reais(execucao.despesa_liquidada)}</span>
            </div>
            <div className="tile">
              <span className="tile-rotulo">
                {num(execucao.resultado)! < 0 ? "Déficit orçamentário" : "Superávit orçamentário"}
              </span>
              <span className="tile-valor">{reais(execucao.resultado)}</span>
              <span className="sub">receita realizada − despesa empenhada</span>
            </div>
          </div>
          {num(execucao.resultado)! < 0 && num(execucao.superavit_financeiro_utilizado) ? (
            <p className="nota">
              O déficit do exercício pode ser coberto por saldo de anos anteriores: o ente
              registrou {reais(execucao.superavit_financeiro_utilizado)} de superávit financeiro
              utilizado.
            </p>
          ) : null}
        </div>
      )}

      <div className="bloco">
        <h4>Autonomia, liquidez e investimento</h4>
        <div className="tiles">
          <div className="tile">
            <span className="tile-rotulo">Autonomia</span>
            <span className="tile-valor">
              {autonomia?.razao ? `${Number(autonomia.razao).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}×` : "—"}
            </span>
            <span className="sub">
              receita local {reais(autonomia?.receita_local ?? null)} ÷ estrutura administrativa{" "}
              {reais(autonomia?.custo_estrutura ?? null)}
              {porHab(pc?.receita_local) && <> · receita local: {porHab(pc?.receita_local)}</>}
            </span>
          </div>
          <div className="tile">
            <span className="tile-rotulo">Liquidez (recursos não vinculados)</span>
            <span className="tile-valor">{pct(num(liquidez?.percentual ?? null))}</span>
            <span className="sub">
              da RCL · caixa {reais(liquidez?.caixa_liquido_nao_vinculado ?? null)}
              {liquidez?.percentual_com_vinculados && (
                <> · com vinculados: {pct(num(liquidez.percentual_com_vinculados))} (contexto, fora da nota)</>
              )}
            </span>
          </div>
          <div className="tile">
            <span className="tile-rotulo">Investimento liquidado</span>
            <span className="tile-valor">{pct(num(investimento?.percentual ?? null))}</span>
            <span className="sub">
              da receita · {reais(investimento?.liquidado ?? null)} liquidados; empenhados{" "}
              {reais(investimento?.empenhado ?? null)}, restos a pagar não processados{" "}
              {reais(investimento?.restos_a_pagar_nao_processados ?? null)}
              {porHab(pc?.investimento_liquidado) && <> · {porHab(pc?.investimento_liquidado)}</>}
            </span>
          </div>
          <div className="tile">
            <span className="tile-rotulo">Transparência (relatórios entregues)</span>
            <span className="tile-valor">
              {transparencia ? pct(Number(transparencia.indice) * 100) : "—"}
            </span>
            <span className="sub">
              {transparencia
                ? `RREO ${transparencia.blocos.rreo.disponiveis}/${transparencia.blocos.rreo.esperados} · RGF Exec. ${transparencia.blocos.rgf_executivo.disponiveis}/${transparencia.blocos.rgf_executivo.esperados} · RGF Leg. ${transparencia.blocos.rgf_legislativo.disponiveis}/${transparencia.blocos.rgf_legislativo.esperados} · DCA ${transparencia.blocos.dca.disponiveis}/1`
                : "extrato de entregas não coletado"}
            </span>
          </div>
        </div>
        {pc && (pc.receita_local != null || pc.investimento_liquidado != null) && (
          <p className="sub">
            Por habitante: população de {pc.populacao.toLocaleString("pt-BR")} ({pc.fonte_populacao},{" "}
            {pc.ano_populacao}). Só contexto: não entra na nota do ranking.
            {AUDITORIA_ATIVA && pc.resposta_id_populacao && (
              <>
                {" "}
                <a href={urlAuditoria(`/api/respostas/${pc.resposta_id_populacao}/bruto`)} target="_blank" rel="noreferrer">
                  cópia arquivada
                </a>
              </>
            )}
          </p>
        )}
        {liquidez?.nao_vinculados_derivado && (
          <p className="nota">
            A linha “recursos não vinculados (I)” não veio na API do SICONFI, que omite linhas com
            valor zero. O valor foi calculado pelo total do próprio relatório: (I) = (IV) − (II) − (III).
          </p>
        )}
        {liquidez && Number(liquidez.percentual) < 0 && (
          <p className="nota">
            Caixa líquido negativo nos recursos não vinculados: as obrigações a pagar com recursos
            livres superam o caixa livre no fim do ano.
          </p>
        )}
      </div>

      <Evolucao cod={cod} />
    </section>
  );
}
