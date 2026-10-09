import argparse
import logging
import sys

from rastro.coletores import COLETORES, siconfi_demonstrativos
from rastro.coletores.base import executar, novo_cliente
from rastro.db import get_sessionmaker


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["siconfi-lote"]:
        from rastro.coletores import siconfi_lote

        return siconfi_lote.main(argv[1:])
    if argv[:1] == ["politicos"]:
        from rastro.politicos import coletar

        return coletar.main(argv[1:])

    parser = argparse.ArgumentParser(prog="rastro")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("coletar", help="executa coletores")
    p.add_argument("fontes", nargs="*", help="fontes a coletar (padrão: todas)")
    sub.add_parser("fontes", help="lista as fontes disponíveis")
    vr = sub.add_parser(
        "verificar-respostas",
        help="recalcula o SHA-256 das respostas brutas arquivadas",
    )
    vr.add_argument("--amostra", type=int, help="verifica só N payloads sorteados")
    sub.add_parser("testar-fontes", help="testa o acesso às APIs oficiais a partir desta máquina")
    ex = sub.add_parser("exportar-site", help="gera os arquivos estáticos do site (JSON)")
    ex.add_argument("--uf", default="SP")
    ex.add_argument("--saida", required=True, help="pasta de saída (ex.: ../frontend/dist/dados)")
    ex.add_argument(
        "--completa",
        action="store_true",
        help="refaz tudo, sem reaproveitar a exportação anterior que estiver na pasta",
    )
    ex.add_argument(
        "--sem-ranking", action="store_true", help="prévia: não exporta o ranking nem as notas"
    )
    pb = sub.add_parser(
        "publicar-site", help="verifica e publica o site no GitHub Pages (branch gh-pages)"
    )
    pb.add_argument("--dist", required=True, help="frontend compilado, com dados/ dentro")
    pb.add_argument("--repo", default="https://github.com/fasn98/rastro-publico.git")
    pb.add_argument(
        "--simular",
        action="store_true",
        help="só verifica contra o site publicado; não envia nada",
    )
    bx = sub.add_parser(
        "baixar-site",
        help="copia o dados/ publicado no gh-pages (ponto de partida da exportação incremental)",
    )
    bx.add_argument("--saida", required=True, help="pasta vazia de destino")
    bx.add_argument("--repo", default="https://github.com/fasn98/rastro-publico.git")
    lp = sub.add_parser("listar-publicacoes", help="lista as publicações guardadas (snapshots)")
    lp.add_argument("--repo", default="https://github.com/fasn98/rastro-publico.git")
    rv = sub.add_parser("reverter-site", help="volta o site para a publicação anterior")
    rv.add_argument("--repo", default="https://github.com/fasn98/rastro-publico.git")
    rv.add_argument("--para", help="tag de destino (padrão: a anterior à que está no ar)")
    ce = sub.add_parser(
        "coleta-exclusiva",
        help="roda o comando só se nenhuma outra coleta estiver em andamento (trava no banco)",
    )
    ce.add_argument("argv", nargs=argparse.REMAINDER, help="ex.: bash scripts/coleta_sp.sh")
    rs = sub.add_parser(
        "resumo-coleta",
        help="situação de cada fonte nesta coleta (linha 'Fontes com falha: ...')",
    )
    rs.add_argument("--desde", help="início da coleta (ISO 8601); padrão: última tentativa")
    sub.add_parser(
        "conferir-producao",
        help="recusa a credencial de desenvolvimento (rastro:rastro) no banco de produção",
    )
    sub.add_parser(
        "conferir-codigo",
        help="avisa se o código em disco está atrás do main do GitHub (imprime o commit)",
    )
    sub.add_parser(
        "criar-usuario-auditoria",
        help="cria o usuário só de leitura da API de auditoria, com senha forte gerada",
    )
    sub.add_parser(
        "redigir-respostas",
        help="aplica a redação LGPD a respostas já arquivadas (remove dados pessoais)",
    )
    rc = sub.add_parser(
        "reconstruir",
        help="reconstrói linhas do RREO/RGF a partir do arquivo bruto (sem chamar a API)",
    )
    rc.add_argument("--anexo", help='ex.: "RGF-Anexo 01"')
    rc.add_argument("--cod-conta", nargs="+")
    rc.add_argument("--coluna", nargs="+")
    rc.add_argument("--ente", type=int, nargs="+")
    rc.add_argument("--exercicio", type=int, nargs="+")
    rc.add_argument("--demonstrativo", type=int, nargs="+")
    rc.add_argument("--gravar", action="store_true", help="insere em conta_demonstrativo")
    am = sub.add_parser(
        "aplicar-mapeamento",
        help="alinha conta_demonstrativo ao mapeamento_siconfi.yaml usando o arquivo bruto",
    )
    am.add_argument(
        "--podar", action="store_true", help="apaga linhas fora do mapeamento (ficam no bruto)"
    )
    am.add_argument("--tipo", help='só um tipo de relatório: "RGF" (RGF e RGF Simplificado)')
    am.add_argument(
        "--se-mudou",
        action="store_true",
        help="não faz nada se esta versão do mapeamento já foi aplicada a esse tipo",
    )
    r = sub.add_parser("ranking", help="calcula e grava o Ranking Fiscal de uma UF")
    r.add_argument("--uf", required=True)
    sub.add_parser(
        "politicos",
        help="coleta deputados federais, senadores e emendas (ver `rastro politicos --help`)",
        add_help=False,
    )
    sub.add_parser(
        "siconfi-lote",
        help="coleta RREO/RGF em lote, retomável (ver `rastro siconfi-lote --help`)",
        add_help=False,
    )

    d = sub.add_parser(
        "siconfi-demonstrativos",
        help="coleta RREO e RGF do SICONFI (requer `rastro coletar siconfi-entes` antes)",
    )
    d.add_argument("--exercicio", type=int, nargs="+", required=True)
    alvo = d.add_argument_group("entes (informe ao menos um filtro, ou --todos)")
    alvo.add_argument("--ente", type=int, nargs="+", help="código IBGE do ente")
    alvo.add_argument("--uf", nargs="+", help="ex.: SP RJ")
    alvo.add_argument("--esfera", nargs="+", choices=["U", "E", "D", "M"])
    alvo.add_argument("--todos", action="store_true", help="todos os 5.598 entes")
    d.add_argument("--forcar", action="store_true", help="baixa de novo mesmo sem retificação")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # uma linha por requisição lota o log (a exportação faz milhares, internas); erros e
    # avisos do httpx continuam aparecendo
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.comando == "fontes":
        print("\n".join(COLETORES))
        return 0

    if args.comando == "reconstruir":
        return _reconstruir(parser, args)

    if args.comando == "aplicar-mapeamento":
        from rastro import reconstrucao

        with get_sessionmaker()() as session:
            resumo = reconstrucao.aplicar_mapeamento(
                session, podar=args.podar, tipo=args.tipo, se_mudou=args.se_mudou
            )
        if resumo["pulado"]:
            print(f"mapeamento {resumo['mapeamento']} já aplicado ({args.tipo or 'todos'})")
            return 0
        print(
            f"mapeamento {resumo['mapeamento']}: {resumo['reconstruidas']} linhas reconstruídas "
            f"do arquivo bruto, {resumo['podadas']} podadas"
        )
        return 0

    if args.comando == "verificar-respostas":
        return _verificar_respostas(args.amostra)

    if args.comando == "coleta-exclusiva":
        from rastro.db import get_engine
        from rastro.trava import executar_exclusivo

        if not args.argv:
            parser.error(
                "informe o comando, ex.: rastro coleta-exclusiva bash scripts/coleta_sp.sh"
            )
        return executar_exclusivo(get_engine(), args.argv)

    if args.comando == "resumo-coleta":
        from datetime import datetime

        from rastro import fontes

        desde = datetime.fromisoformat(args.desde) if args.desde else None
        with get_sessionmaker()() as session:
            situacao = fontes.status(session, desde)
        for f in situacao:
            marca = (
                "ok   "
                if f["atualizada_nesta_coleta"]
                else "FALHA"
                if f["tentada_nesta_coleta"]
                else "-    "
            )
            print(
                f"{marca} {f['fonte']:<16} última atualização: {f['ultima_atualizacao'] or 'nunca'}"
            )
        print(fontes.resumo(situacao))
        return 0

    if args.comando == "conferir-codigo":
        import os
        from pathlib import Path

        import httpx

        from rastro import versao_codigo

        token = os.environ.get("RASTRO_GITHUB_TOKEN")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "rastro-publico"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # cliente sem arquivo bruto: a lista de commits traz e-mails de autores (LGPD)
        commit = versao_codigo.conferir(
            Path(__file__).resolve().parents[3],
            lambda: httpx.Client(headers=headers, timeout=30),
            lambda texto: print(texto, file=sys.stderr, flush=True),
        )
        if commit:
            print(commit)
        return 0

    if args.comando in ("conferir-producao", "criar-usuario-auditoria"):
        return _seguranca(args.comando)

    if args.comando == "testar-fontes":
        from rastro.testar_fontes import testar

        resultados = testar()
        for r in resultados:
            situacao = "OK   " if r["ok"] else "FALHA"
            print(f"{situacao} {r['fonte']:<28} {r['detalhe']} ({r['segundos']} s)")
        return 0 if all(r["ok"] for r in resultados) else 1

    if args.comando == "exportar-site":
        from pathlib import Path

        from rastro import site

        m = site.exportar(
            Path(args.saida), args.uf, completa=args.completa, sem_ranking=args.sem_ranking
        )
        e = m["exportacao"]
        print(
            f"Site exportado: {e['arquivos']} arquivos, {e['bytes'] / 1e6:.1f} MB, "
            f"{m['contagens']['municipios']} municípios, {m['contagens']['politicos']} políticos; "
            f"{e['escritos']} arquivos gravados ({e['bytes_escritos'] / 1e6:.1f} MB), "
            f"{e['removidos']} removidos, {e['grupos_reaproveitados']}/{e['grupos']} grupos "
            f"reaproveitados, {e['segundos']} s, pico de memória {e['memoria_pico_mb']} MB"
        )
        return 0

    if args.comando in ("publicar-site", "baixar-site", "listar-publicacoes", "reverter-site"):
        return _publicacao(args)

    if args.comando == "redigir-respostas":
        from rastro.coletores.redacao import redigir_arquivadas
        from rastro.politicos import lgpd

        with get_sessionmaker()() as session:
            n = redigir_arquivadas(session, lgpd.REGRAS)
        print(f"{n} resposta(s) arquivada(s) regravada(s) sem dados pessoais")
        return 0

    if args.comando == "ranking":
        from rastro import ranking

        met = ranking.carregar_metodologia()
        with get_sessionmaker()() as session:
            itens = ranking.calcular(session, args.uf, met)
        com_nota = sum(1 for i in itens if i["nota"] is not None)
        print(
            f"Ranking {args.uf.upper()} v{met.versao} ({met.hash}), exercícios "
            f"{met.exercicios}: {com_nota}/{len(itens)} municípios com nota"
        )
        # distribuição da transparência (indicador provisório: rever se quase todos = 100%)
        notas_t = [
            i["componentes"]["transparencia"]["nota"]
            for i in itens
            if i["componentes"]["transparencia"]["nota"] is not None
        ]
        if notas_t:
            print(f"Transparência ({len(notas_t)} municípios com extrato coletado):")
            faixas_t = [(1.0, 1.0, "100%"), (0.75, 0.9999, "75–99%"), (0.5, 0.7499, "50–74%"),
                        (0.0, 0.4999, "0–49%")]  # fmt: skip
            for de, ate, rotulo in faixas_t:
                n = sum(1 for v in notas_t if de <= v <= ate)
                print(f"  {rotulo:>7}: {n:4d} ({n / len(notas_t):.0%})")
        return 0

    if args.comando == "siconfi-demonstrativos":
        return _demonstrativos(parser, args)

    desconhecidas = set(args.fontes) - set(COLETORES)
    if desconhecidas:
        parser.error(f"fonte(s) desconhecida(s): {', '.join(sorted(desconhecidas))}")

    from rastro.fontes import executar_com_esperas

    falhas = 0
    with get_sessionmaker()() as session:
        for fonte in args.fontes or list(COLETORES):
            coleta = executar_com_esperas(session, fonte, COLETORES[fonte], novo_cliente)
            print(f"{fonte}: {coleta.status} ({coleta.registros or 0} registros)")
            if coleta.erro:
                print(f"  erro: {coleta.erro}", file=sys.stderr)
                falhas += 1
    return 1 if falhas else 0


def _demonstrativos(parser: argparse.ArgumentParser, args) -> int:
    if not (args.ente or args.uf or args.esfera or args.todos):
        parser.error("informe --ente, --uf, --esfera ou --todos")
    with novo_cliente() as client, get_sessionmaker()() as session:
        entes = siconfi_demonstrativos.selecionar_entes(session, args.ente, args.uf, args.esfera)
        if not entes:
            print(
                "Nenhum ente encontrado. Rode `rastro coletar siconfi-entes` antes.",
                file=sys.stderr,
            )
            return 1
        if args.ente:
            faltando = set(args.ente) - {e.cod_ibge for e in entes}
            if faltando:
                print(f"Entes não cadastrados: {sorted(faltando)}", file=sys.stderr)
        print(f"{len(entes)} ente(s), exercício(s) {args.exercicio}")
        coletor = siconfi_demonstrativos.coletor(entes, args.exercicio, args.forcar)
        coleta = executar(session, "siconfi-demonstrativos", coletor, client)
    print(f"siconfi-demonstrativos: {coleta.status} ({coleta.registros or 0} linhas)")
    if coleta.erro:
        print(coleta.erro, file=sys.stderr)
    return 0 if coleta.status == "sucesso" else 1


def _reconstruir(parser: argparse.ArgumentParser, args) -> int:
    import csv

    from rastro import reconstrucao

    if not (args.anexo or args.cod_conta or args.demonstrativo):
        parser.error("informe ao menos --anexo, --cod-conta ou --demonstrativo")
    filtro = reconstrucao.Filtro(
        anexo=args.anexo,
        cod_conta=args.cod_conta,
        coluna=args.coluna,
        cod_ibge=args.ente,
        exercicio=args.exercicio,
        demonstrativo_id=args.demonstrativo,
    )
    with get_sessionmaker()() as session:
        linhas = list(reconstrucao.reconstruir(session, filtro))
        if args.gravar:
            n = reconstrucao.gravar(session, linhas)
            print(f"{len(linhas)} linhas reconstruídas, {n} novas gravadas", file=sys.stderr)
            return 0
    w = csv.writer(sys.stdout, delimiter=";")
    w.writerow(["demonstrativo_id", "anexo", "rotulo", "cod_conta", "conta", "coluna", "valor",
                "resposta_id"])  # fmt: skip
    for li in linhas:
        w.writerow([li.demonstrativo_id, li.anexo, li.rotulo, li.cod_conta, li.conta, li.coluna,
                    li.valor, li.resposta_id])  # fmt: skip
    print(f"{len(linhas)} linhas", file=sys.stderr)
    return 0


def _publicacao(args) -> int:
    import os
    from pathlib import Path

    from rastro import publicacao

    token = os.environ.get("RASTRO_GITHUB_TOKEN")
    try:
        if args.comando == "publicar-site":
            tag = publicacao.publicar(Path(args.dist), args.repo, token, simular=args.simular)
            if args.simular:
                print(f"Simulação: verificação ok; nada foi publicado (seria {tag})")
            else:
                print(f"Site publicado: {tag}")
        elif args.comando == "baixar-site":
            m = publicacao.baixar_publicado(args.repo, Path(args.saida), token)
            if m:
                print(
                    f"Base publicada copiada: gerada em {m.get('gerado_em')}, "
                    f"formato {m.get('formato')}"
                )
            else:
                print("Nenhuma publicação anterior: a exportação será completa.")
        elif args.comando == "listar-publicacoes":
            for p in publicacao.listar(args.repo, token):
                print(f"{p['tag']}  {p['sha'][:10]}{'  <- no ar' if p['no_ar'] else ''}")
        else:
            print(f"Site revertido para {publicacao.reverter(args.repo, token, args.para)}")
    except publicacao.ErroPublicacao as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def _verificar_respostas(amostra: int | None = None) -> int:
    from sqlalchemy import func, select

    from rastro.coletores.arquivo import ler_payload
    from rastro.models import PayloadBruto, RespostaBruta

    with get_sessionmaker()() as session:
        total = ruins = 0
        q = select(PayloadBruto)
        if amostra:
            q = q.order_by(func.random()).limit(amostra)
        for p in session.scalars(q.execution_options(yield_per=200)):
            total += 1
            try:
                ler_payload(p)
            except ValueError as exc:
                ruins += 1
                print(exc, file=sys.stderr)
        respostas = session.scalar(select(func.count()).select_from(RespostaBruta))
    print(f"{respostas} respostas, {total} payloads distintos verificados, {ruins} com problema")
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())


def _seguranca(comando: str) -> int:
    from rastro import seguranca
    from rastro.config import get_settings
    from rastro.db import get_engine

    try:
        seguranca.conferir_producao(get_settings().database_url)
        if comando == "conferir-producao":
            print("Banco de produção: credencial própria (não é a de desenvolvimento).")
            return 0
        url = seguranca.criar_usuario_auditoria(get_engine())
    except seguranca.ErroSeguranca as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        if comando == "criar-usuario-auditoria":
            print(
                "Sem usuário só de leitura: a API de auditoria usará a string principal. "
                "Registre como risco aceito (docs/deploy-replit.md, passo 7).",
                file=sys.stderr,
            )
        return 1
    print(f"Usuário {seguranca.USUARIO_AUDITORIA} pronto (só leitura, 4 tabelas).")
    print("Copie a linha abaixo para o Secret DATABASE_URL do app rastro-auditoria.")
    print("Ela não é guardada em lugar nenhum; se perder, rode o comando de novo (troca a senha).")
    print(url.set(drivername="postgresql").render_as_string(hide_password=False))
    return 0
