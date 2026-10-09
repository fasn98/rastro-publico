"""Site estático: exporta tudo o que o visitante vê para arquivos JSON.

O site publicado (GitHub Pages) lê só estes arquivos; o banco não é consultado por
visitantes. Para que o site mostre exatamente o que a API mostraria, a exportação chama
as próprias rotas da API dentro do processo (sem servidor) e grava as respostas.

Estrutura gerada em `<saida>/` (formato 3):

    manifesto.json                      data, coleta, versões, travas e contagens (lido pelo site)
    indice.json                         SHA-256 de cada arquivo e impressão digital de cada
                                        grupo (exportação incremental e verificação)
    municipios.json                     lista para a busca (feita no navegador)
    municipios/{cod}.json               detalhe, série de indicadores, nota, emendas, os
                                        representantes e os prefeitos eleitos do município
    representantes/{hash}.json          seção de representantes repetida em vários municípios
                                        (estado, federal, eleitos 2026): um arquivo por
                                        conteúdo distinto, referenciado como {"ref": ...}
    ranking.json, ranking.csv           ranking fiscal da UF
    metodologia.json
    politicos/{id}.json                 detalhe do deputado/senador
    politicos/{id}/{lista}/{ano}-{n}.json
                                        proposicoes | votacoes | presencas | cota: página n
                                        (500 itens) do ano; nenhuma lista é cortada
    politicos/{id}/cota/{ano}.json      totais por categoria do ano; lançamentos item a item
                                        só no ano corrente e no anterior
    politicos/{id}/emendas/{ano}.json   emendas do ano (sem limite de itens)
    catalogos/{lista}/{casa}/{ano}.json dados de cada votação/evento que são iguais para todos
                                        os parlamentares (data, órgão, matéria, fonte); a
                                        página do político guarda só o id e o voto
    eleitos/m-{cod}.json                eleitos do TSE no município (prefeito e vereadores)
    eleitos/uf-{UF}-{ano}.json          eleitos do TSE para cargos estaduais/federais da UF

Listas compactas: campos com o mesmo valor em todos os itens ficam em "comum"; campos
de texto que se repetem muito ficam em "indices" (o item guarda a posição na lista).

Fontes: cada item aponta para o SHA-256 do conteúdo arquivado (`sha256`), não para o id
interno da resposta; a data é a do primeiro recebimento daquele conteúdo. Assim o arquivo
só muda quando a fonte muda, e a cópia é aberta na API de auditoria em /api/bruto/{sha256}.

Exportação incremental: a saída é JSON determinístico. Cada político federal e cada
arquivo de eleitos é um grupo com uma impressão digital calculada no banco (linhas que o
alimentam, sem ids e datas de gravação) mais o formato, as travas, as exceções de emendas
e o código do exportador. Grupo com a mesma impressão da exportação anterior reaproveita
os arquivos já gravados; os demais arquivos são recalculados e só regravados se mudarem.

Travas de publicação (`Settings.pol_publicar_*`): a exportação lê tudo pela API, que já
esconde o que está travado (políticos do TSE, eleitos 2026, emendas). O que a API não
mostra não entra no site; o estado das travas vai no manifesto.

Os únicos dados que continuam dinâmicos são os da auditoria (resposta bruta e verificação
do SHA-256), servidos pela API de auditoria.
"""

import hashlib
import json
import logging
import math
import os
import resource
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from rastro import fontes
from rastro import mapeamento as mp
from rastro import ranking as rk
from rastro.config import get_settings
from rastro.models import Coleta, Municipio, PayloadBruto, RespostaBruta

log = logging.getLogger(__name__)

VERSAO_FORMATO = 3
TAM_PAGINA = 500
LISTAS_POLITICO = ("proposicoes", "votacoes", "presencas", "cota")
# listas cujos itens se repetem entre parlamentares: id do item -> campos do catálogo
CATALOGOS = {
    "votacoes": ("id_votacao", ("data", "orgao", "materia", "descricao", "url_fonte", "sha256")),
    "presencas": ("id_evento", ("data_hora_inicio", "url_fonte", "sha256")),
}
# cota parlamentar: lançamentos item a item só no ano corrente e no anterior
ANOS_COTA_DETALHADA = 2
AVISO_COTA = "Lançamentos detalhados disponíveis na página oficial da Câmara"
URL_COTA_BUSCA = "https://www.camara.leg.br/cota-parlamentar/"
URL_COTA_DEPUTADO = (
    "https://www.camara.leg.br/transparencia/gastos-parlamentares?legislatura={leg}&ano={ano}"
    "&mes=&por=deputado&deputado={id}&uf=&partido="
)
# arquivos cujo conteúdo define o que o exportador grava (entram na impressão digital)
_CODIGO = ("site.py", "api/politicos.py", "politicos/publicacao.py", "politicos/modelos.py")
_GERADOS = (
    "manifesto.json", "indice.json", "municipios.json", "municipios", "representantes",
    "ranking.json", "ranking.csv", "metodologia.json", "politicos", "eleitos", "catalogos",
)  # fmt: skip


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
    """JSON determinístico: mesmo conteúdo, mesmos bytes (chaves em ordem, sem espaços)."""
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _sha(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _travas() -> dict[str, bool]:
    """Estado das travas de publicação no momento da exportação."""
    cfg = get_settings()
    return {k: v for k, v in cfg.model_dump().items() if k.startswith("pol_publicar_")}


def legislatura(ano: int) -> int:
    """Legislatura da Câmara que cobre a maior parte do ano (57ª = 2023–2027)."""
    return 57 + (ano - 2023) // 4


def url_cota_deputado(id_camara: str, ano: int) -> str:
    return URL_COTA_DEPUTADO.format(leg=legislatura(ano), ano=ano, id=id_camara)


# --------------------------------------------------------------------------- compactação

_AUSENTE = object()


def compactar(itens: list[dict]) -> dict:
    """{"comum", "indices", "itens"}: tira dos itens o que se repete (ver docstring)."""
    if len(itens) < 2:
        return {"itens": itens}
    comum, indices = {}, {}
    for campo in sorted({k for x in itens for k in x}):
        valores = [x.get(campo, _AUSENTE) for x in itens]
        if any(v is _AUSENTE or isinstance(v, dict | list) for v in valores):
            continue
        distintos = list(dict.fromkeys(valores))
        if len(distintos) == 1:
            comum[campo] = distintos[0]
        elif all(isinstance(v, str) for v in distintos) and len(distintos) <= len(itens) // 4:
            indices[campo] = distintos
    posicao = {c: {v: i for i, v in enumerate(lista)} for c, lista in indices.items()}
    novos = []
    for x in itens:
        y = {k: v for k, v in x.items() if k not in comum}
        for c, pos in posicao.items():
            y[c] = pos[x[c]]
        novos.append(y)
    saida: dict = {"itens": novos}
    if comum:
        saida["comum"] = comum
    if indices:
        saida["indices"] = indices
    return saida


def expandir(compacto: dict) -> list[dict]:
    """Inverso de `compactar` (o mesmo que o site faz no navegador)."""
    comum, indices = compacto.get("comum", {}), compacto.get("indices", {})
    saida = []
    for x in compacto["itens"]:
        y = {**comum, **x}
        for c, lista in indices.items():
            y[c] = lista[x[c]]
        saida.append(y)
    return saida


# --------------------------------------------------------------------------- fontes


class _Arquivados:
    """resposta_id -> (SHA-256 do conteúdo arquivado, primeiro recebimento desse conteúdo)."""

    def __init__(self, session: Session):
        self.session = session
        self.mapa: dict[int, tuple[str, str]] = {}

    def carregar(self, ids) -> None:
        faltam = {i for i in ids if i is not None and i not in self.mapa}
        for lote in _lotes(sorted(faltam), 5000):
            rows = self.session.execute(
                select(RespostaBruta.id, RespostaBruta.sha256, PayloadBruto.criado_em)
                .join(PayloadBruto, PayloadBruto.sha256 == RespostaBruta.sha256)
                .where(RespostaBruta.id.in_(lote))
            )
            for rid, sha, criado in rows:
                self.mapa[rid] = (sha, criado.isoformat())

    def trocar(self, dados):
        """Troca `resposta_id` por `sha256` (e a data pelo 1º recebimento) e tira as datas
        de gravação no banco (`atualizado_em`), que mudam a cada coleta."""
        ids: set[int] = set()
        _coletar_ids(dados, ids)
        self.carregar(ids)
        return self._trocar(dados)

    def _trocar(self, dados):
        if isinstance(dados, list):
            return [self._trocar(x) for x in dados]
        if not isinstance(dados, dict):
            return dados
        saida = {}
        for k, v in dados.items():
            if k == "atualizado_em":
                continue
            if k == "resposta_id":
                sha, criado = self.mapa.get(v, (None, None)) if v is not None else (None, None)
                saida["sha256"] = sha
                if "recebido_em" in dados:
                    saida["recebido_em"] = criado
                continue
            if k == "recebido_em" and "resposta_id" in dados:
                continue
            saida[k] = self._trocar(v)
        if isinstance(saida.get("fontes"), list):
            # respostas diferentes com o mesmo conteúdo viram uma fonte só
            vistos, unicas = set(), []
            for f in saida["fontes"]:
                chave = (f.get("url"), f.get("sha256"))
                if chave not in vistos:
                    vistos.add(chave)
                    unicas.append(f)
            saida["fontes"] = unicas
        return saida


def _coletar_ids(dados, ids: set[int]) -> None:
    if isinstance(dados, list):
        for x in dados:
            _coletar_ids(x, ids)
    elif isinstance(dados, dict):
        for k, v in dados.items():
            if k == "resposta_id" and v is not None:
                ids.add(v)
            else:
                _coletar_ids(v, ids)


def _lotes(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# --------------------------------------------------------------------------- impressões


def _sal(uf: str, anos_cota: tuple[int, ...], estado_emendas: dict) -> str:
    """Parte da impressão digital comum a todos os grupos."""
    from rastro.politicos.vinculo import ARQUIVO_EXCECOES

    raiz = Path(__file__).parent
    codigo = hashlib.sha256()
    for nome in _CODIGO:
        codigo.update((raiz / nome).read_bytes())
    return _sha(
        _bytes(
            {
                "formato": VERSAO_FORMATO,
                "uf": uf,
                "travas": _travas(),
                "excecoes": _sha(ARQUIVO_EXCECOES.read_bytes()),
                "codigo": codigo.hexdigest(),
                "anos_cota_detalhada": anos_cota,
                "emendas": estado_emendas,
            }
        )
    )


def _linhas_sql(tabela: str, grupo: str) -> str:
    """Linhas de `tabela` como texto, sem id interno, id da resposta e data de gravação;
    a resposta entra pelo SHA-256 e pela URL (o que o site mostra)."""
    return (
        f"select {grupo} as grupo, (to_jsonb(t) - 'id' - 'resposta_id' - 'atualizado_em')"
        f"::text || '#' || coalesce(r.sha256, '') || '#' || coalesce(r.url, '') as linha "
        f"from {tabela} t left join resposta_bruta r on r.id = t.resposta_id"
    )


_TABELAS_POLITICO = (
    ("pol_politico", "id"),
    ("pol_proposicao", "politico_id"),
    ("pol_votacao", "politico_id"),
    ("pol_presenca", "politico_id"),
    ("pol_comissao", "politico_id"),
    ("pol_despesa_cota", "politico_id"),
    ("pol_evento_mandato", "politico_id"),
    ("pol_emenda", "politico_id"),
)


def _impressoes_politicos(session: Session, ids: list[int], sal: str) -> dict[int, str]:
    partes: dict[int, list[str]] = defaultdict(list)
    for tabela, coluna in _TABELAS_POLITICO:
        sql = text(
            f"select grupo, md5(string_agg(linha, '|' order by linha)) from "
            f"({_linhas_sql(tabela, f't.{coluna}')} where t.{coluna} = any(:ids)) x group by grupo"
        )
        for pid, h in session.execute(sql, {"ids": ids}):
            partes[pid].append(f"{tabela}:{h}")
    return {pid: _sha(f"{sal}|{'|'.join(partes[pid])}".encode()) for pid in ids}


def chave_eleitos(p: dict) -> str:
    """Arquivo de eleitos do TSE: por município (cargos municipais) ou por UF e eleição."""
    if p.get("cod_ibge"):
        return f"m-{p['cod_ibge']}"
    return f"uf-{p['uf']}-{p['eleicao_ano']}"


def _impressoes_eleitos(session: Session, ids: list[int], sal: str) -> dict[str, str]:
    chave = (
        "case when t.cod_ibge is not null then 'm-' || t.cod_ibge "
        "else 'uf-' || t.uf || '-' || t.eleicao_ano end"
    )
    sql = text(
        f"select grupo, md5(string_agg(linha, '|' order by linha)) from "
        f"({_linhas_sql('pol_politico', chave)} "
        f"where t.id = any(:ids)) x group by grupo"
    )
    return {g: _sha(f"{sal}|{h}".encode()) for g, h in session.execute(sql, {"ids": ids})}


# --------------------------------------------------------------------------- catálogos


class _CatVotacao(BaseModel):
    data: date
    orgao: str | None
    materia: str | None
    descricao: str | None
    url_fonte: str


class _CatPresenca(BaseModel):
    data_hora_inicio: datetime
    url_fonte: str


def _catalogos(
    session: Session, federais: dict[int, str], arquivados: _Arquivados
) -> tuple[dict[tuple[str, str, int], dict[str, dict]], dict[int, set[tuple]]]:
    """(lista, casa, ano) -> {id: campos iguais em todas as linhas daquele id}, e as
    entradas que cada político usa: politico_id -> {(lista, casa, ano, id)}.

    Campo que difere entre parlamentares (ex.: a URL de votação do Senado, que é por
    senador) fica fora do catálogo e continua no arquivo de cada político.
    """
    from rastro.politicos.modelos import PolPresenca, PolVotacao

    consultas = {
        "votacoes": (
            PolVotacao,
            PolVotacao.id_votacao,
            (PolVotacao.data, PolVotacao.orgao, PolVotacao.materia, PolVotacao.descricao),
            _CatVotacao,
        ),
        "presencas": (
            PolPresenca, PolPresenca.id_evento, (PolPresenca.data_hora_inicio,), _CatPresenca
        ),
    }  # fmt: skip
    saida: dict[tuple[str, str, int], dict[str, dict]] = {}
    usadas: dict[int, set[tuple]] = defaultdict(set)
    ids = list(federais)
    for lista, (modelo, chave, colunas, esquema) in consultas.items():
        rows = session.execute(
            select(modelo.politico_id, chave, *colunas, modelo.url_fonte, modelo.resposta_id)
            .where(modelo.politico_id.in_(ids))
            .distinct()
        ).all()
        arquivados.carregar({r.resposta_id for r in rows})
        valores: dict[tuple[str, int, str], dict[str, set]] = defaultdict(lambda: defaultdict(set))
        nomes = [c.key for c in colunas] + ["url_fonte"]
        for r in rows:
            item = esquema(**{n: getattr(r, n) for n in nomes}).model_dump(mode="json")
            item["sha256"] = arquivados.mapa.get(r.resposta_id, (None,))[0]
            data_item = item["data"] if lista == "votacoes" else item["data_hora_inicio"]
            k = (federais[r.politico_id], int(data_item[:4]), getattr(r, chave.key))
            usadas[r.politico_id].add((lista, *k))
            for campo, v in item.items():
                valores[k][campo].add(json.dumps(v))
        for (casa, ano, id_item), campos in valores.items():
            entrada = {c: json.loads(next(iter(vs))) for c, vs in campos.items() if len(vs) == 1}
            saida.setdefault((lista, casa, ano), {})[id_item] = entrada
    return saida, usadas


def _impressao_catalogo(catalogos: dict, usadas: set[tuple]) -> str:
    """Impressão das entradas de catálogo que um político usa: o arquivo dele só depende
    delas (uma votação nova de que ele não participou não refaz a página dele)."""
    entradas = [[*k, catalogos[k[:3]][k[3]]] for k in sorted(usadas)]
    return _sha(_bytes(entradas))


# --------------------------------------------------------------------------- gravação


class _Escritor:
    """Grava só o que mudou e registra o SHA-256 de cada arquivo."""

    def __init__(self, raiz: Path, anteriores: dict[str, str]):
        self.raiz = raiz
        self.anteriores = anteriores
        self.arquivos: dict[str, str] = {}
        self.escritos = 0
        self.bytes_escritos = 0

    def json(self, caminho: str, dados) -> None:
        self.bruto(caminho, _bytes(dados))

    def bruto(self, caminho: str, conteudo: bytes) -> None:
        if caminho in self.arquivos:
            raise ErroExportacao(f"arquivo gravado duas vezes: {caminho}")
        sha = _sha(conteudo)
        self.arquivos[caminho] = sha
        destino = self.raiz / caminho
        if (
            self.anteriores.get(caminho) == sha
            and destino.is_file()
            and _sha(destino.read_bytes()) == sha
        ):
            return  # igual ao que já está gravado
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        self.escritos += 1
        self.bytes_escritos += len(conteudo)

    def intactos(self, caminhos: list[str]) -> bool:
        """Os arquivos de um grupo da exportação anterior ainda estão aí, sem alteração?"""
        for c in caminhos:
            destino = self.raiz / c
            if c not in self.anteriores or not destino.is_file():
                return False
            if _sha(destino.read_bytes()) != self.anteriores[c]:
                return False
        return True

    def manter(self, caminhos: list[str]) -> None:
        for c in caminhos:
            self.arquivos[c] = self.anteriores[c]


@contextmanager
def _sessao(session: Session | None):
    """Sessão de leitura da exportação, em autocommit: cada consulta é a própria transação.

    A exportação passa minutos chamando a API interna entre uma consulta e outra. Com uma
    transação aberta nesse intervalo, a conexão fica "idle in transaction", e o banco de
    produção a encerra (idle_in_transaction_session_timeout; execução 6pfw6, 09/10/2026).
    A exportação só lê, e roda com a trava da coleta (nenhuma gravação concorrente), então
    não precisa de uma transação única.
    """
    from rastro.db import get_engine

    if session is not None:
        yield session
        return
    s = Session(
        bind=get_engine().execution_options(isolation_level="AUTOCOMMIT"),
        expire_on_commit=False,
    )
    try:
        yield s
    finally:
        s.close()


def _indice_anterior(saida: Path) -> dict | None:
    try:
        indice = json.loads((saida / "indice.json").read_bytes())
    except (OSError, ValueError):
        return None
    return indice if indice.get("formato") == VERSAO_FORMATO else None


def _limpar(saida: Path) -> None:
    """Exportação completa: apaga só o que este exportador gera."""
    for nome in _GERADOS:
        alvo = saida / nome
        if alvo.is_dir():
            shutil.rmtree(alvo)
        elif alvo.exists():
            alvo.unlink()


def _resumo_politico(p: dict) -> dict:
    """O que a lista de representantes mostra: nome, partido e o link da página."""
    r = {"id": p["id"], "nome": p["nome"], "partido": p["partido"]}
    if p["fonte"] == "tse":
        r["eleito"] = chave_eleitos(p)
    return r


def _sem_vazios(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, [], {})}


# --------------------------------------------------------------------------- exportação


def exportar(
    saida: Path,
    uf: str = "SP",
    session: Session | None = None,
    hoje: date | None = None,
    completa: bool = False,
    sem_ranking: bool = False,
) -> dict:
    """Gera (ou atualiza) os arquivos do site em `saida` e devolve o manifesto.

    Se `saida` tiver uma exportação anterior no mesmo formato, os grupos sem mudança são
    reaproveitados e só os arquivos alterados são regravados (`completa` refaz tudo).

    `sem_ranking` (prévia com dados fiscais parciais): o ranking e as notas não são
    exportados, nem ficam acessíveis por URL.
    """
    inicio = time.monotonic()
    uf = uf.upper()
    hoje = hoje or datetime.now(UTC).date()
    anos_cota = tuple(hoje.year - i for i in range(ANOS_COTA_DETALHADA))
    api = _cliente(session)
    indice_ant = None if completa else _indice_anterior(saida)
    if indice_ant is None:
        _limpar(saida)
    out = _Escritor(saida, (indice_ant or {}).get("arquivos", {}))
    grupos_ant = (indice_ant or {}).get("grupos", {})
    grupos: dict[str, dict] = {}
    reaproveitados = 0

    def get(url: str, opcional: bool = False):
        r = api.get(url)
        if r.status_code == 404 and opcional:
            return None
        if r.status_code != 200:
            raise ErroExportacao(f"GET {url}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    with _sessao(session) as s:
        arquivados = _Arquivados(s)
        municipios = s.scalars(
            select(Municipio).where(Municipio.uf == uf).order_by(Municipio.nome)
        ).all()
        if not municipios:
            raise ErroExportacao(f"nenhum município de {uf} no banco")
        ultima_coleta = s.scalar(
            select(func.max(Coleta.finalizada_em)).where(Coleta.status.in_(["sucesso", "parcial"]))
        )
        # situação de cada fonte nesta coleta (RASTRO_INICIO_COLETA, posto pela coleta
        # agendada); a página "Status das fontes" e os avisos do site leem daqui
        inicio_coleta = os.environ.get("RASTRO_INICIO_COLETA")
        situacao_fontes = fontes.status(
            s, datetime.fromisoformat(inicio_coleta) if inicio_coleta else None
        )

        # representantes: as seções de estado e federais são iguais em todos os municípios
        # da UF; cada seção que se repete vira um arquivo só, nomeado pelo hash do conteúdo
        conhecidos: dict[int, dict] = {}
        reps = {}
        for m in municipios:
            rep = get(f"/api/municipios/{m.cod_ibge}/representantes")
            for sec in rep["secoes"]:
                for g in sec["grupos"]:
                    conhecidos.update({p["id"]: p for p in g["politicos"]})
                    g["politicos"] = [_resumo_politico(p) for p in g["politicos"]]
            reps[m.cod_ibge] = rep
        vezes: Counter[bytes] = Counter(
            _bytes(sec) for rep in reps.values() for sec in rep["secoes"]
        )
        secoes_gravadas: set[str] = set()

        def secao(sec: dict) -> dict:
            conteudo = _bytes(sec)
            if vezes[conteudo] < 2:
                return sec
            ref = f"representantes/{_sha(conteudo)[:16]}.json"
            if ref not in secoes_gravadas:
                out.bruto(ref, conteudo)
                secoes_gravadas.add(ref)
            return {"ref": ref}

        def prefeitos(cod: int) -> dict:
            """Prefeito e vice eleitos por mandato e exercício (ADR-0018). Só entra no arquivo
            com a trava ligada: desligada, o arquivo do município fica como antes."""
            p = get(f"/api/municipios/{cod}/prefeitos")
            return {"prefeitos": arquivados.trocar(p)} if p["publicados"] else {}

        lista = []
        for m in municipios:
            cod = m.cod_ibge
            detalhe = get(f"/api/municipios/{cod}")
            # lista da busca: dados básicos e a população do IBGE (desempata as sugestões)
            pop = detalhe.get("populacao_ibge")
            lista.append(
                {
                    **{
                        k: v
                        for k, v in detalhe.items()
                        if k not in ("ente_siconfi", "populacao_ibge")
                    },
                    "populacao": pop["populacao"] if pop else None,
                }
            )
            rep = reps[cod]
            out.json(
                f"municipios/{cod}.json",
                {
                    "detalhe": detalhe,
                    "serie": get(f"/api/entes/{cod}/indicadores/serie"),
                    "nota": None if sem_ranking else get(f"/api/ranking/{cod}", opcional=True),
                    "representantes": {
                        "municipio": rep["municipio"],
                        "secoes": [secao(sec) for sec in rep["secoes"]],
                    },
                    "emendas": arquivados.trocar(get(f"/api/municipios/{cod}/emendas")),
                    **prefeitos(cod),
                },
            )
        out.json("municipios.json", lista)

        ranking = None if sem_ranking else get(f"/api/ranking?uf={uf}", opcional=True)
        if ranking:
            out.json("ranking.json", ranking)
            out.bruto("ranking.csv", api.get(f"/api/ranking.csv?uf={uf}").content)
        out.json("metodologia.json", get("/api/metodologia"))

        # só os políticos que a API mostra (travas aplicadas), mais os citados nas páginas
        deslocamento = 0
        while True:
            pagina = get(f"/api/politicos?uf={uf}&limite=500&deslocamento={deslocamento}")
            conhecidos.update({p["id"]: p for p in pagina["itens"]})
            deslocamento += len(pagina["itens"])
            if not pagina["itens"] or deslocamento >= pagina["total"]:
                break
        federais = {i: p["fonte"] for i, p in conhecidos.items() if p["fonte"] != "tse"}
        tse = {i: p for i, p in conhecidos.items() if p["fonte"] == "tse"}

        # catálogos de votações e presenças (sempre recalculados; gravados se mudarem)
        catalogos, usadas = _catalogos(s, federais, arquivados)
        for (lista_nome, casa, ano), entradas in sorted(catalogos.items()):
            itens = [{CATALOGOS[lista_nome][0]: i, **e} for i, e in sorted(entradas.items())]
            caminho = f"catalogos/{lista_nome}/{casa}/{ano}.json"
            out.json(caminho, {"ano": ano, "casa": casa, **compactar(itens)})

        coletadas = bool(
            s.scalar(
                select(func.count())
                .select_from(Coleta)
                .where(Coleta.fonte == "pol-emendas", Coleta.status.in_(["sucesso", "parcial"]))
            )
        )
        tem_arquivo = (
            s.execute(
                text("select 1 from pol_emenda where fonte_dados = 'arquivo' limit 1")
            ).first()
            is not None
        )
        sal = _sal(uf, anos_cota, {"coletadas": coletadas, "arquivo": tem_arquivo})
        impressoes = {
            pid: _sha(f"{imp}|{_impressao_catalogo(catalogos, usadas[pid])}".encode())
            for pid, imp in _impressoes_politicos(s, sorted(federais), sal).items()
        }

        for pid in sorted(federais):
            nome = f"politico:{pid}"
            ant = grupos_ant.get(nome)
            if ant and ant["impressao"] == impressoes[pid] and out.intactos(ant["arquivos"]):
                out.manter(ant["arquivos"])
                grupos[nome] = ant
                reaproveitados += 1
                continue
            antes = set(out.arquivos)
            _exportar_politico(pid, get, out, arquivados, catalogos, anos_cota)
            grupos[nome] = {
                "impressao": impressoes[pid],
                "arquivos": sorted(set(out.arquivos) - antes),
            }

        # eleitos do TSE: um arquivo por município ou por UF e eleição
        por_chave: dict[str, list[int]] = defaultdict(list)
        for i, p in tse.items():
            por_chave[chave_eleitos(p)].append(i)
        imp_eleitos = _impressoes_eleitos(s, sorted(tse), sal)
        for chave in sorted(por_chave):
            nome = f"eleitos:{chave}"
            caminho = f"eleitos/{chave}.json"
            ant = grupos_ant.get(nome)
            if ant and ant["impressao"] == imp_eleitos[chave] and out.intactos(ant["arquivos"]):
                out.manter(ant["arquivos"])
                grupos[nome] = ant
                reaproveitados += 1
                continue
            ids = sorted(por_chave[chave], key=lambda i: (tse[i]["nome"], i))
            detalhes = [_sem_vazios(arquivados.trocar(get(f"/api/politicos/{i}"))) for i in ids]
            out.json(caminho, {"chave": chave, **compactar(detalhes)})
            grupos[nome] = {"impressao": imp_eleitos[chave], "arquivos": [caminho]}

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
        "fontes": situacao_fontes,
        "cota_detalhada": list(anos_cota),
        "contagens": {
            "municipios": len(municipios),
            "municipios_com_nota": sum(1 for i in (ranking or {}).get("itens", []) if i["nota"]),
            "politicos": len(conhecidos),
        },
    }
    extras = ("manifesto.json", "indice.json")

    # o que estava na exportação anterior e não está nesta sai da pasta
    removidos = 0
    for caminho in set(out.anteriores) - set(out.arquivos) - set(extras):
        (saida / caminho).unlink(missing_ok=True)
        removidos += 1
    for pasta in sorted((p for p in saida.rglob("*") if p.is_dir()), reverse=True):
        if not any(pasta.iterdir()):
            pasta.rmdir()

    # o manifesto (data da exportação) muda sempre; fica fora do índice para que o índice
    # só mude quando algum arquivo de dados mudar
    (saida / "manifesto.json").write_bytes(_bytes(manifesto))

    indice = {
        "formato": VERSAO_FORMATO,
        "uf": uf,
        "grupos": grupos,
        "arquivos": dict(sorted(out.arquivos.items())),
    }
    indice_mudou = indice != indice_ant
    if indice_mudou:
        (saida / "indice.json").write_bytes(_bytes(indice))
    total_bytes = sum((saida / c).stat().st_size for c in [*out.arquivos, *extras])
    estatisticas = {
        "arquivos": len(out.arquivos) + len(extras),
        "bytes": total_bytes,
        "escritos": out.escritos + 1 + indice_mudou,
        "bytes_escritos": out.bytes_escritos,
        "removidos": removidos,
        "grupos": len(grupos),
        "grupos_reaproveitados": reaproveitados,
        "segundos": round(time.monotonic() - inicio, 1),
        # pico de memória do processo (Linux: KiB), para diagnosticar falta de memória
        "memoria_pico_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }
    log.info("Site exportado em %s: %s", saida, estatisticas)
    return {**manifesto, "exportacao": estatisticas}


def _exportar_politico(pid, get, out: _Escritor, arquivados, catalogos, anos_cota) -> None:
    """Detalhe e listas de um deputado/senador; páginas de 500, nenhuma lista cortada."""
    detalhe = arquivados.trocar(get(f"/api/politicos/{pid}"))
    casa = detalhe["fonte"]
    base = f"politicos/{pid}"
    for lista in LISTAS_POLITICO:
        for contagem in detalhe.get(lista, []):
            ano, total = contagem["ano"], contagem["quantidade"]
            paginas = math.ceil(total / TAM_PAGINA)
            if lista == "cota":
                detalhada = ano in anos_cota
                cab = get(f"/api/politicos/{pid}/cota?ano={ano}&limite=1")
                out.json(
                    f"{base}/cota/{ano}.json",
                    {
                        "ano": ano,
                        "total": total,
                        "por_categoria": cab["por_categoria"],
                        "detalhada": detalhada,
                        "paginas": paginas if detalhada else 0,
                        "aviso": None if detalhada else AVISO_COTA,
                        "url_oficial": url_cota_deputado(detalhe["id_fonte"], ano),
                        "url_busca_detalhada": URL_COTA_BUSCA,
                    },
                )
                if not detalhada:
                    continue
            catalogo = catalogos.get((lista, casa, ano), {})
            chave = CATALOGOS[lista][0] if lista in CATALOGOS else None
            recebidos = 0
            for n in range(1, paginas + 1):
                url = (
                    f"/api/politicos/{pid}/{lista}?ano={ano}&limite={TAM_PAGINA}"
                    f"&deslocamento={(n - 1) * TAM_PAGINA}"
                )
                resp = get(url)
                pagina = resp["despesas"] if lista == "cota" else resp
                if pagina["total"] != total:
                    raise ErroExportacao(f"{url}: total {pagina['total']}, esperado {total}")
                itens = arquivados.trocar(pagina["itens"])
                if chave:
                    for x in itens:
                        comum = catalogo.get(x[chave], {})
                        for campo, v in comum.items():
                            if x.get(campo) == v:
                                del x[campo]
                recebidos += len(itens)
                out.json(
                    f"{base}/{lista}/{ano}-{n}.json",
                    {"ano": ano, "pagina": n, "paginas": paginas, "total": total,
                     **compactar(itens)},
                )  # fmt: skip
            if recebidos != total:
                raise ErroExportacao(f"{base}/{lista}/{ano}: {recebidos} itens de {total}")

    anos_emendas = []
    resumo = get(f"/api/politicos/{pid}/emendas")
    for ano in sorted({e["ano"] for e in resumo["itens"]}, reverse=True):
        out.json(
            f"{base}/emendas/{ano}.json",
            arquivados.trocar(get(f"/api/politicos/{pid}/emendas?ano={ano}")),
        )
        anos_emendas.append(ano)
    detalhe["emendas"] = {
        "coletadas": resumo["coletadas"],
        "publicadas": resumo["publicadas"],
        "aviso": resumo["aviso"],
        "anos": anos_emendas,
    }
    out.json(f"{base}.json", detalhe)


# --------------------------------------------------------------------------- verificação


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
    problemas += _conferir_indice(saida)
    municipios = json.loads((saida / "municipios.json").read_text())
    faltando, refs_quebradas, citados = [], set(), []
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
            citados += [p for g in sec["grupos"] for p in g["politicos"]]
    if faltando:
        problemas.append(f"{len(faltando)} municípios sem arquivo de detalhe")
    if refs_quebradas:
        problemas.append(f"seções de representantes ausentes: {sorted(refs_quebradas)}")
    eleitos: dict[str, set[int]] = {}
    sem_pagina = set()
    for p in citados:
        if "eleito" in p:
            if p["eleito"] not in eleitos:
                arq = saida / "eleitos" / f"{p['eleito']}.json"
                eleitos[p["eleito"]] = (
                    {x["id"] for x in expandir(json.loads(arq.read_bytes()))}
                    if arq.exists()
                    else set()
                )
            if p["id"] not in eleitos[p["eleito"]]:
                sem_pagina.add(p["id"])
        elif not (saida / "politicos" / f"{p['id']}.json").exists():
            sem_pagina.add(p["id"])
    if sem_pagina:
        problemas.append(
            f"{len(sem_pagina)} políticos citados sem página: {sorted(sem_pagina)[:10]}"
        )
    problemas += _conferir_listas(saida)
    problemas += _conferir_travas(saida, manifesto.get("travas", {}))
    for obrigatorio in ("metodologia.json",):
        if not (saida / obrigatorio).exists():
            problemas.append(f"arquivo obrigatório ausente: {obrigatorio}")
    if anterior:
        mesmas_travas = anterior.get("travas") == manifesto.get("travas")
        # fonte de políticos que nunca foi coletada com sucesso (falhou nesta coleta e não
        # tem dado anterior no banco): a seção dela sai como "fonte indisponível nesta
        # coleta" e a queda no número de políticos é esperada, não um erro
        indisponiveis = [
            f["fonte"]
            for f in manifesto.get("fontes", [])
            if f["fonte"] in fontes.FONTES_POLITICOS and not f["disponivel"]
        ]
        for chave in ("municipios", "politicos"):
            if chave == "politicos" and not mesmas_travas:
                continue  # ligar/desligar uma trava muda o número de políticos de propósito
            if chave == "politicos" and indisponiveis:
                log.warning(
                    "Número de políticos pode cair: fonte(s) indisponível(is) nesta coleta: %s",
                    ", ".join(indisponiveis),
                )
                continue
            antes = anterior.get("contagens", {}).get(chave, 0)
            agora = manifesto["contagens"].get(chave, 0)
            if agora < antes:
                problemas.append(f"{chave}: {agora} na nova versão, {antes} na publicada")
        if anterior.get("uf") and anterior["uf"] != manifesto["uf"]:
            problemas.append(f"UF mudou de {anterior['uf']} para {manifesto['uf']}")
    return problemas


def _conferir_indice(saida: Path) -> list[str]:
    """Cada arquivo listado no índice existe e tem o SHA-256 registrado; nada sobra."""
    try:
        indice = json.loads((saida / "indice.json").read_bytes())
    except (OSError, ValueError) as exc:
        return [f"indice.json ausente ou inválido: {exc}"]
    problemas = []
    arquivos = indice.get("arquivos", {})
    diferentes = [
        c for c, sha in arquivos.items()
        if not (saida / c).is_file() or _sha((saida / c).read_bytes()) != sha
    ]  # fmt: skip
    if diferentes:
        problemas.append(
            f"{len(diferentes)} arquivos ausentes ou diferentes do índice: {diferentes[:5]}"
        )
    sobrando = [
        c
        for p in saida.rglob("*")
        if p.is_file() and (c := p.relative_to(saida).as_posix()) not in arquivos
        and c not in ("indice.json", "manifesto.json")
    ]  # fmt: skip
    if sobrando:
        problemas.append(f"{len(sobrando)} arquivos fora do índice: {sorted(sobrando)[:5]}")
    return problemas


def _conferir_listas(saida: Path) -> list[str]:
    """Nenhuma lista cortada: as páginas de cada ano somam a quantidade do detalhe."""
    problemas = []
    for arq in sorted((saida / "politicos").glob("*.json")):
        p = json.loads(arq.read_bytes())
        base = saida / "politicos" / arq.stem
        for lista in LISTAS_POLITICO:
            for c in p.get(lista, []):
                ano = c["ano"]
                if lista == "cota":
                    cab_arq = base / "cota" / f"{ano}.json"
                    if not cab_arq.exists():
                        problemas.append(f"{arq.stem}/cota/{ano}.json ausente")
                        continue
                    if not json.loads(cab_arq.read_bytes())["detalhada"]:
                        continue
                n, itens = 1, 0
                while (pag := base / lista / f"{ano}-{n}.json").exists():
                    itens += len(json.loads(pag.read_bytes())["itens"])
                    n += 1
                if itens != c["quantidade"]:
                    problemas.append(
                        f"politicos/{arq.stem}/{lista}/{ano}: {itens} itens nos arquivos, "
                        f"{c['quantidade']} no detalhe"
                    )
        for ano in p.get("emendas", {}).get("anos", []):
            if not (base / "emendas" / f"{ano}.json").exists():
                problemas.append(f"politicos/{arq.stem}/emendas/{ano}.json ausente")
    return problemas


def _conferir_travas(saida: Path, travas: dict) -> list[str]:
    """Segunda barreira: nada que uma trava desligada esconde pode estar nos arquivos."""
    from rastro.politicos.publicacao import ELEICOES_FUTURAS

    problemas = []
    if not travas:
        return ["manifesto sem o estado das travas de publicação"]
    candidatos = [
        (arq, json.loads(arq.read_bytes())) for arq in (saida / "politicos").glob("*.json")
    ]
    candidatos += [
        (arq, p)
        for arq in (saida / "eleitos").glob("*.json")
        for p in expandir(json.loads(arq.read_bytes()))
    ]
    for arq, p in candidatos:
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
    if not travas.get("pol_publicar_gestoes"):
        # prefeitos eleitos por exercício (ADR-0018): fora da página do município
        for arq in (saida / "municipios").glob("*.json"):
            p = json.loads(arq.read_bytes()).get("prefeitos") or {}
            if p.get("publicados") or p.get("mandatos") or p.get("exercicios"):
                problemas.append(
                    f"{arq.relative_to(saida)}: prefeitos exportados com pol_publicar_gestoes "
                    "desligada"
                )
    # o ranking nunca traz nomes de prefeitos, com qualquer trava (ADR-0018, decisão de
    # 09/10/2026: na mesma linha da nota, o nome pareceria uma nota para a pessoa)
    if (saida / "ranking.json").exists():
        itens = json.loads((saida / "ranking.json").read_bytes()).get("itens", [])
        if any("prefeitos_no_periodo" in i for i in itens):
            problemas.append("ranking.json: o ranking não pode trazer prefeitos (ADR-0018)")
    if (saida / "ranking.csv").exists():
        cabecalho = (saida / "ranking.csv").read_text(encoding="utf-8-sig").split("\n", 1)[0]
        if "prefeito" in cabecalho:
            problemas.append("ranking.csv: o ranking não pode trazer prefeitos (ADR-0018)")
    return problemas
