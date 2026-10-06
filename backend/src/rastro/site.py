"""Site estático: exporta tudo o que o visitante vê para arquivos JSON.

O site publicado (GitHub Pages) lê só estes arquivos; o banco não é consultado por
visitantes. Para que o site mostre exatamente o que a API mostraria, a exportação chama
as próprias rotas da API dentro do processo (sem servidor) e grava as respostas.

Estrutura gerada em `<saida>/`:

    manifesto.json                      data, coleta, versões da metodologia/mapeamento
    municipios.json                     lista para a busca (feita no navegador)
    municipios/{cod}.json               detalhe, série de indicadores, nota, emendas e os
                                        representantes do município
    representantes/{hash}.json          seção de representantes repetida em vários municípios
                                        (estado, federal, eleitos 2026): um arquivo por
                                        conteúdo distinto, referenciado como {"ref": ...}
    ranking.json, ranking.csv           ranking fiscal da UF
    metodologia.json
    politicos/{id}.json                 detalhe do político
    politicos/{id}/{lista}/{ano}.json   proposicoes | votacoes | presencas | cota | emendas,
                                        por ano ("todos" = sem filtro de ano)

Travas de publicação (`Settings.pol_publicar_*`): a exportação lê tudo pela API, que já
esconde o que está travado (políticos do TSE, eleitos 2026, emendas). O que a API não
mostra não entra no site; o estado das travas vai no manifesto.

Os únicos dados que continuam dinâmicos são os da auditoria (resposta bruta e verificação
do SHA-256), servidos pela API de auditoria.
"""

import hashlib
import json
import logging
import os
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro import mapeamento as mp
from rastro import ranking as rk
from rastro.config import get_settings
from rastro.models import Coleta, Municipio

log = logging.getLogger(__name__)

LISTAS_POLITICO = ("proposicoes", "votacoes", "presencas", "cota")
# listas que formam o seletor de ano da página do político
ANOS_POLITICO = LISTAS_POLITICO
VERSAO_FORMATO = 2


class ErroExportacao(RuntimeError):
    pass


def _cliente(session: Session | None) -> TestClient:
    from rastro.api.main import app
    from rastro.db import get_session

    if session is not None:
        app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def _commit_codigo() -> str | None:
    if os.environ.get("RASTRO_COMMIT"):
        return os.environ["RASTRO_COMMIT"]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _bytes(dados) -> bytes:
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode()


def _travas() -> dict[str, bool]:
    """Estado das travas de publicação no momento da exportação."""
    cfg = get_settings()
    return {k: v for k, v in cfg.model_dump().items() if k.startswith("pol_publicar_")}


class _Escritor:
    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.arquivos = 0
        self.bytes = 0

    def json(self, caminho: str, dados) -> None:
        self.bruto(caminho, _bytes(dados))

    def bruto(self, caminho: str, conteudo: bytes) -> None:
        destino = self.raiz / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        self.arquivos += 1
        self.bytes += len(conteudo)


def exportar(saida: Path, uf: str = "SP", session: Session | None = None) -> dict:
    """Gera os arquivos do site em `saida` e devolve o manifesto."""
    uf = uf.upper()
    api = _cliente(session)
    out = _Escritor(saida)

    def get(url: str, opcional: bool = False):
        r = api.get(url)
        if r.status_code == 404 and opcional:
            return None
        if r.status_code != 200:
            raise ErroExportacao(f"GET {url}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    from rastro.db import get_sessionmaker

    s = session or get_sessionmaker()()
    try:
        municipios = s.scalars(
            select(Municipio).where(Municipio.uf == uf).order_by(Municipio.nome)
        ).all()
        if not municipios:
            raise ErroExportacao(f"nenhum município de {uf} no banco")
        ultima_coleta = s.scalar(
            select(func.max(Coleta.finalizada_em)).where(Coleta.status.in_(["sucesso", "parcial"]))
        )
    finally:
        if session is None:
            s.close()

    # representantes: as seções de estado e federais são iguais em todos os municípios da
    # UF; cada seção que se repete vira um arquivo só, nomeado pelo hash do conteúdo
    reps = {m.cod_ibge: get(f"/api/municipios/{m.cod_ibge}/representantes") for m in municipios}
    vezes: Counter[bytes] = Counter(_bytes(sec) for rep in reps.values() for sec in rep["secoes"])
    secoes_gravadas: set[str] = set()

    def secao(sec: dict) -> dict:
        conteudo = _bytes(sec)
        if vezes[conteudo] < 2:
            return sec
        ref = f"representantes/{hashlib.sha256(conteudo).hexdigest()[:16]}.json"
        if ref not in secoes_gravadas:
            out.bruto(ref, conteudo)
            secoes_gravadas.add(ref)
        return {"ref": ref}

    lista = []
    citados: set[int] = set()
    for m in municipios:
        cod = m.cod_ibge
        detalhe = get(f"/api/municipios/{cod}")
        lista.append({k: v for k, v in detalhe.items() if k != "ente_siconfi"})
        rep = reps[cod]
        citados |= {p["id"] for sec in rep["secoes"] for g in sec["grupos"] for p in g["politicos"]}
        out.json(
            f"municipios/{cod}.json",
            {
                "detalhe": detalhe,
                "serie": get(f"/api/entes/{cod}/indicadores/serie"),
                "nota": get(f"/api/ranking/{cod}", opcional=True),
                "representantes": {
                    "municipio": rep["municipio"],
                    "secoes": [secao(sec) for sec in rep["secoes"]],
                },
                "emendas": get(f"/api/municipios/{cod}/emendas"),
            },
        )
    out.json("municipios.json", lista)

    # só os políticos que a API mostra (travas aplicadas), mais os citados nas páginas
    politicos: set[int] = set(citados)
    deslocamento = 0
    while True:
        pagina = get(f"/api/politicos?uf={uf}&limite=500&deslocamento={deslocamento}")
        politicos |= {p["id"] for p in pagina["itens"]}
        deslocamento += len(pagina["itens"])
        if not pagina["itens"] or deslocamento >= pagina["total"]:
            break

    ranking = get(f"/api/ranking?uf={uf}", opcional=True)
    if ranking:
        out.json("ranking.json", ranking)
        out.bruto("ranking.csv", api.get(f"/api/ranking.csv?uf={uf}").content)
    out.json("metodologia.json", get("/api/metodologia"))

    for pid in sorted(politicos):
        detalhe = get(f"/api/politicos/{pid}")
        out.json(f"politicos/{pid}.json", detalhe)
        anos = sorted({c["ano"] for k in ANOS_POLITICO for c in detalhe.get(k, [])}, reverse=True)
        for ano in [None, *anos]:
            nome_ano = "todos" if ano is None else str(ano)
            filtro = "" if ano is None else f"&ano={ano}"
            for lista_nome in LISTAS_POLITICO:
                out.json(
                    f"politicos/{pid}/{lista_nome}/{nome_ano}.json",
                    get(f"/api/politicos/{pid}/{lista_nome}?limite=500{filtro}"),
                )
            out.json(
                f"politicos/{pid}/emendas/{nome_ano}.json",
                get(f"/api/politicos/{pid}/emendas?{filtro.lstrip('&')}"),
            )

    met = rk.carregar_metodologia()
    mapa = mp.padrao()
    manifesto = {
        "formato": VERSAO_FORMATO,
        "gerado_em": datetime.now(UTC).isoformat(),
        "uf": uf,
        "ultima_coleta": ultima_coleta.isoformat() if ultima_coleta else None,
        "codigo": _commit_codigo(),
        "metodologia": {"versao": met.versao, "hash": met.hash},
        "mapeamento": {"versao": mapa.versao, "hash": mapa.hash},
        "travas": _travas(),
        "contagens": {
            "municipios": len(municipios),
            "municipios_com_nota": sum(1 for i in (ranking or {}).get("itens", []) if i["nota"]),
            "politicos": len(politicos),
        },
        "arquivos": out.arquivos + 1,
        "bytes": out.bytes,
    }
    out.json("manifesto.json", manifesto)
    log.info(
        "Site exportado em %s: %d arquivos, %.1f MB",
        saida, manifesto["arquivos"], out.bytes / 1e6,
    )  # fmt: skip
    return manifesto


def verificar(saida: Path, anterior: dict | None = None) -> list[str]:
    """Problemas que impedem publicar (lista vazia = pode publicar).

    `anterior` é o manifesto da publicação em vigor: o número de municípios e de
    políticos não pode cair (uma coleta incompleta não pode apagar dados do site), a menos
    que uma trava de publicação tenha mudado de propósito.
    """
    problemas = []
    try:
        manifesto = json.loads((saida / "manifesto.json").read_text())
    except (OSError, ValueError) as exc:
        return [f"manifesto ausente ou inválido: {exc}"]
    for arq in saida.rglob("*.json"):
        try:
            json.loads(arq.read_bytes())
        except ValueError as exc:
            problemas.append(f"JSON inválido: {arq.relative_to(saida)} ({exc})")
    if problemas:
        return problemas
    municipios = json.loads((saida / "municipios.json").read_text())
    faltando, refs_quebradas, citados = [], set(), set()
    for m in municipios:
        arq = saida / "municipios" / f"{m['cod_ibge']}.json"
        if not arq.exists():
            faltando.append(m["cod_ibge"])
            continue
        for sec in json.loads(arq.read_bytes())["representantes"]["secoes"]:
            if "ref" in sec:
                if not (saida / sec["ref"]).exists():
                    refs_quebradas.add(sec["ref"])
                    continue
                sec = json.loads((saida / sec["ref"]).read_bytes())
            citados |= {p["id"] for g in sec["grupos"] for p in g["politicos"]}
    if faltando:
        problemas.append(f"{len(faltando)} municípios sem arquivo de detalhe")
    if refs_quebradas:
        problemas.append(f"seções de representantes ausentes: {sorted(refs_quebradas)}")
    sem_pagina = sorted(i for i in citados if not (saida / "politicos" / f"{i}.json").exists())
    if sem_pagina:
        problemas.append(f"{len(sem_pagina)} políticos citados sem página: {sem_pagina[:10]}")
    problemas += _conferir_travas(saida, manifesto.get("travas", {}))
    for obrigatorio in ("metodologia.json",):
        if not (saida / obrigatorio).exists():
            problemas.append(f"arquivo obrigatório ausente: {obrigatorio}")
    if anterior:
        mesmas_travas = anterior.get("travas") == manifesto.get("travas")
        for chave in ("municipios", "politicos"):
            if chave == "politicos" and not mesmas_travas:
                continue  # ligar/desligar uma trava muda o número de políticos de propósito
            antes = anterior.get("contagens", {}).get(chave, 0)
            agora = manifesto["contagens"].get(chave, 0)
            if agora < antes:
                problemas.append(f"{chave}: {agora} na nova versão, {antes} na publicada")
        if anterior.get("uf") and anterior["uf"] != manifesto["uf"]:
            problemas.append(f"UF mudou de {anterior['uf']} para {manifesto['uf']}")
    return problemas


def _conferir_travas(saida: Path, travas: dict) -> list[str]:
    """Segunda barreira: nada que uma trava desligada esconde pode estar nos arquivos."""
    from rastro.politicos.publicacao import ELEICOES_FUTURAS

    problemas = []
    if not travas:
        return ["manifesto sem o estado das travas de publicação"]
    for arq in (saida / "politicos").glob("*.json"):
        p = json.loads(arq.read_bytes())
        if p.get("fonte") != "tse":
            continue
        futura = p.get("eleicao_ano") in ELEICOES_FUTURAS
        trava = "pol_publicar_tse_2026" if futura else "pol_publicar_tse"
        if not travas.get(trava):
            problemas.append(f"{arq.name}: eleito do TSE exportado com {trava} desligada")
    if not travas.get("pol_publicar_emendas"):
        arquivos = [
            *(saida / "politicos").glob("*/emendas/*.json"),
            *(saida / "municipios").glob("*.json"),
        ]
        for arq in arquivos:
            dados = json.loads(arq.read_bytes())
            e = dados.get("emendas", dados) if arq.parent.name == "municipios" else dados
            if e.get("publicadas") or e.get("itens") or e.get("totais"):
                problemas.append(
                    f"{arq.relative_to(saida)}: emendas exportadas com pol_publicar_emendas "
                    "desligada"
                )
    return problemas
