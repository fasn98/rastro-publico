"""Tabelas do módulo de políticos (prefixo `pol_`).

Cada linha guarda `resposta_id`: a resposta bruta (tabela `resposta_bruta`) de onde saiu.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from rastro.db import Base

# Cargos (códigos estáveis; o rótulo exibido fica no frontend)
DEPUTADO_FEDERAL = "deputado_federal"
SENADOR = "senador"
GOVERNADOR = "governador"
DEPUTADO_ESTADUAL = "deputado_estadual"
PREFEITO = "prefeito"
VEREADOR = "vereador"
CARGOS_ESTADUAIS = (GOVERNADOR, SENADOR, DEPUTADO_FEDERAL, DEPUTADO_ESTADUAL)
CARGOS_MUNICIPAIS = (PREFEITO, VEREADOR)


def _resposta():
    return mapped_column(BigInteger, ForeignKey("resposta_bruta.id"), index=True)


class PolPolitico(Base):
    """Um mandato: quem ocupa (ou ocupou) um cargo, segundo a fonte oficial.

    Só dados para identificar o mandato. Nada de CPF, data de nascimento, endereço,
    e-mail pessoal etc. (LGPD).
    """

    __tablename__ = "pol_politico"
    __table_args__ = (UniqueConstraint("fonte", "id_fonte", "cargo", name="uq_pol_politico"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fonte: Mapped[str] = mapped_column(String(20))  # camara | senado | tse
    id_fonte: Mapped[str] = mapped_column(String(40))  # id na fonte (Câmara, Senado, TSE)
    nome: Mapped[str] = mapped_column(String(200), index=True)  # nome parlamentar / de urna
    partido: Mapped[str | None] = mapped_column(String(30))
    cargo: Mapped[str] = mapped_column(String(30), index=True)
    uf: Mapped[str] = mapped_column(String(2), index=True)
    cod_ibge: Mapped[int | None] = mapped_column(Integer, index=True)  # só cargos municipais
    # como a fonte descreve a situação (ex.: "Exercício", "Titular", "1º Suplente")
    situacao: Mapped[str | None] = mapped_column(String(80))
    em_exercicio: Mapped[bool | None] = mapped_column(Boolean)
    legislatura: Mapped[int | None]
    mandato_inicio: Mapped[date | None] = mapped_column(Date)
    mandato_fim: Mapped[date | None] = mapped_column(Date)
    eleicao_ano: Mapped[int | None]
    url_fonte: Mapped[str] = mapped_column(Text)  # registro na API oficial
    url_pagina: Mapped[str | None] = mapped_column(Text)  # página oficial para pessoas
    resposta_id: Mapped[int | None] = _resposta()
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PolProposicao(Base):
    """Proposição/matéria em que o parlamentar consta como autor(a), segundo a fonte."""

    __tablename__ = "pol_proposicao"
    __table_args__ = (UniqueConstraint("politico_id", "id_fonte", name="uq_pol_proposicao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    politico_id: Mapped[int] = mapped_column(
        ForeignKey("pol_politico.id", ondelete="CASCADE"), index=True
    )
    id_fonte: Mapped[str] = mapped_column(String(40))
    sigla_tipo: Mapped[str | None] = mapped_column(String(20))
    numero: Mapped[str | None] = mapped_column(String(20))
    ano: Mapped[int] = mapped_column(Integer, index=True)
    ementa: Mapped[str | None] = mapped_column(Text)
    data_apresentacao: Mapped[date | None] = mapped_column(Date)
    # Senado: lista de autores como publicada; Câmara: nulo
    autoria: Mapped[str | None] = mapped_column(Text)
    url_fonte: Mapped[str] = mapped_column(Text)
    url_pagina: Mapped[str | None] = mapped_column(Text)
    resposta_id: Mapped[int | None] = _resposta()


class PolVotacao(Base):
    """Voto registrado do parlamentar em uma votação nominal."""

    __tablename__ = "pol_votacao"
    __table_args__ = (UniqueConstraint("politico_id", "id_votacao", name="uq_pol_votacao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    politico_id: Mapped[int] = mapped_column(
        ForeignKey("pol_politico.id", ondelete="CASCADE"), index=True
    )
    id_votacao: Mapped[str] = mapped_column(String(40))
    data: Mapped[date] = mapped_column(Date, index=True)
    voto: Mapped[str] = mapped_column(String(60))  # como registrado na fonte (ex.: "Sim", "AP")
    # descrição do voto quando a fonte a fornece (Senado: "Atividade parlamentar" etc.)
    voto_descricao: Mapped[str | None] = mapped_column(String(120))
    orgao: Mapped[str | None] = mapped_column(String(40))
    materia: Mapped[str | None] = mapped_column(String(80))  # ex.: "PLP 192/2023"
    descricao: Mapped[str | None] = mapped_column(Text)
    url_fonte: Mapped[str] = mapped_column(Text)
    resposta_id: Mapped[int | None] = _resposta()


class PolPresenca(Base):
    """Presença registrada pela Câmara em um evento (arquivo eventosPresencaDeputados)."""

    __tablename__ = "pol_presenca"
    __table_args__ = (UniqueConstraint("politico_id", "id_evento", name="uq_pol_presenca"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    politico_id: Mapped[int] = mapped_column(
        ForeignKey("pol_politico.id", ondelete="CASCADE"), index=True
    )
    id_evento: Mapped[str] = mapped_column(String(20))
    data_hora_inicio: Mapped[datetime] = mapped_column(DateTime, index=True)
    url_fonte: Mapped[str] = mapped_column(Text)
    resposta_id: Mapped[int | None] = _resposta()


class PolComissao(Base):
    """Participação em comissão (Senado), como publicada."""

    __tablename__ = "pol_comissao"

    id: Mapped[int] = mapped_column(primary_key=True)
    politico_id: Mapped[int] = mapped_column(
        ForeignKey("pol_politico.id", ondelete="CASCADE"), index=True
    )
    codigo: Mapped[str] = mapped_column(String(20))
    sigla: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str] = mapped_column(Text)
    casa: Mapped[str | None] = mapped_column(String(10))
    participacao: Mapped[str | None] = mapped_column(String(60))
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    url_fonte: Mapped[str] = mapped_column(Text)
    resposta_id: Mapped[int | None] = _resposta()


class PolEmenda(Base):
    """Emenda parlamentar (Portal da Transparência).

    Duas origens (`fonte_dados`): "arquivo" = download em lote EmendasParlamentares.csv
    (uma linha por emenda x local/ação, com o código IBGE oficial do município; `linha` é
    a posição no arquivo) e "api" = /api-de-dados/emendas. Cada carga substitui as linhas
    da sua origem; por isso não há chave única por código de emenda.
    """

    __tablename__ = "pol_emenda"

    id: Mapped[int] = mapped_column(primary_key=True)
    fonte_dados: Mapped[str] = mapped_column(String(10), default="api")
    linha: Mapped[int | None]
    codigo_emenda: Mapped[str] = mapped_column(String(40), index=True)
    codigo_autor: Mapped[str | None] = mapped_column(String(20))
    acao: Mapped[str | None] = mapped_column(Text)
    ano: Mapped[int] = mapped_column(Integer, index=True)
    tipo_emenda: Mapped[str | None] = mapped_column(String(120))
    # "transferência especial" (as chamadas emendas Pix), conforme `tipo_emenda`
    transferencia_especial: Mapped[bool] = mapped_column(Boolean, default=False)
    autor: Mapped[str | None] = mapped_column(String(200))
    nome_autor: Mapped[str | None] = mapped_column(String(200), index=True)
    numero_emenda: Mapped[str | None] = mapped_column(String(40))
    localidade_gasto: Mapped[str | None] = mapped_column(String(200))
    cod_ibge_destino: Mapped[int | None] = mapped_column(Integer, index=True)
    funcao: Mapped[str | None] = mapped_column(String(120))
    subfuncao: Mapped[str | None] = mapped_column(String(120))
    valor_empenhado: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_liquidado: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_resto_inscrito: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_resto_cancelado: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_resto_pago: Mapped[Decimal | None] = mapped_column(Numeric)
    politico_id: Mapped[int | None] = mapped_column(
        ForeignKey("pol_politico.id", ondelete="SET NULL"), index=True
    )
    url_fonte: Mapped[str] = mapped_column(Text)
    resposta_id: Mapped[int | None] = _resposta()
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PolPendencia(Base):
    """Cargo sem ocupante identificável na fonte (ex.: município sem prefeito eleito no
    arquivo do TSE porque a eleição foi anulada e a suplementar ainda não ocorreu)."""

    __tablename__ = "pol_pendencia"
    __table_args__ = (
        UniqueConstraint(
            "fonte",
            "eleicao_ano",
            "cargo",
            "uf",
            "cod_ibge",
            name="uq_pol_pendencia",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fonte: Mapped[str] = mapped_column(String(20))
    eleicao_ano: Mapped[int]
    cargo: Mapped[str] = mapped_column(String(30))
    uf: Mapped[str] = mapped_column(String(2))
    cod_ibge: Mapped[int | None] = mapped_column(Integer, index=True)
    motivo: Mapped[str] = mapped_column(Text)
    url_fonte: Mapped[str] = mapped_column(Text)
    resposta_id: Mapped[int | None] = _resposta()


class PolDespesaCota(Base):
    """Despesa da Cota para o Exercício da Atividade Parlamentar (CEAP), Câmara.

    Uma linha do arquivo anual `Ano-AAAA.csv.zip`. O arquivo não tem chave única por
    linha (há linhas idênticas, ex.: débitos de telefonia); cada carga substitui o ano
    inteiro, e `linha` é a posição no arquivo original (1 = primeira linha de dados).
    CPF de fornecedor pessoa física e o nome dele NÃO são guardados (LGPD).
    """

    __tablename__ = "pol_despesa_cota"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    politico_id: Mapped[int] = mapped_column(
        ForeignKey("pol_politico.id", ondelete="CASCADE"), index=True
    )
    ano: Mapped[int] = mapped_column(Integer, index=True)
    mes: Mapped[int]
    linha: Mapped[int]
    categoria: Mapped[str] = mapped_column(String(200))
    especificacao: Mapped[str | None] = mapped_column(String(200))
    fornecedor: Mapped[str | None] = mapped_column(String(300))  # nulo se pessoa física
    cnpj: Mapped[str | None] = mapped_column(String(14))  # só CNPJ (14 dígitos)
    pessoa_fisica: Mapped[bool] = mapped_column(Boolean, default=False)
    numero_documento: Mapped[str | None] = mapped_column(String(100))
    tipo_documento: Mapped[str | None] = mapped_column(String(4))
    data_emissao: Mapped[date | None] = mapped_column(Date)
    valor_documento: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_glosa: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_liquido: Mapped[Decimal | None] = mapped_column(Numeric)
    valor_restituicao: Mapped[Decimal | None] = mapped_column(Numeric)
    ide_documento: Mapped[str | None] = mapped_column(String(20))
    url_documento: Mapped[str | None] = mapped_column(Text)
    url_fonte: Mapped[str] = mapped_column(Text)
    resposta_id: Mapped[int | None] = _resposta()
