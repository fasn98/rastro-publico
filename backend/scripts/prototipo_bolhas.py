"""Protótipo do mapa de bolhas: dados REAIS da amostra, com a trilha até a resposta bruta.

Uso (na pasta backend/):

    uv run python scripts/prototipo_bolhas.py --saida <arquivo.json>

Lê o banco e a própria API (em processo, como a exportação do site). Nada é estimado:
um ponto sem algum dos valores não é desenhado e entra na contagem de "fora do gráfico",
com o motivo. A população por ano é baixada do IBGE (agregados 6579 e 4709) pelo cliente
dos coletores, então cada resposta fica no arquivo bruto com o SHA-256.

Este script é só do protótipo (etapa 1). A implementação (etapa 2) vai para site.py.
"""

import argparse
import calendar
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from rastro.api.main import app
from rastro.coletores.base import get_json_com_origem, novo_cliente
from rastro.db import get_sessionmaker
from rastro.models import DemonstrativoSiconfi, RespostaBruta
from rastro.politicos.modelos import PolDespesaCota, PolEmenda, PolEventoMandato, PolPolitico
from rastro.reconstrucao import linhas_brutas

AMOSTRA = [3500105, 3507209, 3509502, 3526308, 3539103, 3542602, 3548500, 3548807, 3550308, 3555406]
ESTADO_SP = 35
ANOS_ENTES = [2022, 2023, 2024, 2025]
ANO_LEGISLATIVO = 2025
ULTIMO_EXERCICIO_ENCERRADO = 2025
PERIODOS_RGF = {"S": "semestre", "Q": "quadrimestre"}
DEPUTADOS_COM_LANCAMENTOS = 3  # no protótipo, lançamentos item a item só destes

IBGE = "https://servicodados.ibge.gov.br/api/v3/agregados"
URL_ESTIMATIVAS = IBGE + "/6579/periodos/2021|2024|2025|2026/variaveis/9324"
URL_CENSO = IBGE + "/4709/periodos/2022/variaveis/93"

# Limites mensais da CEAP por UF (Câmara). Fonte: Anexo Único do Ato da Mesa nº 43/2009,
# na redação do Ato da Mesa nº 270/2023, em vigor em 1º/2/2023 (norma consolidada).
# O Ato da Mesa nº 244/2026 (20/2/2026) manda atualizar pelo IPCA de fev/2023 a dez/2025,
# mas não publica a tabela; os valores atualizados aparecem só no "Guia para jornalistas",
# sem data. Por isso o protótipo usa só 2025, inteiro sob o Ato 270/2023.
FONTE_LIMITES = {
    "ato": "Ato da Mesa nº 43/2009, Anexo Único, redação do Ato da Mesa nº 270/2023",
    "vigencia": {"inicio": "2023-02-01", "fim": "2026-02-19"},
    "url": "https://www2.camara.leg.br/legin/int/atomes/2009/"
    "atodamesa-43-21-maio-2009-588364-normaatualizada-cd-mesa.pdf",
    "url_ato_270": "https://www2.camara.leg.br/legin/int/atomes/2023/"
    "atodamesa-270-19-janeiro-2023-793708-publicacaooriginal-166895-cd-mesa.html",
    "url_ato_244": "https://www2.camara.leg.br/legin/int/atomes/2026/"
    "atodamesa-244-20-fevereiro-2026-798720-publicacaooriginal-178157-cd-mesa.html",
}
LIMITE_MENSAL_ATO_270 = {
    "AC": "50426.26", "AL": "46737.90", "AM": "49363.92", "AP": "49168.58", "BA": "44804.65",
    "CE": "48245.57", "DF": "36582.46", "ES": "43217.71", "GO": "41300.86", "MA": "47945.49",
    "MG": "41886.51", "MS": "46336.64", "MT": "45221.83", "PA": "48021.25", "PB": "47826.36",
    "PE": "47470.60", "PI": "46765.57", "PR": "44665.66", "RJ": "41553.77", "RN": "48525.79",
    "RO": "49466.29", "RR": "51406.33", "RS": "46669.70", "SC": "45671.58", "SE": "45933.06",
    "SP": "42837.33", "TO": "45297.41",
}  # fmt: skip


def num(v) -> float | None:
    return None if v is None else float(v)


class Gerador:
    def __init__(self):
        self.api = TestClient(app)
        self.s = get_sessionmaker()()
        self.respostas: dict[int, dict] = {}

    def get(self, url: str):
        r = self.api.get(url)
        r.raise_for_status()
        return r.json()

    def resposta(self, rid: int | None) -> str | None:
        """Guarda a resposta bruta (uma vez) e devolve a chave dela."""
        if rid is None:
            return None
        if rid not in self.respostas:
            r = self.s.get(RespostaBruta, rid)
            self.respostas[rid] = {
                "url": r.url,
                "sha256": r.sha256,
                "recebido_em": r.recebido_em.isoformat(),
                "tamanho": r.tamanho,
                "sha256_original": r.sha256_original,
                "campos_removidos": r.campos_removidos,
            }
        return str(rid)

    # ------------------------------------------------------------------ população
    def populacao(self) -> dict:
        """{cod: {ano: {valor, fonte, resposta}}}: estimativas (6579) e Censo 2022 (4709)."""
        locais = "N6[" + ",".join(map(str, AMOSTRA)) + f"]|N3[{ESTADO_SP}]"
        saida: dict = defaultdict(dict)
        with novo_cliente() as client:
            for url, fonte in (
                (URL_ESTIMATIVAS, "IBGE, Estimativas de População (SIDRA 6579)"),
                (URL_CENSO, "IBGE, Censo Demográfico 2022 (SIDRA 4709)"),
            ):
                dados, rid = get_json_com_origem(client, url, params={"localidades": locais})
                chave = self.resposta(rid)
                for s in dados[0]["resultados"][0]["series"]:
                    for ano, valor in s["serie"].items():
                        if valor.isdigit():
                            saida[int(s["localidade"]["id"])][int(ano)] = {
                                "valor": int(valor),
                                "fonte": fonte,
                                "resposta": chave,
                            }
        return saida

    # ------------------------------------------------------------------ entes
    def linhas(self, demonstrativo_id: int, filtros: list[tuple[str, str]]) -> list[dict]:
        """Linhas do demonstrativo usadas no cálculo, cada uma com o item original da API."""
        d = self.s.get(DemonstrativoSiconfi, demonstrativo_id)
        contas = self.get(f"/api/demonstrativos/{demonstrativo_id}/contas")
        brutos = {}
        for item, rid in linhas_brutas(self.s, d):
            brutos[(item["anexo"], item["cod_conta"], item["coluna"], item.get("rotulo"))] = (
                item,
                rid,
            )
        saida = []
        for c in contas:
            if (c["cod_conta"], c["coluna"]) not in filtros:
                continue
            item, rid = brutos.get(
                (c["anexo"], c["cod_conta"], c["coluna"], c["rotulo"]), (None, None)
            )
            saida.append(
                {
                    "demonstrativo": d.demonstrativo,
                    "exercicio": d.exercicio,
                    "periodicidade": d.periodicidade,
                    "periodo": d.periodo,
                    "instituicao": d.instituicao,
                    "anexo": c["anexo"],
                    "rotulo": c["rotulo"],
                    "cod_conta": c["cod_conta"],
                    "conta": c["conta"],
                    "coluna": c["coluna"],
                    "valor": c["valor"],
                    "resposta": self.resposta(c["resposta_id"] or rid),
                    "item_original": json.loads(json.dumps(item, default=str)) if item else None,
                }
            )
        return saida

    def entes(self, pop: dict) -> tuple[list, list, dict]:
        pontos, fora, trilhas = [], [], {}
        for cod in [*AMOSTRA, ESTADO_SP]:
            serie = self.get(f"/api/entes/{cod}/indicadores/serie")
            nome = self.get(f"/api/municipios/{cod}")["nome"] if cod != ESTADO_SP else "São Paulo"
            for a in serie:
                ano = a["exercicio"]
                ex = a.get("execucao")
                pes = next((p for p in a.get("pessoal") or [] if p["poder"] == "E"), None)
                p = pop.get(cod, {}).get(ano)
                ident = {
                    "id": f"{cod}-{ano}",
                    "cod": cod,
                    "nome": nome,
                    "esfera": "E" if cod == ESTADO_SP else "M",
                    "uf": "SP",
                    "ano": ano,
                }
                motivo = None
                if not ex or not ex.get("receita_realizada") or not ex.get("despesa_empenhada"):
                    motivo = "sem RREO com receita realizada e despesa empenhada"
                elif not p:
                    motivo = f"sem população oficial do IBGE para {ano}"
                elif not pes:
                    motivo = "sem RGF do Executivo (situação na LRF)"
                if motivo:
                    fora.append({**ident, "motivo": motivo})
                    continue
                receita = Decimal(ex["receita_realizada"])
                empenhada = Decimal(ex["despesa_empenhada"])
                pontos.append(
                    {
                        **ident,
                        "x": float(receita / p["valor"]),
                        "y": float(empenhada / receita),
                        "tamanho": p["valor"],
                        "receita_realizada": num(receita),
                        "despesa_empenhada": num(empenhada),
                        "periodo_rreo": {
                            "periodicidade": ex["periodicidade"],
                            "periodo": ex["periodo"],
                            "final": ex["periodo_final"],
                        },
                        "populacao": p,
                        "lrf": {
                            "percentual": num(pes["percentual"]),
                            "alerta": num(pes["limite_alerta"]),
                            "prudencial": num(pes["limite_prudencial"]),
                            "maximo": num(pes["limite_maximo"]),
                            "situacao": pes["situacao"],
                            "instituicao": pes["instituicao"],
                            "periodo": f"{pes['periodo']}º {PERIODOS_RGF[pes['periodicidade']]}",
                        },
                    }
                )
                trilhas[f"{cod}-{ano}"] = {
                    "rreo": self.linhas(
                        ex["demonstrativo_id"],
                        [
                            ("TotalReceitas", "Até o Bimestre (c)"),
                            ("TotalDespesas", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)"),
                        ],
                    ),
                    "rgf": self.linhas(
                        pes["demonstrativo_id"],
                        [
                            ("DespesaComPessoalTotal", "% sobre a RCL Ajustada"),
                            ("LimiteDeAlertaDespesaComPessoalTotal", "% sobre a RCL Ajustada"),
                            ("LimitePrudencialDespesaComPessoalTotal", "% sobre a RCL Ajustada"),
                            ("LimiteMaximoDespesaComPessoalTotal", "% sobre a RCL Ajustada"),
                        ],
                    ),
                }
        return pontos, fora, trilhas

    # ------------------------------------------------------------------ executivo
    def executivo(self, entes: list) -> tuple[list, list]:
        """Prefeitos (eleitos 2024) e governador (eleito 2022) com os exercícios do mandato.

        O TSE não traz datas de mandato; o período sai da Constituição: prefeito eleito em
        2024 exerce de 2025 a 2028 (art. 29, III); governador eleito em 2022, de 2023 a 2026
        (art. 28). O 1º exercício executa o orçamento aprovado na gestão anterior.
        """
        por_ente = {(p["cod"], p["ano"]): p for p in entes}
        pontos, fora = [], []
        eleitos = self.s.scalars(
            select(PolPolitico).where(
                PolPolitico.fonte == "tse",
                (
                    (PolPolitico.cargo == "prefeito")
                    & PolPolitico.cod_ibge.in_(AMOSTRA)
                    & (PolPolitico.eleicao_ano == 2024)
                )
                | (
                    (PolPolitico.cargo == "governador")
                    & (PolPolitico.uf == "SP")
                    & (PolPolitico.eleicao_ano == 2022)
                ),
            )
        ).all()
        for pol in eleitos:
            cod = pol.cod_ibge if pol.cargo == "prefeito" else ESTADO_SP
            inicio = pol.eleicao_ano + 1
            for ano in range(inicio, inicio + 4):
                if ano > ULTIMO_EXERCICIO_ENCERRADO:
                    continue  # exercício em curso ou futuro: não é dado ausente
                base = por_ente.get((cod, ano))
                ident = {
                    "id": f"{pol.id}-{ano}",
                    "politico_id": pol.id,
                    "nome": pol.nome,
                    "partido": pol.partido,
                    "cargo": pol.cargo,
                    "ente": cod,
                    "ente_nome": base["nome"] if base else None,
                    "ano": ano,
                    "mandato": f"{inicio}–{inicio + 3}",
                    "primeiro_exercicio": ano == inicio,
                    "fonte_eleicao": {
                        "url": pol.url_fonte,
                        "resposta": self.resposta(pol.resposta_id),
                    },
                }
                if base is None:
                    fora.append(
                        {**ident, "motivo": f"dados fiscais de {ano} não coletados para o ente"}
                    )
                    continue
                pontos.append(
                    {
                        **ident,
                        **{
                            k: base[k]
                            for k in (
                                "x",
                                "y",
                                "tamanho",
                                "lrf",
                                "receita_realizada",
                                "despesa_empenhada",
                                "populacao",
                                "periodo_rreo",
                            )
                        },
                        "trilha": f"{cod}-{ano}",
                    }
                )
        return pontos, fora

    # ------------------------------------------------------------------ legislativo
    def parlamentares(self) -> dict[int, PolPolitico]:
        return {
            p.id: p
            for p in self.s.scalars(
                select(PolPolitico).where(
                    PolPolitico.fonte.in_(["camara", "senado"]), PolPolitico.uf == "SP"
                )
            )
        }

    def emendas(self, pols: dict) -> tuple[list, list, dict]:
        linhas = self.s.scalars(
            select(PolEmenda).where(
                PolEmenda.ano == ANO_LEGISLATIVO, PolEmenda.politico_id.in_(pols)
            )
        ).all()
        grupos = defaultdict(list)
        for e in linhas:
            grupos[e.politico_id].append(e)
        pontos, fora, trilhas = [], [], {}
        for pid, pol in pols.items():
            ident = {
                "id": f"{pid}-{ANO_LEGISLATIVO}",
                "politico_id": pid,
                "nome": pol.nome,
                "partido": pol.partido,
                "cargo": pol.cargo,
                "uf": pol.uf,
                "ano": ANO_LEGISLATIVO,
            }
            es = grupos.get(pid, [])
            if not es:
                fora.append(
                    {
                        **ident,
                        "motivo": f"nenhuma emenda de {ANO_LEGISLATIVO} vinculada no arquivo "
                        "do Portal da Transparência",
                    }
                )
                continue

            def soma(campo: str, es=es) -> float:
                return float(sum((getattr(e, campo) or 0) for e in es))

            emp = soma("valor_empenhado")
            ponto = {
                **ident,
                "empenhado": emp,
                "liquidado": soma("valor_liquidado"),
                "pago": soma("valor_pago"),
                "rp_inscrito": soma("valor_resto_inscrito"),
                "rp_cancelado": soma("valor_resto_cancelado"),
                "rp_pago": soma("valor_resto_pago"),
                "n_emendas": len(es),
                "municipios": len({e.cod_ibge_destino for e in es if e.cod_ibge_destino}),
                "sem_municipio": sum(1 for e in es if not e.cod_ibge_destino),
            }
            if emp <= 0:
                fora.append({**ident, "motivo": "valor empenhado zero: percentuais indefinidos"})
                continue
            ponto["pct_liquidado"] = ponto["liquidado"] / emp
            ponto["pct_pago"] = ponto["pago"] / emp
            pontos.append(ponto)
            trilhas[str(pid)] = [
                {
                    "codigo": e.codigo_emenda,
                    "numero": e.numero_emenda,
                    "tipo": e.tipo_emenda,
                    "transferencia_especial": e.transferencia_especial,
                    "autor_no_arquivo": e.nome_autor,
                    "localidade": e.localidade_gasto,
                    "cod_ibge": e.cod_ibge_destino,
                    "funcao": e.funcao,
                    "subfuncao": e.subfuncao,
                    "acao": e.acao,
                    "empenhado": num(e.valor_empenhado),
                    "liquidado": num(e.valor_liquidado),
                    "pago": num(e.valor_pago),
                    "rp_inscrito": num(e.valor_resto_inscrito),
                    "rp_cancelado": num(e.valor_resto_cancelado),
                    "rp_pago": num(e.valor_resto_pago),
                    "linha_arquivo": e.linha,
                    "vinculo": e.vinculo,
                    "resposta": self.resposta(e.resposta_id),
                }
                for e in sorted(
                    es, key=lambda e: (e.localidade_gasto or "", e.funcao or "", e.codigo_emenda)
                )
            ]
        return pontos, fora, trilhas

    def dias_por_situacao(self, pid: int, ano: int) -> dict[int, dict[str, int]] | None:
        """{mês: {"exercicio": dias, "licenca": dias}} pela linha do tempo da Câmara.

        Vale a última situação registrada até o dia (inclusive: o Ato da Mesa 43/2009,
        art. 11, conta o dia de assunção e o de afastamento). Eventos sem situação
        ("Nome no início da legislatura") não mudam o estado. None sem linha do tempo.
        """
        eventos = [
            e
            for e in self.s.scalars(
                select(PolEventoMandato)
                .where(PolEventoMandato.politico_id == pid)
                .order_by(PolEventoMandato.data_hora)
            )
            if e.situacao
        ]
        if not eventos:
            return None
        saida = {}
        for mes in range(1, 13):
            conta = {"exercicio": 0, "licenca": 0}
            for dia in range(1, calendar.monthrange(ano, mes)[1] + 1):
                d = date(ano, mes, dia)
                no_dia = [e.situacao for e in eventos if e.data_hora.date() == d]
                antes = [e.situacao for e in eventos if e.data_hora.date() < d]
                estados = ([antes[-1]] if antes else []) + no_dia
                if any(x == "Exercício" for x in estados):
                    conta["exercicio"] += 1
                elif any(x == "Licença" for x in estados):
                    conta["licenca"] += 1
            saida[mes] = conta
        return saida

    def cota(self, pols: dict) -> tuple[list, list, dict]:
        pontos, fora, trilhas = [], [], {}
        despesas = self.s.scalars(
            select(PolDespesaCota).where(
                PolDespesaCota.ano == ANO_LEGISLATIVO, PolDespesaCota.politico_id.in_(pols)
            )
        ).all()
        por_pol = defaultdict(list)
        for d in despesas:
            por_pol[d.politico_id].append(d)
        com_lancamentos = [
            pid
            for pid, _ in sorted(((p, len(v)) for p, v in por_pol.items()), key=lambda t: -t[1])[
                :DEPUTADOS_COM_LANCAMENTOS
            ]
        ]
        for pid, pol in pols.items():
            ident = {
                "id": f"{pid}-{ANO_LEGISLATIVO}",
                "politico_id": pid,
                "nome": pol.nome,
                "partido": pol.partido,
                "cargo": pol.cargo,
                "uf": pol.uf,
                "ano": ANO_LEGISLATIVO,
                "casa": pol.fonte,
            }
            ds = por_pol.get(pid, [])
            if pol.fonte == "senado":
                fora.append(
                    {
                        **ident,
                        "motivo": "CEAPS do Senado ainda não coletada; limites sem fonte "
                        "oficial estruturada com vigência",
                    }
                )
                continue
            if not ds:
                fora.append({**ident, "motivo": f"nenhum lançamento da cota em {ANO_LEGISLATIVO}"})
                continue
            total = float(sum((d.valor_liquido or 0) for d in ds))
            ponto = {**ident, "gasto": total, "lancamentos": len(ds)}
            dias = self.dias_por_situacao(pid, ANO_LEGISLATIVO)
            mensal = Decimal(LIMITE_MENSAL_ATO_270[pol.uf])
            if dias is None:
                ponto["limite"] = None
                ponto["motivo_sem_limite"] = "linha do tempo de exercício não coletada"
            else:
                # só os dias em "Exercício" (Ato da Mesa 43/2009, art. 12). As licenças que a
                # Câmara registra na linha do tempo (Ministro, Secretário, afastamento
                # consecutivo) vêm com convocação de suplente, fora do art. 11, § 2º
                limite = sum(
                    mensal * c["exercicio"] / calendar.monthrange(ANO_LEGISLATIVO, m)[1]
                    for m, c in dias.items()
                )
                ponto["limite"] = float(limite)
                ponto["dias_exercicio"] = sum(c["exercicio"] for c in dias.values())
                ponto["dias_licenca"] = sum(c["licenca"] for c in dias.values())
                ponto["razao"] = total / float(limite) if limite else None
                if not limite:
                    ponto["motivo_sem_limite"] = (
                        f"sem dias em exercício em {ANO_LEGISLATIVO} na linha do tempo"
                    )
            pontos.append(ponto)
            meses = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
            for d in ds:
                c = meses[d.mes][d.categoria]
                c[0] += 1
                c[1] += float(d.valor_liquido or 0)
            trilha = {
                "limite_mensal": float(mensal),
                "dias": dias,
                "meses": {
                    m: {cat: {"n": v[0], "valor": v[1]} for cat, v in sorted(cats.items())}
                    for m, cats in sorted(meses.items())
                },
                "resposta": self.resposta(ds[0].resposta_id),
                "lancamentos": None,
            }
            if pid in com_lancamentos:
                itens, deslocamento = [], 0
                while True:
                    pagina = self.get(
                        f"/api/politicos/{pid}/cota?ano={ANO_LEGISLATIVO}&limite=500&deslocamento={deslocamento}"
                    )["despesas"]
                    itens += pagina["itens"]
                    deslocamento += len(pagina["itens"])
                    if not pagina["itens"] or deslocamento >= pagina["total"]:
                        break
                trilha["lancamentos"] = [
                    {
                        k: it.get(k)
                        for k in (
                            "mes",
                            "categoria",
                            "fornecedor",
                            "cnpj",
                            "pessoa_fisica",
                            "numero_documento",
                            "data_emissao",
                            "valor_documento",
                            "valor_glosa",
                            "valor_liquido",
                            "url_documento",
                            "linha",
                        )
                    }
                    | {"resposta": self.resposta(it.get("resposta_id"))}
                    for it in itens
                ]
            trilhas[str(pid)] = trilha
        return pontos, fora, trilhas


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--saida", required=True)
    p.add_argument("--html", help="também grava a página do protótipo com os dados embutidos")
    args = p.parse_args()
    g = Gerador()
    pop = g.populacao()
    entes, entes_fora, trilhas_entes = g.entes(pop)
    executivo, executivo_fora = g.executivo(entes)
    pols = g.parlamentares()
    emendas, emendas_fora, trilhas_emendas = g.emendas(pols)
    cota, cota_fora, trilhas_cota = g.cota(pols)
    saida = {
        "gerado_em": datetime.now(UTC).isoformat(),
        "amostra": {"municipios": AMOSTRA, "estado": ESTADO_SP, "ano_legislativo": ANO_LEGISLATIVO},
        "limites_cota": {**FONTE_LIMITES, "valores": LIMITE_MENSAL_ATO_270},
        "entes": {"pontos": entes, "fora": entes_fora},
        "executivo": {"pontos": executivo, "fora": executivo_fora},
        "emendas": {"pontos": emendas, "fora": emendas_fora},
        "cota": {"pontos": cota, "fora": cota_fora},
        "trilhas": {"entes": trilhas_entes, "emendas": trilhas_emendas, "cota": trilhas_cota},
        "respostas": g.respostas,
    }
    Path(args.saida).write_text(
        json.dumps(saida, ensure_ascii=False, separators=(",", ":"), default=str)
    )
    if args.html:
        modelo = (Path(__file__).parent / "prototipo_bolhas.html").read_text()
        # "</" dentro de <script> fecharia a tag: o JSON vai com a barra escapada
        dados = json.dumps(saida, ensure_ascii=False, separators=(",", ":"), default=str)
        Path(args.html).write_text(modelo.replace("/*DADOS*/", dados.replace("</", "<\\/")))
    for modo in ("entes", "executivo", "emendas", "cota"):
        print(f"{modo}: {len(saida[modo]['pontos'])} pontos, {len(saida[modo]['fora'])} fora")
    print(
        f"{len(g.respostas)} respostas brutas referenciadas; "
        f"{Path(args.saida).stat().st_size / 1e6:.2f} MB"
    )


if __name__ == "__main__":
    main()
