import { useEffect, useId, useRef, useState } from "react";
import {
  arquivoMunicipio,
  obterMunicipio,
  sugerirMunicipios,
  todosMunicipios,
  type Municipio,
  type MunicipioDetalhe,
} from "./api";
import { AUDITORIA_ATIVA, urlAuditoria } from "./dados";
import Indicadores from "./Indicadores";
import { PrefeitosEleitos } from "./Politicos";

const formatarCnpj = (c: string) =>
  c.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");

const abrir = (c: number) => {
  location.hash = `#/municipio/${c}`;
};

/** Campo de busca com sugestões (padrão combobox do WAI-ARIA): setas, Enter e Esc. */
function BuscaMunicipio() {
  const id = useId();
  const [texto, setTexto] = useState("");
  const [sugestoes, setSugestoes] = useState<Municipio[]>([]);
  const [ativa, setAtiva] = useState(-1);
  const [aberta, setAberta] = useState(false);
  const campo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let atual = true;
    sugerirMunicipios(texto).then((s) => {
      if (!atual) return;
      setSugestoes(s);
      setAtiva(s.length ? 0 : -1);
    });
    return () => {
      atual = false;
    };
  }, [texto]);

  const escolher = (m: Municipio) => {
    setTexto("");
    setAberta(false);
    campo.current?.blur();
    abrir(m.cod_ibge);
  };

  const teclado = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAberta(true);
      setAtiva((i) => Math.min(i + 1, sugestoes.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setAtiva((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && aberta && sugestoes[ativa]) {
      e.preventDefault();
      escolher(sugestoes[ativa]);
    } else if (e.key === "Escape") {
      setAberta(false);
    }
  };

  const mostrar = aberta && texto.trim() !== "";
  return (
    <div className="busca">
      <label htmlFor={`${id}-campo`} className="busca-rotulo">
        Buscar município
      </label>
      <input
        id={`${id}-campo`}
        ref={campo}
        type="search"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={mostrar}
        aria-controls={`${id}-lista`}
        aria-activedescendant={mostrar && ativa >= 0 ? `${id}-op-${ativa}` : undefined}
        placeholder="Digite o nome, ex.: sao paulo"
        autoComplete="off"
        autoCapitalize="none"
        spellCheck={false}
        enterKeyHint="go"
        value={texto}
        onChange={(e) => {
          setTexto(e.target.value);
          setAberta(true);
        }}
        onFocus={() => setAberta(true)}
        onBlur={() => setTimeout(() => setAberta(false), 150)}
        onKeyDown={teclado}
      />
      {mostrar && (
        <ul id={`${id}-lista`} role="listbox" className="sugestoes" aria-label="Municípios encontrados">
          {sugestoes.length === 0 ? (
            <li className="sem-sugestao" role="option" aria-selected={false} aria-disabled>
              Nenhum município encontrado
            </li>
          ) : (
            sugestoes.map((m, i) => (
              <li
                key={m.cod_ibge}
                id={`${id}-op-${i}`}
                role="option"
                aria-selected={i === ativa}
                className={i === ativa ? "ativa" : undefined}
                // mousedown: escolhe antes de o campo perder o foco
                onMouseDown={(e) => {
                  e.preventDefault();
                  escolher(m);
                }}
                onMouseEnter={() => setAtiva(i)}
              >
                {m.nome} <span className="uf">{m.uf}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

/** Lista completa, recolhida: abre só quando pedida. */
function ListaCompleta() {
  const [aberta, setAberta] = useState(false);
  const [todos, setTodos] = useState<Municipio[] | null>(null);
  useEffect(() => {
    if (aberta && !todos) todosMunicipios().then(setTodos);
  }, [aberta, todos]);
  return (
    <details className="lista-completa" onToggle={(e) => setAberta(e.currentTarget.open)}>
      <summary>Lista completa de municípios{todos ? ` (${todos.length})` : ""}</summary>
      {!todos ? (
        <p className="sub">Carregando…</p>
      ) : (
        <ul className="lista">
          {todos.map((m) => (
            <li key={m.cod_ibge}>
              <a href={`#/municipio/${m.cod_ibge}`}>
                {m.nome} <span>{m.uf}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

function Populacao({ d }: { d: MunicipioDetalhe }) {
  const p = d.populacao_ibge;
  const siconfi = d.ente_siconfi;
  return (
    <>
      <dt>População</dt>
      <dd>
        {p ? (
          <>
            <strong className="populacao">{p.populacao.toLocaleString("pt-BR")}</strong>{" "}
            <span className="sub">
              estimativa do IBGE para {p.ano} · {p.fonte}
              {p.url_fonte && (
                <>
                  {" · "}
                  <a href={p.url_fonte} target="_blank" rel="noreferrer">
                    <span aria-hidden="true">↗</span> fonte
                  </a>
                </>
              )}
              {AUDITORIA_ATIVA && p.resposta_id && (
                <>
                  {" · "}
                  <a href={urlAuditoria(`/api/respostas/${p.resposta_id}/bruto`)} target="_blank" rel="noreferrer">
                    cópia arquivada
                  </a>
                </>
              )}
            </span>
          </>
        ) : (
          "Estimativa do IBGE ainda não coletada"
        )}
      </dd>
      {siconfi?.populacao != null && (
        <>
          <dt className="secundario">População informada pelo ente ao SICONFI ({siconfi.exercicio})</dt>
          <dd className="secundario">
            {siconfi.populacao.toLocaleString("pt-BR")}{" "}
            <span className="sub">só informativa: o portal usa a estimativa do IBGE</span>
          </dd>
        </>
      )}
    </>
  );
}

export default function Municipios({ cod }: { cod: number | null }) {
  const [detalhe, setDetalhe] = useState<MunicipioDetalhe | null>(null);
  const [comRepresentantes, setComRepresentantes] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // o município aberto fica na URL (#/municipio/3550308), para links diretos
  useEffect(() => {
    setErro(null);
    if (cod === null) {
      setDetalhe(null);
      return;
    }
    setDetalhe(null);
    setComRepresentantes(false);
    // fora da UF dos políticos o arquivo vem sem representantes (ADR-0020): sem link
    arquivoMunicipio(cod)
      .then((a) => setComRepresentantes(a.representantes !== null))
      .catch(() => setComRepresentantes(false));
    obterMunicipio(cod)
      .then((d) => {
        setDetalhe(d);
        // o conteúdo chega depois da troca de rota: volta ao topo de novo
        window.scrollTo(0, 0);
      })
      .catch((e: Error) => setErro(e.message));
  }, [cod]);

  return (
    <>
      <BuscaMunicipio />
      {erro && <p className="erro">{erro}</p>}
      {cod !== null && !detalhe && !erro && <p className="sub">Carregando…</p>}

      {detalhe && (
        <article className="detalhe" aria-labelledby="titulo-municipio">
          <h2 id="titulo-municipio">
            {detalhe.nome} / {detalhe.uf}
          </h2>
          <dl>
            <Populacao d={detalhe} />
            <dt>Código IBGE</dt>
            <dd>{detalhe.cod_ibge}</dd>
            <dt>Região imediata</dt>
            <dd>{detalhe.regiao_imediata ?? "—"}</dd>
            <dt>Região intermediária</dt>
            <dd>{detalhe.regiao_intermediaria ?? "—"}</dd>
            {detalhe.ente_siconfi ? (
              <>
                <dt>CNPJ</dt>
                <dd>
                  {detalhe.ente_siconfi.cnpj ? formatarCnpj(detalhe.ente_siconfi.cnpj) : "—"}
                </dd>
                <dt>Capital</dt>
                <dd>{detalhe.ente_siconfi.capital ? "Sim" : "Não"}</dd>
              </>
            ) : (
              <>
                <dt>SICONFI</dt>
                <dd>Sem cadastro como ente no SICONFI</dd>
              </>
            )}
          </dl>
          {comRepresentantes && (
            <p>
              <a href={`#/representantes/${detalhe.cod_ibge}`}>Representantes e emendas recebidas</a>
            </p>
          )}
          {detalhe.ente_siconfi && <Indicadores cod={detalhe.cod_ibge} />}
          <PrefeitosEleitos cod={detalhe.cod_ibge} municipio={`${detalhe.nome}/${detalhe.uf}`} />
        </article>
      )}

      {cod === null && <ListaCompleta />}
    </>
  );
}
