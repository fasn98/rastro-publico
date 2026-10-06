"""Redação LGPD das fontes do módulo de políticos.

Nenhum CPF, data de nascimento, título de eleitor ou e-mail pode existir nas tabelas nem
no arquivo de respostas brutas. As regras abaixo valem na coleta (o redator vai na
requisição) e para respostas já arquivadas (`rastro redigir-respostas`).
"""

from rastro.coletores.redacao import redator_json

# Câmara, /deputados (listas): e-mail de gabinete
CAMARA_DEPUTADOS = redator_json({"email"})
# Senado, /senador/lista/*: e-mail de gabinete
SENADO_LISTA = redator_json({"EmailParlamentar"})

REGRAS = [
    (r"^https://dadosabertos\.camara\.leg\.br/api/v2/deputados(\?|$)", CAMARA_DEPUTADOS),
    (r"^https://legis\.senado\.leg\.br/dadosabertos/senador/lista/", SENADO_LISTA),
]
