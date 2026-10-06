"""Teste rápido de acesso às fontes oficiais a partir da máquina atual (ex.: o Replit).

Faz uma chamada pequena a cada fonte usada pelo portal e informa se respondeu. Não grava
nada no banco nem no arquivo bruto. Rode antes da primeira coleta numa plataforma nova:
algumas APIs públicas bloqueiam faixas de IP de nuvens estrangeiras.
"""

import time

import httpx

from rastro.config import get_settings

FONTES = [
    ("Tesouro / SICONFI (entes)", "https://apidatalake.tesouro.gov.br/ords/cdwhprd/siconfi/tt/entes?limit=1"),
    ("Tesouro / SICONFI (RREO)",
     "https://apidatalake.tesouro.gov.br/ords/cdwhprd/siconfi/tt/rreo?an_exercicio=2025"
     "&nr_periodo=6&co_tipo_demonstrativo=RREO&id_ente=3550308&no_anexo=RREO-Anexo%2001&limit=1"),
    ("IBGE / Localidades", "https://servicodados.ibge.gov.br/api/v1/localidades/estados/SP"),
    ("Câmara dos Deputados", "https://dadosabertos.camara.leg.br/api/v2/deputados?siglaUf=SP&itens=1"),
    ("Senado Federal", "https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json"),
]  # fmt: skip


def testar(cliente: httpx.Client | None = None) -> list[dict]:
    s = get_settings()
    proprio = cliente is None
    cliente = cliente or httpx.Client(
        timeout=s.http_timeout, headers={"User-Agent": s.user_agent}, follow_redirects=True
    )
    resultados = []
    try:
        for nome, url in FONTES:
            inicio = time.monotonic()
            try:
                r = cliente.get(url)
                ok = r.status_code == 200 and len(r.content) > 0
                detalhe = f"HTTP {r.status_code}, {len(r.content)} bytes"
            except httpx.HTTPError as exc:
                ok, detalhe = False, f"{type(exc).__name__}: {exc}"
            resultados.append(
                {"fonte": nome, "ok": ok, "detalhe": detalhe,
                 "segundos": round(time.monotonic() - inicio, 2)}
            )  # fmt: skip
            time.sleep(1 / s.req_por_segundo if s.req_por_segundo else 0)
    finally:
        if proprio:
            cliente.close()
    return resultados
