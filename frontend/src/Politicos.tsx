import { useEffect, useState } from "react";
import { buscarMunicipios, type Municipio } from "./api";
import { AUDITORIA_ATIVA, urlAuditoria } from "./dados";
import {
  CARGOS,
  FONTES,
  hrefPolitico,
  listarPresencas,
  listarProposicoes,
  listarVotacoes,
  obterEmendas,
  obterCota,
  obterEmendasMunicipio,
  obterEleito,
  obterPolitico,
  obterRepresentantes,
  type Contagem,
  type ContagemValor,
  type Cota,
  type Emendas,
  type Fonte,
  type Lista,
  type PoliticoDetalhe,
  type Presenca,
  type Proposicao,
  type Representantes,
  type Votacao,
} from "./apiPoliticos";

// Princípios desta tela: só fatos com fonte, sem notas nem adjetivos, ordem alfabética.

const REPO = "https://github.com/fasn98/rastro-publico";

const data = (iso: string | null) =>
  iso ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("pt-BR") : "—";
const dataHora = (iso: string) => new Date(iso).toLocaleString("pt-BR");
const reais = (v: string | null) =>
  v === null ? "—" : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const inteiro = (n: number) => n.toLocaleString("pt-BR");

/** Ícone de fonte: link para a fonte oficial + cópia arquivada (pelo SHA-256 do conteúdo)
 * e a data em que esse conteúdo foi recebido pela primeira vez. */
export function LinkFonte({ url, sha256, recebidoEm }: {
  url: string;
  sha256?: string | null;
  recebidoEm?: string | null;
}) {
  return (
    <span className="fonte">
      <a href={url} target="_blank" rel="noreferrer" title={url} aria-label={`Fonte oficial: ${url}`}>
        <span aria-hidden="true">↗</span> fonte
      </a>
      {sha256 && AUDITORIA_ATIVA ? (
        <>
          {" · "}
          <a
            href={urlAuditoria(`/api/bruto/${sha256}`)}
            target="_blank"
            rel="noreferrer"
            title={`SHA-256 ${sha256}`}
            aria-label={`Cópia arquivada (SHA-256 ${sha256.slice(0, 12)}…)`}
          >
            cópia arquivada
          </a>
        </>
      ) : null}
      {recebidoEm && <span className="coleta"> · recebido em {dataHora(recebidoEm)}</span>}
    </span>
  );
}

function Fontes({ fontes }: { fontes: Fonte[] }) {
  if (!fontes.length) return null;
  return (
    <span className="fontes">
      {fontes.map((f) => (
        <LinkFonte key={`${f.url}-${f.sha256}`} url={f.url} sha256={f.sha256} recebidoEm={f.recebido_em} />
      ))}
    </span>
  );
}

function linkContestar(titulo: string) {
  const corpo = [
    `Página: ${location.href}`,
    "",
    "Qual dado está diferente da fonte oficial?",
    "",
    "Link da fonte oficial que mostra o valor correto:",
    "",
  ].join("\n");
  const qs = new URLSearchParams({ title: `Contestação: ${titulo}`, body: corpo, labels: "contestacao" });
  return `${REPO}/issues/new?${qs}`;
}

export function Contestar({ titulo }: { titulo: string }) {
  return (
    <p className="contestar">
      <a href={linkContestar(titulo)} target="_blank" rel="noreferrer">
        Contestar um dado
      </a>{" "}
      <span className="sub">(abre uma issue pública no repositório do projeto)</span>
    </p>
  );
}

// ------------------------------------------------------------- Quem representa você

export function QuemRepresenta({ cod }: { cod: number | null }) {
  const [busca, setBusca] = useState("");
  const [municipios, setMunicipios] = useState<Municipio[]>([]);
  const [rep, setRep] = useState<Representantes | null>(null);
  const [emendas, setEmendas] = useState<Emendas | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      buscarMunicipios("SP", busca.trim().length >= 2 ? busca.trim() : "")
        .then((r) => setMunicipios(r.itens))
        .catch((e: Error) => setErro(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [busca]);

  useEffect(() => {
    setRep(null);
    setEmendas(null);
    if (cod === null) return;
    obterRepresentantes(cod).then(setRep).catch((e: Error) => setErro(e.message));
    obterEmendasMunicipio(cod).then(setEmendas).catch((e: Error) => setErro(e.message));
  }, [cod]);

  return (
    <section className="politicos">
      <h2>Quem representa você</h2>
      <p className="sub">
        Escolha um município de SP para ver quem ocupa cada cargo, segundo as fontes oficiais.
        Listas em ordem alfabética.
      </p>
      <div className="filtros">
        <input
          placeholder="Buscar município de SP"
          aria-label="Buscar município de SP"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <select
          aria-label="Município"
          value={cod ?? ""}
          onChange={(e) => (location.hash = e.target.value ? `#/representantes/${e.target.value}` : "#/representantes")}
        >
          <option value="">Selecione o município</option>
          {municipios.map((m) => (
            <option key={m.cod_ibge} value={m.cod_ibge}>
              {m.nome}
            </option>
          ))}
        </select>
      </div>
      {erro && <p className="erro">{erro}</p>}

      {rep && (
        <>
          <h3>
            {rep.municipio.nome} / {rep.municipio.uf}
          </h3>
          {emendas?.publicadas && emendas.por_parlamentar.length > 0 && (
            <section className="destaque-emendas" aria-labelledby="emendas-destino">
              <h4 id="emendas-destino">Parlamentares que destinaram emendas a este município</h4>
              <p className="sub">
                Emendas com {rep.municipio.nome} como local do gasto, segundo o Portal da
                Transparência. Ordem alfabética.
              </p>
              <div className="tabela-rolagem">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Parlamentar</th>
                      <th scope="col">Emendas</th>
                      <th scope="col">Empenhado</th>
                      <th scope="col">Liquidado</th>
                      <th scope="col">Pago</th>
                    </tr>
                  </thead>
                  <tbody>
                    {emendas.por_parlamentar.map((x) => (
                      <tr key={`${x.politico_id}-${x.nome_autor}`}>
                        <th scope="row">
                          {x.politico_id ? <a href={`#/politico/${x.politico_id}`}>{x.nome_autor}</a> : x.nome_autor}
                          {x.partido && <span className="sub"> {x.partido}</span>}
                          {x.nota_vinculo && (
                            <div className="rotulo-vinculo">
                              {x.nota_vinculo}. Na fonte: “{x.nome_fonte}”
                            </div>
                          )}
                        </th>
                        <td>{inteiro(x.quantidade)}</td>
                        <td>{reais(x.valor_empenhado)}</td>
                        <td>{reais(x.valor_liquidado)}</td>
                        <td>{reais(x.valor_pago)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {rep.secoes.map((sec, i) => (
            <section key={sec.titulo} className="secao-representantes" aria-labelledby={`secao-${i}`}>
              <h3 id={`secao-${i}`}>{sec.titulo}</h3>
              {sec.nota && <p className="nota">{sec.nota}</p>}
              {sec.grupos.map((g) => (
                <div key={g.cargo} className="grupo-cargo">
                  <h4>
                    {CARGOS[g.cargo] ?? g.cargo}
                    {g.politicos.length > 0 && <span className="sub"> ({g.politicos.length})</span>}
                  </h4>
                  {g.pendente ? (
                    <p className="pendente">
                      {g.pendente}
                      {g.pendente_url && (
                        <>
                          {" "}
                          <a href={g.pendente_url} target="_blank" rel="noreferrer">
                            Arquivo de origem
                          </a>
                        </>
                      )}
                    </p>
                  ) : (
                    <ul className="lista">
                      {g.politicos.map((p) => (
                        <li key={p.id}>
                          <a className="cartao-link" href={hrefPolitico(p)}>
                            {p.nome} <span>{p.partido ?? "sem partido informado"}</span>
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </section>
          ))}

          <h3>Emendas recebidas</h3>
          {emendas && <TabelaEmendas emendas={emendas} mostrarAutor />}
          <Contestar titulo={`representantes de ${rep.municipio.nome}/${rep.municipio.uf}`} />
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------- Página do político

function anosDe(...listas: Contagem[][]): number[] {
  return [...new Set(listas.flat().map((c) => c.ano))].sort((a, b) => b - a);
}

function somar(lista: Contagem[], ano: number | null) {
  const sel = lista.filter((c) => ano === null || c.ano === ano);
  return { quantidade: sel.reduce((s, c) => s + c.quantidade, 0), fontes: sel.flatMap((c) => c.fontes) };
}

function Tile({ rotulo, lista, ano }: { rotulo: string; lista: Contagem[]; ano: number | null }) {
  const { quantidade, fontes } = somar(lista, ano);
  return (
    <div className="tile">
      <span className="tile-rotulo">{rotulo}</span>
      <span className="tile-valor">{inteiro(quantidade)}</span>
      <Fontes fontes={fontes} />
    </div>
  );
}

export function PaginaPolitico({ id, eleito }: { id: number; eleito?: string }) {
  const [p, setP] = useState<PoliticoDetalhe | null>(null);
  const [ano, setAno] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setP(null);
    setAno(null);
    (eleito ? obterEleito(eleito, id) : obterPolitico(id)).then(setP).catch((e: Error) => setErro(e.message));
  }, [id, eleito]);

  if (erro) return <p className="erro">{erro}</p>;
  if (!p) return <p className="sub">Carregando…</p>;

  const anos = anosDe(p.proposicoes, p.votacoes, p.presencas, p.cota);
  const federal = p.fonte === "camara" || p.fonte === "senado";
  const votos: Record<string, number> = {};
  for (const c of p.votacoes)
    if (ano === null || c.ano === ano)
      for (const [v, n] of Object.entries(c.por_voto)) votos[v] = (votos[v] ?? 0) + n;

  return (
    <article className="politicos detalhe">
      <h2>{p.nome}</h2>
      <dl>
        <dt>Cargo</dt>
        <dd>
          {CARGOS[p.cargo] ?? p.cargo} — {p.uf}
        </dd>
        <dt>Partido</dt>
        <dd>{p.partido ?? "—"}</dd>
        {p.situacao && p.fonte !== "tse" && (
          <>
            <dt>Situação</dt>
            <dd>{p.situacao}</dd>
          </>
        )}
        <dt>Em exercício</dt>
        <dd>{p.em_exercicio === null ? "—" : p.em_exercicio ? "Sim" : "Não"}</dd>
        {p.fonte === "tse" && (
          <>
            <dt>Eleição</dt>
            <dd>
              {p.eleicao_ano}
              {p.eleicao_ano && p.eleicao_ano >= 2026 && " (mandato a partir de 2027)"}
            </dd>
            <dt>Situação no arquivo do TSE</dt>
            <dd>
              {p.situacao}
              {p.situacao_candidatura && ` · candidatura: ${p.situacao_candidatura}`}
            </dd>
            {p.data_divulgacao && (
              <>
                <dt>Arquivo gerado pelo TSE em</dt>
                <dd>{data(p.data_divulgacao)}</dd>
              </>
            )}
          </>
        )}
        {p.legislatura && (
          <>
            <dt>Legislatura</dt>
            <dd>{p.legislatura}ª</dd>
          </>
        )}
        {(p.mandato_inicio || p.mandato_fim) && (
          <>
            <dt>Mandato</dt>
            <dd>
              {data(p.mandato_inicio)} a {data(p.mandato_fim)}
            </dd>
          </>
        )}
        <dt>Fonte</dt>
        <dd>
          {FONTES[p.fonte]}:{" "}
          <LinkFonte
            url={p.fonte_registro?.url ?? p.url_fonte}
            sha256={p.fonte_registro?.sha256 ?? p.sha256}
            recebidoEm={p.fonte_registro?.recebido_em}
          />
          {p.url_pagina && (
            <>
              {" · "}
              <a href={p.url_pagina} target="_blank" rel="noreferrer">
                página oficial
              </a>
            </>
          )}
        </dd>
      </dl>
      <Contestar titulo={`${p.nome} (${CARGOS[p.cargo] ?? p.cargo}, id ${p.id})`} />

      {p.linha_do_tempo.length > 0 && <LinhaDoTempo periodos={p.linha_do_tempo} />}

      {federal && (
        <>
          <div className="filtros">
            <label>
              Ano{" "}
              <select
                value={ano ?? ""}
                onChange={(e) => setAno(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Todos os anos coletados</option>
                {anos.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="tiles">
            <Tile
              rotulo={p.fonte === "senado" ? "Matérias com o(a) senador(a) entre os autores" : "Proposições com o(a) deputado(a) entre os autores"}
              lista={p.proposicoes}
              ano={ano}
            />
            <Tile rotulo="Votos registrados em votações nominais" lista={p.votacoes} ano={ano} />
            {p.fonte === "camara" && (
              <Tile rotulo="Presenças registradas em eventos da Câmara" lista={p.presencas} ano={ano} />
            )}
            {p.fonte === "camara" && <TileCota lista={p.cota} ano={ano} />}
          </div>
          {Object.keys(votos).length > 0 && (
            <div className="tabela-rolagem">
              <table aria-label="Votos por tipo, como registrados na fonte">
                <caption className="sub">Votos por tipo, como registrados na fonte</caption>
                <thead>
                  <tr>
                    <th scope="col">Voto</th>
                    <th scope="col">Quantidade</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(votos)
                    .sort(([a], [b]) => a.localeCompare(b, "pt-BR"))
                    .map(([v, n]) => (
                      <tr key={v}>
                        <th scope="row">
                          {v || "(sem valor na fonte)"}
                          {p.descricao_votos[v] && <span className="sub"> — {p.descricao_votos[v]}</span>}
                        </th>
                        <td>{inteiro(n)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
          <Listas p={p} ano={ano} camara={p.fonte === "camara"} />
          {p.comissoes.length > 0 && (
            <details>
              <summary>Comissões ({p.comissoes.length})</summary>
              <ul>
                {p.comissoes.map((c) => (
                  <li key={`${c.sigla}-${c.data_inicio}`}>
                    {c.sigla} — {c.nome} ({c.casa}) · {c.participacao} · {data(c.data_inicio)} a{" "}
                    {c.data_fim ? data(c.data_fim) : "atual"}{" "}
                    <LinkFonte url={c.url_fonte} sha256={c.sha256} />
                  </li>
                ))}
              </ul>
            </details>
          )}
          {p.fonte === "camara" && p.cota.length > 0 && <CotaDetalhe p={p} ano={ano} />}
          <h3>Emendas parlamentares</h3>
          <EmendasDoPolitico p={p} ano={ano} />
        </>
      )}
      <p className="nota">Somente fatos registrados nas fontes oficiais, sem notas nem classificações.</p>
    </article>
  );
}

function LinhaDoTempo({ periodos }: { periodos: PoliticoDetalhe["linha_do_tempo"] }) {
  return (
    <section className="linha-do-tempo" aria-labelledby="titulo-mandato">
      <h3 id="titulo-mandato">Linha do tempo do mandato (legislatura 2023–2027)</h3>
      <p className="nota">
        Exercício, licença, suplência e afastamentos segundo o histórico oficial da Câmara, com o
        motivo exatamente como está na fonte. Leia proposições, votos, presenças e emendas com
        este contexto: fora do exercício, o parlamentar não vota nem registra presença.
      </p>
      <div className="tabela-rolagem">
        <table>
          <thead>
            <tr>
              <th scope="col">De</th>
              <th scope="col">Até</th>
              <th scope="col">Situação</th>
              <th scope="col">Motivo (como na fonte)</th>
            </tr>
          </thead>
          <tbody>
            {periodos.map((x) => (
              <tr key={x.inicio + (x.descricao_status ?? "")}>
                <td>{data(x.inicio)}</td>
                <td>{x.fim ? data(x.fim) : "atual"}</td>
                <td className="esq">
                  {x.situacao}
                  {x.condicao_eleitoral && <span className="sub"> ({x.condicao_eleitoral})</span>}
                </td>
                <td className="esq">{x.descricao_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {periodos[0] && <LinkFonte url={periodos[0].url_fonte} sha256={periodos[0].sha256} />}
    </section>
  );
}

function TileCota({ lista, ano }: { lista: ContagemValor[]; ano: number | null }) {
  const sel = lista.filter((c) => ano === null || c.ano === ano);
  const total = sel.reduce((s, c) => s + Number(c.valor_liquido), 0);
  return (
    <div className="tile">
      <span className="tile-rotulo">Cota parlamentar: valor líquido das despesas</span>
      <span className="tile-valor">{reais(String(total))}</span>
      <span className="sub">{inteiro(sel.reduce((s, c) => s + c.quantidade, 0))} lançamentos</span>
      <Fontes fontes={sel.flatMap((c) => c.fontes)} />
    </div>
  );
}

function Mais({ lista, carregar }: { lista: Lista<unknown> | null; carregar: () => void }) {
  if (!lista) return null;
  return (
    <p className="nota">
      Mostrando {inteiro(lista.itens.length)} de {inteiro(lista.total)}.
      {lista.mais && (
        <>
          {" "}
          <button type="button" onClick={carregar}>
            Carregar mais
          </button>
        </>
      )}
    </p>
  );
}

function CotaDetalhe({ p, ano }: { p: PoliticoDetalhe; ano: number | null }) {
  const [aberto, setAberto] = useState(false);
  const [paginas, setPaginas] = useState(1);
  const [c, setC] = useState<Cota | null>(null);
  useEffect(() => {
    setC(null);
    setPaginas(1);
  }, [p.id, ano]);
  useEffect(() => {
    if (aberto) obterCota(p, ano, paginas).then(setC);
  }, [aberto, p, ano, paginas]);
  const resumidos = c?.anos.filter((a) => !a.detalhada) ?? [];
  return (
    <details onToggle={(e) => e.currentTarget.open && setAberto(true)}>
      <summary>Cota parlamentar por categoria e lançamentos</summary>
      {c && (
        <>
          <div className="tabela-rolagem">
            <table aria-label="Cota parlamentar por categoria">
              <thead>
                <tr>
                  <th scope="col">Categoria (como na fonte)</th>
                  <th scope="col">Lançamentos</th>
                  <th scope="col">Valor líquido</th>
                </tr>
              </thead>
              <tbody>
                {c.por_categoria.map((x) => (
                  <tr key={x.categoria}>
                    <th scope="row">{x.categoria}</th>
                    <td>{inteiro(x.quantidade)}</td>
                    <td>{reais(x.valor_liquido)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {resumidos.map((a) => (
            <p key={a.ano} className="nota aviso-cota">
              {a.ano}: {a.aviso}:{" "}
              <a href={a.url_oficial} target="_blank" rel="noreferrer">
                gastos do(a) deputado(a) em {a.ano}
              </a>{" "}
              ·{" "}
              <a href={a.url_busca_detalhada} target="_blank" rel="noreferrer">
                busca detalhada da cota
              </a>
              .
            </p>
          ))}
          {c.despesas.total > 0 && (
            <>
              <ul>
                {c.despesas.itens.map((x) => (
                  <li key={`${x.ano}-${x.linha}`}>
                    {String(x.mes).padStart(2, "0")}/{x.ano} · {x.categoria} ·{" "}
                    {x.pessoa_fisica ? "fornecedor pessoa física (nome não exibido)" : (x.fornecedor ?? "—")}
                    {x.cnpj && ` (CNPJ ${x.cnpj})`} · líquido {reais(x.valor_liquido)}
                    {x.url_documento && (
                      <>
                        {" "}
                        <a href={x.url_documento} target="_blank" rel="noreferrer">
                          documento
                        </a>
                      </>
                    )}{" "}
                    <LinkFonte url={x.url_fonte} sha256={x.sha256} />
                  </li>
                ))}
              </ul>
              <Mais lista={c.despesas} carregar={() => setPaginas((n) => n + 1)} />
            </>
          )}
        </>
      )}
    </details>
  );
}

function Listas({ p, ano, camara }: { p: PoliticoDetalhe; ano: number | null; camara: boolean }) {
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [paginas, setPaginas] = useState({ props: 1, vots: 1, pres: 1 });
  const [props, setProps] = useState<Lista<Proposicao> | null>(null);
  const [vots, setVots] = useState<Lista<Votacao> | null>(null);
  const [pres, setPres] = useState<Lista<Presenca> | null>(null);

  useEffect(() => {
    setProps(null);
    setVots(null);
    setPres(null);
    setPaginas({ props: 1, vots: 1, pres: 1 });
  }, [p.id, ano]);
  useEffect(() => {
    if (abertos.has("props")) listarProposicoes(p, ano, paginas.props).then(setProps);
  }, [abertos, p, ano, paginas.props]);
  useEffect(() => {
    if (abertos.has("vots")) listarVotacoes(p, ano, paginas.vots).then(setVots);
  }, [abertos, p, ano, paginas.vots]);
  useEffect(() => {
    if (abertos.has("pres")) listarPresencas(p, ano, paginas.pres).then(setPres);
  }, [abertos, p, ano, paginas.pres]);

  const alternar = (k: string) => (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    if (e.currentTarget.open) setAbertos((a) => new Set(a).add(k));
  };
  const mais = (k: keyof typeof paginas) => () => setPaginas((x) => ({ ...x, [k]: x[k] + 1 }));

  return (
    <>
      <details onToggle={alternar("props")}>
        <summary>Lista de proposições</summary>
        {props && (
          <ul>
            {props.itens.map((x) => (
              <li key={x.id_fonte}>
                <strong>
                  {x.sigla_tipo} {x.numero}/{x.ano}
                </strong>{" "}
                ({data(x.data_apresentacao)}) — {x.ementa}{" "}
                <LinkFonte url={x.url_pagina ?? x.url_fonte} sha256={x.sha256} />
              </li>
            ))}
          </ul>
        )}
        <Mais lista={props} carregar={mais("props")} />
      </details>
      <details onToggle={alternar("vots")}>
        <summary>Lista de votos</summary>
        {vots && (
          <ul>
            {vots.itens.map((x) => (
              <li key={x.id_votacao}>
                {data(x.data)} · {x.orgao ?? ""} {x.materia ?? ""} — voto: <strong>{x.voto || "(sem valor na fonte)"}</strong>
                {x.voto_descricao && ` (${x.voto_descricao})`}
                {x.descricao && <div className="sub">{x.descricao}</div>}
                <LinkFonte url={x.url_fonte} sha256={x.sha256} />
              </li>
            ))}
          </ul>
        )}
        <Mais lista={vots} carregar={mais("vots")} />
      </details>
      {camara && (
        <details onToggle={alternar("pres")}>
          <summary>Lista de presenças registradas</summary>
          {pres && (
            <ul>
              {pres.itens.map((x) => (
                <li key={x.id_evento}>
                  {dataHora(x.data_hora_inicio)} · evento {x.id_evento}{" "}
                  <LinkFonte url={x.url_fonte} sha256={x.sha256} />
                </li>
              ))}
            </ul>
          )}
          <Mais lista={pres} carregar={mais("pres")} />
        </details>
      )}
    </>
  );
}

function EmendasDoPolitico({ p, ano }: { p: PoliticoDetalhe; ano: number | null }) {
  const [e, setE] = useState<Emendas | null>(null);
  useEffect(() => {
    obterEmendas(p, ano).then(setE);
  }, [p, ano]);
  return e ? <TabelaEmendas emendas={e} /> : null;
}

function TabelaEmendas({ emendas, mostrarAutor = false }: { emendas: Emendas; mostrarAutor?: boolean }) {
  if (emendas.aviso) return <p className="pendente">{emendas.aviso}</p>;
  if (!emendas.itens.length) return <p className="sub">Nenhuma emenda encontrada na coleta.</p>;
  return (
    <>
      <div className="tabela-rolagem">
        <table aria-label="Totais de emendas por ano e tipo">
          <thead>
            <tr>
              <th scope="col">Ano</th>
              <th scope="col">Tipo</th>
              <th scope="col">Emendas</th>
              <th scope="col">Empenhado</th>
              <th scope="col">Liquidado</th>
              <th scope="col">Pago</th>
            </tr>
          </thead>
          <tbody>
            {emendas.totais.map((t) => (
              <tr key={`${t.ano}-${t.transferencia_especial}`}>
                <th scope="row">{t.ano}</th>
                <td>{t.transferencia_especial ? "Transferência especial" : "Demais emendas"}</td>
                <td>{inteiro(t.quantidade)}</td>
                <td>{reais(t.valor_empenhado)}</td>
                <td>{reais(t.valor_liquidado)}</td>
                <td>{reais(t.valor_pago)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Emendas ({emendas.itens.length})</summary>
        <ul>
          {emendas.itens.map((x) => (
            <li key={x.codigo_emenda}>
              {x.ano} · {x.numero_emenda} · {x.tipo_emenda}
              {(mostrarAutor || x.nota_vinculo) && ` · autor na fonte: “${x.nome_autor}”`}
              {x.nota_vinculo && <div className="rotulo-vinculo">{x.nota_vinculo}</div>} ·{" "}
              {x.localidade_gasto} · empenhado{" "}
              {reais(x.valor_empenhado)} → liquidado {reais(x.valor_liquidado)} → pago{" "}
              {reais(x.valor_pago)} <LinkFonte url={x.url_fonte} sha256={x.sha256} />
            </li>
          ))}
        </ul>
      </details>
    </>
  );
}
