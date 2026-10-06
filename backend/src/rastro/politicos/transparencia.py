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

import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.models import Municipio
from rastro.politicos.comum import get_json_com_origem, gravar
from rastro.politicos.modelos import PolEmenda

API = "https://api.portaldatransparencia.gov.br/api-de-dados"
VARIAVEL_CHAVE = "RASTRO_TRANSPARENCIA_CHAVE"
AVISO_SEM_CHAVE = (
    "Portal da Transparência recusou o acesso (401, chave de API não informada). Defina "
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
        raise SemChave(AVISO_SEM_CHAVE)
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
    n = gravar(session, PolEmenda, linhas, ["codigo_emenda"]) if linhas else 0
    session.commit()
    return n
