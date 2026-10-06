"""Redatores: removem dados pessoais do que é gravado no arquivo de respostas brutas.

Ver `rastro.coletores.arquivo` (seção Redação). Cada redator devolve o conteúdo a gravar
e a lista de campos removidos; o arquivo registra também o SHA-256 do original.
"""

import csv
import fnmatch
import io
import json
import zipfile
from collections.abc import Callable, Iterable

from rastro.coletores.arquivo import Redacao, Redator


def redator_json(campos: Iterable[str]) -> Redator:
    """Remove as chaves `campos` em qualquer nível do JSON (objetos dentro de listas etc.)."""
    alvo = frozenset(campos)

    def redigir(original: bytes) -> Redacao:
        removidos: set[str] = set()

        def limpar(no):
            if isinstance(no, dict):
                for k in alvo & no.keys():
                    removidos.add(k)
                return {k: limpar(v) for k, v in no.items() if k not in alvo}
            if isinstance(no, list):
                return [limpar(v) for v in no]
            return no

        dados = limpar(json.loads(original))
        conteudo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode()
        return Redacao(
            conteudo,
            sorted(removidos),
            f"JSON regravado sem as chaves: {', '.join(sorted(alvo))}",
        )

    return redigir


# Ajuste por linha: altera a linha no lugar e devolve os nomes dos campos alterados.
Transformacao = Callable[[dict], list[str]]


def _redigir_csv(
    texto: str,
    remover: frozenset[str],
    filtro: Callable[[dict], bool] | None,
    delimitador: str,
    transformar: Transformacao | None = None,
    alterados: dict[str, int] | None = None,
) -> tuple[str, list[str], int, int]:
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    colunas = leitor.fieldnames or []
    ficam = [c for c in colunas if c not in remover]
    saida = io.StringIO()
    escritor = csv.DictWriter(
        saida,
        fieldnames=ficam,
        delimiter=delimitador,
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
        extrasaction="ignore",
    )
    escritor.writeheader()
    total = mantidas = 0
    for linha in leitor:
        total += 1
        if filtro is None or filtro(linha):
            if transformar is not None:
                for campo in transformar(linha):
                    alterados[campo] = alterados.get(campo, 0) + 1
            escritor.writerow(linha)
            mantidas += 1
    return saida.getvalue(), [c for c in colunas if c in remover], total, mantidas


def redator_csv(
    colunas: Iterable[str],
    *,
    filtro: Callable[[dict], bool] | None = None,
    descricao_filtro: str = "",
    delimitador: str = ";",
    encoding: str = "utf-8-sig",
    membro_zip: str | None = None,
    transformar: Transformacao | None = None,
) -> Redator:
    """Remove colunas (e, opcionalmente, linhas) de um CSV, ou de um CSV dentro de um ZIP.

    `transformar` apaga valores pessoais linha a linha (ex.: CPF de fornecedor pessoa
    física); os campos alterados entram na lista de removidos com a quantidade de linhas.

    Com `membro_zip` (padrão glob, ex.: "*_SP.csv"), o original é um ZIP: grava-se só o
    CSV do membro correspondente (exatamente um), já redigido, em UTF-8.
    """
    remover = frozenset(colunas)

    def redigir(original: bytes) -> Redacao:
        origem = ""
        if membro_zip:
            with zipfile.ZipFile(io.BytesIO(original)) as z:
                nomes = [n for n in z.namelist() if fnmatch.fnmatch(n, membro_zip)]
                if len(nomes) != 1:
                    raise ValueError(f"ZIP: esperado 1 membro {membro_zip!r}, achados {nomes}")
                origem = f"membro {nomes[0]} do ZIP; "
                bruto = z.read(nomes[0])
        else:
            bruto = original
        alterados: dict[str, int] = {}
        texto, removidas, total, mantidas = _redigir_csv(
            bruto.decode(encoding), remover, filtro, delimitador, transformar, alterados
        )
        faltando = remover - set(removidas)
        if faltando:
            # coluna esperada não existe: o layout mudou; melhor falhar do que gravar errado
            raise ValueError(f"colunas a remover ausentes no arquivo: {sorted(faltando)}")
        descricao = (
            f"{origem}CSV regravado em UTF-8 sem {len(removidas)} coluna(s); "
            f"{mantidas} de {total} linhas" + (f" ({descricao_filtro})" if descricao_filtro else "")
        )
        removidas += [f"{c} ({n} linhas)" for c, n in sorted(alterados.items())]
        if alterados:
            descricao += "; valores apagados: " + ", ".join(
                f"{c} em {n} linhas" for c, n in sorted(alterados.items())
            )
        return Redacao(texto.encode("utf-8"), removidas, descricao)

    return redigir


def redigir_arquivadas(session, regras: list[tuple[str, Redator]]) -> int:
    """Aplica a redação a respostas JÁ arquivadas sem ela (coletas anteriores à regra).

    `regras`: (expressão regular sobre a URL, redator). O conteúdo antigo é substituído
    pela versão redigida; `sha256_original` fica com o hash do que havia sido gravado
    (os bytes originais da fonte) e o payload antigo é apagado se nada mais o usa.
    """
    import gzip
    import re
    from datetime import UTC, datetime

    from sqlalchemy import func, select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from rastro.coletores.arquivo import ler_payload, sha256
    from rastro.models import PayloadBruto, RespostaBruta

    compiladas = [(re.compile(p), r) for p, r in regras]
    feitas = 0
    pendentes = session.scalars(
        select(RespostaBruta)
        .where(RespostaBruta.sha256_original.is_(None), RespostaBruta.status_http < 300)
        .order_by(RespostaBruta.id)
    ).all()
    for resp in pendentes:
        redator = next((r for p, r in compiladas if p.search(resp.url)), None)
        if redator is None:
            continue
        antigo = session.get(PayloadBruto, resp.sha256)
        red = redator(ler_payload(antigo))
        novo = sha256(red.conteudo)
        session.execute(
            pg_insert(PayloadBruto)
            .values(
                sha256=novo,
                tamanho=len(red.conteudo),
                compressao="gzip",
                conteudo=gzip.compress(red.conteudo, mtime=0),
            )
            .on_conflict_do_nothing(index_elements=["sha256"])
        )
        resp.sha256_original, resp.tamanho_original = resp.sha256, resp.tamanho
        resp.sha256, resp.tamanho = novo, len(red.conteudo)
        resp.campos_removidos = red.campos_removidos
        resp.redacao = f"{red.descricao} (redigido em {datetime.now(UTC):%Y-%m-%d}, após a coleta)"
        session.flush()
        em_uso = session.scalar(
            select(func.count())
            .select_from(RespostaBruta)
            .where(RespostaBruta.sha256 == antigo.sha256)
        )
        if not em_uso:
            session.delete(antigo)
        feitas += 1
    session.commit()
    return feitas
