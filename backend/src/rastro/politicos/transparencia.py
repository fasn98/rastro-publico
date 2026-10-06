"""Emendas parlamentares (Portal da Transparência, Controladoria-Geral da União).

Endpoint `/api-de-dados/emendas` (especificação: https://api.portaldatransparencia.gov.br/v3/api-docs),
campos do `ConsultaEmendasDTO`: codigoEmenda, ano, tipoEmenda, autor, nomeAutor, numeroEmenda,
localidadeDoGasto, funcao, subfuncao, valorEmpenhado, valorLiquidado, valorPago,
valorRestoInscrito, valorRestoCancelado, valorRestoPago (valores como texto).

Exige a chave no cabeçalho `chave-api-dados` (cadastro gratuito em
https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email). Dois modos:
- com a variável `RASTRO_TRANSPARENCIA_CHAVE` (ex.: Replit), o coletor envia o cabeçalho;
- sem ela, conta com um proxy que injeta o cabeçalho (credencial de API do ambiente).
Antes de coletar, uma consulta de teste confirma o acesso; se a API responder 401, a
coleta falha com aviso claro (nenhum dado é gravado). A chave nunca é gravada: o
arquivo de respostas guarda só a URL e a resposta, não os cabeçalhos enviados.

ATENÇÃO: até agora nenhuma resposta com dados foi recebida neste projeto (não havia chave).
O formato dos valores em texto, o formato de `localidadeDoGasto`, os valores de
`tipoEmenda` e a forma de `nomeAutor` aceita no filtro precisam ser confirmados na
primeira coleta real, antes de exibir os números.
"""

import csv
import io
import os
import re
import unicodedata
import zipfile
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from rastro.coletores.arquivo import com_redacao, resposta_id
from rastro.coletores.redacao import redator_csv
from rastro.models import Municipio
from rastro.politicos.comum import get_json_com_origem
from rastro.politicos.modelos import PolEmenda

API = "https://api.portaldatransparencia.gov.br/api-de-dados"
VARIAVEL_CHAVE = "RASTRO_TRANSPARENCIA_CHAVE"
AVISO_SEM_CHAVE = (
    "Portal da Transparência recusou o acesso (401). Defina "
    f"{VARIAVEL_CHAVE} ou configure a credencial no proxy do ambiente (cadastro em "
    "https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email)."
)


class SemChave(Exception):
    """A API do Portal da Transparência recusou o acesso (sem chave válida)."""


def preparar_cliente(client: httpx.Client) -> str:
    """Põe a chave no cliente, se houver na variável de ambiente. Devolve o modo usado."""
    k = chave()
    if k:
        client.headers["chave-api-dados"] = k
        return f"chave da variável {VARIAVEL_CHAVE}"
    return "credencial injetada pelo proxy do ambiente (sem variável local)"


def verificar_acesso(client: httpx.Client, ano: int) -> None:
    """Consulta de teste (1 página). Levanta SemChave se a API responder 401."""
    resp = client.get(f"{API}/emendas", params={"ano": ano, "pagina": 1})
    if resp.status_code == 401:
        # a API distingue "Chave de API não informada!" de "Chave de API inválida!"
        raise SemChave(f"{AVISO_SEM_CHAVE} Resposta da API: {resp.text.strip()}")
    resp.raise_for_status()


def chave() -> str | None:
    return os.environ.get(VARIAVEL_CHAVE) or None


def valor(texto: str | None) -> Decimal | None:
    """Valor monetário em texto. Aceita '1234.56' e o formato brasileiro '1.234,56'."""
    if texto is None or not str(texto).strip():
        return None
    t = str(texto).strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())


_LOCALIDADE = re.compile(r"^(.+?)\s*-\s*([A-Z]{2})$")


def municipios_por_nome(session: Session) -> dict[tuple[str, str], int]:
    return {
        (_normalizar(nome), uf): cod
        for cod, nome, uf in session.execute(
            select(Municipio.cod_ibge, Municipio.nome, Municipio.uf)
        )
    }


def cod_ibge_destino(localidade: str | None, municipios: dict[tuple[str, str], int]) -> int | None:
    """'NOME DO MUNICÍPIO - UF' -> código IBGE, só se houver correspondência exata."""
    m = _LOCALIDADE.match(localidade or "")
    return municipios.get((_normalizar(m[1]), m[2])) if m else None


def coletar_emendas_autor(
    session: Session,
    client: httpx.Client,
    nome_autor: str,
    politico_id: int | None,
    ano: int,
    municipios: dict[tuple[str, str], int],
) -> int:
    linhas = []
    pagina = 1
    while True:
        params = {"nomeAutor": nome_autor, "ano": ano, "pagina": pagina}
        url = str(httpx.URL(f"{API}/emendas", params=params))
        itens, rid = get_json_com_origem(client, url)
        if not itens:
            break
        for e in itens:
            tipo = e.get("tipoEmenda")
            linhas.append(
                {
                    "codigo_emenda": e["codigoEmenda"],
                    "ano": e["ano"],
                    "tipo_emenda": tipo,
                    "transferencia_especial": "especia" in (tipo or "").lower(),
                    "autor": e.get("autor"),
                    "nome_autor": e.get("nomeAutor"),
                    "numero_emenda": e.get("numeroEmenda"),
                    "localidade_gasto": e.get("localidadeDoGasto"),
                    "cod_ibge_destino": cod_ibge_destino(e.get("localidadeDoGasto"), municipios),
                    "funcao": e.get("funcao"),
                    "subfuncao": e.get("subfuncao"),
                    "valor_empenhado": valor(e.get("valorEmpenhado")),
                    "valor_liquidado": valor(e.get("valorLiquidado")),
                    "valor_pago": valor(e.get("valorPago")),
                    "valor_resto_inscrito": valor(e.get("valorRestoInscrito")),
                    "valor_resto_cancelado": valor(e.get("valorRestoCancelado")),
                    "valor_resto_pago": valor(e.get("valorRestoPago")),
                    "politico_id": politico_id,
                    "url_fonte": url,
                    "resposta_id": rid,
                }
            )
        pagina += 1
    session.execute(
        delete(PolEmenda).where(
            PolEmenda.fonte_dados == "api",
            PolEmenda.politico_id == politico_id,
            PolEmenda.ano == ano,
        )
    )
    if linhas:
        session.execute(insert(PolEmenda), [{**x, "fonte_dados": "api"} for x in linhas])
    session.commit()
    return len(linhas)


# ----------------------------------------------------------------- download em lote

URL_ARQUIVO = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
MEMBRO_ARQUIVO = "EmendasParlamentares.csv"
NOMES_UF = {"SP": "SÃO PAULO"}


_SUFIXO = re.compile(r"\s*\(.*$")


def normalizar_nome(nome: str) -> str:
    """Nome do autor para o cruzamento com os parlamentares.

    O arquivo acrescenta ao nome, entre parênteses, de quem a emenda foi herdada (ex.:
    "FULANO (EX-PARLAMENTAR BELTRANO, NOS TERMOS ...)"); o sufixo é ignorado no cruzamento,
    e o texto completo continua gravado em `nome_autor`.
    """
    return _normalizar(_SUFIXO.sub("", nome))


def coletar_arquivo(
    session: Session,
    client: httpx.Client,
    uf: str,
    ano_min: int,
    autores: dict,
    excecoes: dict[str, tuple[int, str]] | None = None,
) -> dict:
    """Emendas do arquivo em lote do Portal (não exige chave).

    Grava as linhas do ano `ano_min` em diante cujo destino é a UF (coluna UF) ou cujo
    autor é um parlamentar da UF. O município de destino vem da coluna oficial "Código
    Município IBGE" (não do texto). `autores`: nome normalizado -> `vinculo.Autor` (só os
    confirmáveis); a ligação com a página do político segue as regras de `vinculo`.
    `excecoes`: texto exato do autor -> (pol_politico.id, rótulo), da tabela aprovada.
    O arquivo bruto guarda só esse recorte do CSV (o arquivo não traz dados pessoais),
    com o SHA-256 do ZIP original.
    """
    nome_uf = NOMES_UF[uf]
    excecoes = excecoes or {}

    def no_recorte(r: dict) -> bool:
        autor = r["Nome do Autor da Emenda"]
        return r["Ano da Emenda"] >= str(ano_min) and (
            r["UF"] == nome_uf or normalizar_nome(autor) in autores or autor in excecoes
        )

    redator = redator_csv(
        [],
        filtro=no_recorte,
        descricao_filtro=f"recorte: ano >= {ano_min} e destino em {uf} ou autor de {uf}",
        encoding="latin-1",
        membro_zip=MEMBRO_ARQUIVO,
    )
    resp = client.get(URL_ARQUIVO, extensions=com_redacao(redator), headers={"Accept": "*/*"})
    resp.raise_for_status()
    rid = resposta_id(resp)
    url = str(resp.url)  # endereço final, depois do redirecionamento
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        texto = z.read(MEMBRO_ARQUIVO).decode("latin-1")
    linhas = []
    fora_do_mandato: dict[str, int] = {}
    for n, r in enumerate(csv.DictReader(io.StringIO(texto), delimiter=";"), start=1):
        if not no_recorte(r):
            continue
        tipo = r["Tipo de Emenda"]
        cod = r["Código Município IBGE"]
        nome_autor = r["Nome do Autor da Emenda"]
        ano = int(r["Ano da Emenda"])
        autor = autores.get(normalizar_nome(nome_autor))
        politico_id = vinculo = nota = None
        if nome_autor in excecoes:
            politico_id, nota = excecoes[nome_autor]
            vinculo = "excecao"
        elif autor is not None:
            if autor.primeiro_ano <= ano <= autor.ultimo_ano:
                politico_id, vinculo = autor.politico_id, "nome"
            else:
                fora_do_mandato[nome_autor] = fora_do_mandato.get(nome_autor, 0) + 1
        linhas.append(
            {
                "fonte_dados": "arquivo",
                "linha": n,
                "codigo_emenda": r["Código da Emenda"],
                "codigo_autor": r["Código do Autor da Emenda"],
                "ano": ano,
                "tipo_emenda": tipo,
                "transferencia_especial": "especia" in tipo.lower(),
                "autor": nome_autor,
                "nome_autor": nome_autor,
                "numero_emenda": r["Número da emenda"],
                "localidade_gasto": r["Localidade de aplicação do recurso"],
                "cod_ibge_destino": int(cod) if cod.isdigit() and len(cod) == 7 else None,
                "funcao": r["Nome Função"],
                "subfuncao": r["Nome Subfunção"],
                "acao": r["Nome Ação"],
                "valor_empenhado": valor(r["Valor Empenhado"]),
                "valor_liquidado": valor(r["Valor Liquidado"]),
                "valor_pago": valor(r["Valor Pago"]),
                "valor_resto_inscrito": valor(r["Valor Restos A Pagar Inscritos"]),
                "valor_resto_cancelado": valor(r["Valor Restos A Pagar Cancelados"]),
                "valor_resto_pago": valor(r["Valor Restos A Pagar Pagos"]),
                "politico_id": politico_id,
                "vinculo": vinculo,
                "nota_vinculo": nota,
                "url_fonte": url,
                "resposta_id": rid,
            }
        )
    # regra 4: um mesmo político, um só "Código do Autor"; se houver mais de um, não liga
    # (as exceções aprovadas trazem o código do ex-parlamentar e ficam fora dessa conferência)
    codigos: dict[int, set[str]] = {}
    for x in linhas:
        if x["vinculo"] == "nome":
            codigos.setdefault(x["politico_id"], set()).add(x["codigo_autor"])
    ambiguos = {pid for pid, c in codigos.items() if len(c) > 1}
    for x in linhas:
        if x["vinculo"] == "nome" and x["politico_id"] in ambiguos:
            x["politico_id"] = x["vinculo"] = None
    session.execute(delete(PolEmenda).where(PolEmenda.fonte_dados == "arquivo"))
    for i in range(0, len(linhas), 2000):
        session.execute(insert(PolEmenda), linhas[i : i + 2000])
    session.commit()
    return {
        "linhas": len(linhas),
        "ligadas": sum(1 for x in linhas if x["politico_id"]),
        "por_excecao": sum(1 for x in linhas if x["vinculo"] == "excecao"),
        "fora_do_mandato": fora_do_mandato,
        "codigo_de_autor_ambiguo": sorted(ambiguos),
    }
