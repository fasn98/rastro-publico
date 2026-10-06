"""Site estático: exporta tudo o que o visitante vê para arquivos JSON.

O site publicado (GitHub Pages) lê só estes arquivos; o banco não é consultado por
visitantes. Para que o site mostre exatamente o que a API mostraria, a exportação chama
as próprias rotas da API dentro do processo (sem servidor) e grava as respostas.

Estrutura gerada em `<saida>/`:

    manifesto.json                      data, coleta, versões da metodologia/mapeamento
    municipios.json                     lista para a busca (feita no navegador)
    municipios/{cod}.json               detalhe, série de indicadores, nota, emendas e a
                                        referência dos representantes do município
    representantes/{hash}.json          grupos de representantes (um arquivo por conteúdo
                                        distinto: os cargos estaduais/federais se repetem)
    ranking.json, ranking.csv           ranking fiscal da UF
    metodologia.json
    politicos/{id}.json                 detalhe do político
    politicos/{id}/{lista}/{ano}.json   proposicoes | votacoes | presencas | emendas,
                                        por ano ("todos" = sem filtro de ano)

Os únicos dados que continuam dinâmicos são os da auditoria (resposta bruta e verificação
do SHA-256), servidos pela API de auditoria.
"""

import hashlib
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro import mapeamento as mp
from rastro import ranking as rk
from rastro.models import Coleta, Municipio
from rastro.politicos.modelos import PolPolitico

log = logging.getLogger(__name__)

LISTAS_POLITICO = ("proposicoes", "votacoes", "presencas")
VERSAO_FORMATO = 1


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


class _Escritor:
    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.arquivos = 0
        self.bytes = 0

    def json(self, caminho: str, dados) -> None:
        conteudo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode()
        self.bruto(caminho, conteudo)

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
        politicos = s.scalars(
            select(PolPolitico.id).where(PolPolitico.uf == uf).order_by(PolPolitico.id)
        ).all()
        ultima_coleta = s.scalar(
            select(func.max(Coleta.finalizada_em)).where(Coleta.status.in_(["sucesso", "parcial"]))
        )
    finally:
        if session is None:
            s.close()

    lista = []
    grupos_gravados: set[str] = set()
    for m in municipios:
        cod = m.cod_ibge
        detalhe = get(f"/api/municipios/{cod}")
        lista.append({k: v for k, v in detalhe.items() if k != "ente_siconfi"})
        # os grupos de representantes estaduais/federais são iguais para todos os municípios
        # da UF: cada conteúdo distinto vira um arquivo só, nomeado pelo hash
        rep = get(f"/api/municipios/{cod}/representantes")
        grupos = json.dumps(rep["grupos"], ensure_ascii=False, separators=(",", ":")).encode()
        ref = f"representantes/{hashlib.sha256(grupos).hexdigest()[:16]}.json"
        if ref not in grupos_gravados:
            out.bruto(ref, grupos)
            grupos_gravados.add(ref)
        out.json(
            f"municipios/{cod}.json",
            {
                "detalhe": detalhe,
                "serie": get(f"/api/entes/{cod}/indicadores/serie"),
                "nota": get(f"/api/ranking/{cod}", opcional=True),
                "representantes": {"municipio": rep["municipio"], "grupos_ref": ref},
                "emendas": get(f"/api/municipios/{cod}/emendas"),
            },
        )
    out.json("municipios.json", lista)

    ranking = get(f"/api/ranking?uf={uf}", opcional=True)
    if ranking:
        out.json("ranking.json", ranking)
        out.bruto("ranking.csv", api.get(f"/api/ranking.csv?uf={uf}").content)
    out.json("metodologia.json", get("/api/metodologia"))

    for pid in politicos:
        detalhe = get(f"/api/politicos/{pid}")
        out.json(f"politicos/{pid}.json", detalhe)
        anos = sorted({c["ano"] for k in LISTAS_POLITICO for c in detalhe.get(k, [])}, reverse=True)
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
    políticos não pode cair (uma coleta incompleta não pode apagar dados do site).
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
    municipios = json.loads((saida / "municipios.json").read_text())
    faltando = [
        m["cod_ibge"]
        for m in municipios
        if not (saida / "municipios" / f"{m['cod_ibge']}.json").exists()
    ]
    if faltando:
        problemas.append(f"{len(faltando)} municípios sem arquivo de detalhe")
    for obrigatorio in ("metodologia.json",):
        if not (saida / obrigatorio).exists():
            problemas.append(f"arquivo obrigatório ausente: {obrigatorio}")
    if anterior:
        for chave in ("municipios", "politicos"):
            antes = anterior.get("contagens", {}).get(chave, 0)
            agora = manifesto["contagens"].get(chave, 0)
            if agora < antes:
                problemas.append(f"{chave}: {agora} na nova versão, {antes} na publicada")
        if anterior.get("uf") and anterior["uf"] != manifesto["uf"]:
            problemas.append(f"UF mudou de {anterior['uf']} para {manifesto['uf']}")
    return problemas
