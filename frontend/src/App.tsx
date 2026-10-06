import { useEffect, useState } from "react";
import {
  buscarMunicipios,
  obterMunicipio,
  type Municipio,
  type MunicipioDetalhe,
  type Pagina,
} from "./api";
import Indicadores from "./Indicadores";

const UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
  "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
];

const formatarCnpj = (c: string) =>
  c.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");

export default function App() {
  const [uf, setUf] = useState("");
  const [nome, setNome] = useState("");
  const [resultado, setResultado] = useState<Pagina<Municipio> | null>(null);
  const [detalhe, setDetalhe] = useState<MunicipioDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!uf && nome.trim().length < 2) {
      setResultado(null);
      return;
    }
    const t = setTimeout(() => {
      buscarMunicipios(uf, nome.trim())
        .then((r) => {
          setResultado(r);
          setErro(null);
        })
        .catch((e: Error) => setErro(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [uf, nome]);

  const abrir = (cod: number) =>
    obterMunicipio(cod)
      .then(setDetalhe)
      .catch((e: Error) => setErro(e.message));

  return (
    <main>
      <h1>Rastro Público</h1>
      <p className="sub">Dados públicos de municípios brasileiros (IBGE e Tesouro/SICONFI)</p>

      <div className="filtros">
        <select value={uf} onChange={(e) => setUf(e.target.value)} aria-label="UF">
          <option value="">Todas as UFs</option>
          {UFS.map((u) => (
            <option key={u}>{u}</option>
          ))}
        </select>
        <input
          placeholder="Nome do município"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
        />
      </div>

      {erro && <p className="erro">{erro}</p>}

      {resultado && (
        <section>
          <p className="total">
            {resultado.total} município(s)
            {resultado.total > resultado.itens.length && `, mostrando ${resultado.itens.length}`}
          </p>
          <ul className="lista">
            {resultado.itens.map((m) => (
              <li key={m.cod_ibge}>
                <button onClick={() => abrir(m.cod_ibge)}>
                  {m.nome} <span>{m.uf}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {detalhe && (
        <aside className="detalhe">
          <h2>
            {detalhe.nome} / {detalhe.uf}
          </h2>
          <dl>
            <dt>Código IBGE</dt>
            <dd>{detalhe.cod_ibge}</dd>
            <dt>Região imediata</dt>
            <dd>{detalhe.regiao_imediata ?? "—"}</dd>
            <dt>Região intermediária</dt>
            <dd>{detalhe.regiao_intermediaria ?? "—"}</dd>
            {detalhe.ente_siconfi ? (
              <>
                <dt>População (SICONFI {detalhe.ente_siconfi.exercicio})</dt>
                <dd>{detalhe.ente_siconfi.populacao?.toLocaleString("pt-BR") ?? "—"}</dd>
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
          {detalhe.ente_siconfi && <Indicadores cod={detalhe.cod_ibge} />}
        </aside>
      )}
    </main>
  );
}
