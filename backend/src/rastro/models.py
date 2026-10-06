from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastro.db import Base


class Municipio(Base):
    """Município segundo a API de Localidades do IBGE."""

    __tablename__ = "municipio"

    cod_ibge: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    nome: Mapped[str] = mapped_column(String(120))
    uf: Mapped[str] = mapped_column(String(2), index=True)
    regiao: Mapped[str] = mapped_column(String(2))
    # Micro e mesorregiões são a divisão antiga do IBGE (substituída em 2017 pelas regiões
    # imediatas e intermediárias). Municípios criados depois disso vêm sem elas na API
    # (ex.: Boa Esperança do Norte/MT), por isso estes campos aceitam nulo.
    microrregiao: Mapped[str | None] = mapped_column(String(120))
    mesorregiao: Mapped[str | None] = mapped_column(String(120))
    regiao_imediata: Mapped[str | None] = mapped_column(String(120))
    regiao_intermediaria: Mapped[str | None] = mapped_column(String(120))
    # resposta bruta (resposta_bruta.id) de onde este registro foi extraído
    resposta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resposta_bruta.id"), index=True
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EnteSiconfi(Base):
    """Ente da Federação cadastrado no SICONFI (Tesouro Nacional)."""

    __tablename__ = "ente_siconfi"

    cod_ibge: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    nome: Mapped[str] = mapped_column(String(120))
    # U = União, E = Estado, D = Distrito Federal, M = Município
    esfera: Mapped[str] = mapped_column(String(1), index=True)
    uf: Mapped[str | None] = mapped_column(String(2), index=True)
    regiao: Mapped[str] = mapped_column(String(2))
    capital: Mapped[bool]
    populacao: Mapped[int | None]
    cnpj: Mapped[str | None] = mapped_column(String(14))
    exercicio: Mapped[int]
    # resposta bruta (resposta_bruta.id) de onde este registro foi extraído
    resposta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resposta_bruta.id"), index=True
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Coleta(Base):
    """Registro de cada execução de um coletor."""

    __tablename__ = "coleta"

    id: Mapped[int] = mapped_column(primary_key=True)
    fonte: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(20))  # executando | sucesso | parcial | falha
    registros: Mapped[int | None]
    erro: Mapped[str | None] = mapped_column(Text)
    iniciada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finalizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemonstrativoSiconfi(Base):
    """Um RREO ou RGF entregue por uma instituição de um ente em um período (cabeçalho)."""

    __tablename__ = "demonstrativo_siconfi"
    __table_args__ = (
        UniqueConstraint(
            "cod_ibge",
            "exercicio",
            "demonstrativo",
            "periodicidade",
            "periodo",
            "poder",
            "instituicao",
            name="uq_demonstrativo_siconfi",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cod_ibge: Mapped[int] = mapped_column(Integer, index=True)
    exercicio: Mapped[int]
    # RREO | RREO Simplificado | RGF | RGF Simplificado
    demonstrativo: Mapped[str] = mapped_column(String(30))
    # B = bimestral (RREO), Q = quadrimestral, S = semestral (RGF)
    periodicidade: Mapped[str] = mapped_column(String(1))
    periodo: Mapped[int]
    # Só no RGF: E = Executivo, L = Legislativo, J = Judiciário, M = Ministério Público,
    # D = Defensoria. Nulo no RREO, que é do ente como um todo.
    poder: Mapped[str | None] = mapped_column(String(1))
    # Um RGF por instituição: o mesmo poder pode ter várias (Câmara e TCM, TJ e TJM...)
    instituicao: Mapped[str | None] = mapped_column(String(200))
    # Data do último status no extrato de entregas; muda quando o ente retifica o relatório.
    data_status: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # linhas devolvidas pela API (todas estão no arquivo bruto)
    linhas: Mapped[int]
    # linhas gravadas em conta_demonstrativo (só as do mapeamento)
    linhas_gravadas: Mapped[int | None]
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    respostas: Mapped[list["DemonstrativoResposta"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    contas: Mapped[list["ContaDemonstrativo"]] = relationship(
        back_populates="demonstrativo", cascade="all, delete-orphan", passive_deletes=True
    )


class ContaDemonstrativo(Base):
    """Uma célula de um anexo do RREO/RGF: conta x coluna = valor."""

    __tablename__ = "conta_demonstrativo"
    # uma célula por demonstrativo: impede linhas em dobro mesmo com dois processos
    # gravando ao mesmo tempo (ex.: duas reconstruções concorrentes)
    __table_args__ = (
        UniqueConstraint(
            "demonstrativo_id", "anexo", "rotulo", "cod_conta", "conta", "coluna",
            name="uq_conta_demonstrativo",
        ),
    )  # fmt: skip

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    demonstrativo_id: Mapped[int] = mapped_column(
        ForeignKey("demonstrativo_siconfi.id", ondelete="CASCADE"), index=True
    )
    anexo: Mapped[str] = mapped_column(String(80))
    rotulo: Mapped[str] = mapped_column(Text)
    coluna: Mapped[str] = mapped_column(Text)
    cod_conta: Mapped[str] = mapped_column(Text)
    conta: Mapped[str] = mapped_column(Text)
    valor: Mapped[Decimal | None] = mapped_column(Numeric)
    # resposta bruta (resposta_bruta.id) de onde este registro foi extraído
    resposta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resposta_bruta.id"), index=True
    )

    demonstrativo: Mapped[DemonstrativoSiconfi] = relationship(back_populates="contas")


class EntregaSiconfi(Base):
    """Item do extrato de entregas do SICONFI (o que o ente declarou ter entregue)."""

    __tablename__ = "entrega_siconfi"

    id: Mapped[int] = mapped_column(primary_key=True)
    cod_ibge: Mapped[int] = mapped_column(Integer, index=True)
    exercicio: Mapped[int]
    entregavel: Mapped[str] = mapped_column(String(120))
    periodicidade: Mapped[str | None] = mapped_column(String(1))
    periodo: Mapped[int | None]
    instituicao: Mapped[str | None] = mapped_column(String(200))
    # HO = homologado, RE = retificado (como devolvido pela API)
    status_relatorio: Mapped[str | None] = mapped_column(String(4))
    # P = completo, S = simplificado (nos relatórios que têm versão simplificada)
    tipo_relatorio: Mapped[str | None] = mapped_column(String(4))
    forma_envio: Mapped[str | None] = mapped_column(String(20))
    data_status: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # resposta bruta (resposta_bruta.id) de onde este registro foi extraído
    resposta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resposta_bruta.id"), index=True
    )


class ExtratoColetado(Base):
    """Marca que o extrato de um ente/ano foi lido (mesmo que vazio).

    Distingue "o ente não entregou nada" de "ainda não coletamos este ano".
    """

    __tablename__ = "extrato_coletado"

    cod_ibge: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    exercicio: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    itens: Mapped[int]
    lido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoteColeta(Base):
    """Coleta longa e retomável (ex.: todos os municípios de uma UF em vários anos)."""

    __tablename__ = "lote_coleta"

    id: Mapped[int] = mapped_column(primary_key=True)
    # parâmetros normalizados; um lote não finalizado com a mesma chave é retomado
    chave: Mapped[str] = mapped_column(String(200), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    itens: Mapped[list["ItemLote"]] = relationship(back_populates="lote")


class ItemLote(Base):
    __tablename__ = "item_lote"

    lote_id: Mapped[int] = mapped_column(ForeignKey("lote_coleta.id"), primary_key=True)
    cod_ibge: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    exercicio: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente|sucesso|falha
    linhas: Mapped[int | None]
    erro: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lote: Mapped[LoteColeta] = relationship(back_populates="itens")


class NotaRanking(Base):
    """Nota de um município no Ranking Fiscal, com a versão da metodologia que a gerou."""

    __tablename__ = "nota_ranking"

    id: Mapped[int] = mapped_column(primary_key=True)
    versao: Mapped[str] = mapped_column(String(20), index=True)
    # sha256 (12 primeiros caracteres) do arquivo de metodologia usado
    hash_metodologia: Mapped[str] = mapped_column(String(12))
    calculado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exercicios: Mapped[str] = mapped_column(String(40))
    cod_ibge: Mapped[int] = mapped_column(Integer, index=True)
    uf: Mapped[str] = mapped_column(String(2), index=True)
    populacao: Mapped[int | None]
    faixa: Mapped[str | None] = mapped_column(String(40))
    nota: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    indicadores_faltantes: Mapped[int]
    posicao_geral: Mapped[int | None]
    posicao_faixa: Mapped[int | None]
    # nota, peso e valores/notas por ano de cada indicador
    componentes: Mapped[dict] = mapped_column(JSONB)


class PayloadBruto(Base):
    """Bytes de uma resposta, exatamente como recebidos, indexados pelo SHA-256 deles."""

    __tablename__ = "payload_bruto"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    tamanho: Mapped[int]  # bytes originais (antes da compressão)
    compressao: Mapped[str] = mapped_column(String(10))  # gzip
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RespostaBruta(Base):
    """Uma chamada HTTP a uma fonte: o que foi pedido, quando, e o que voltou."""

    __tablename__ = "resposta_bruta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    coleta_id: Mapped[int | None] = mapped_column(ForeignKey("coleta.id"), index=True)
    metodo: Mapped[str] = mapped_column(String(10))
    url: Mapped[str] = mapped_column(Text)  # completa, com parâmetros
    status_http: Mapped[int]
    content_type: Mapped[str | None] = mapped_column(String(120))
    recebido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duracao_ms: Mapped[int | None]
    sha256: Mapped[str] = mapped_column(ForeignKey("payload_bruto.sha256"), index=True)
    tamanho: Mapped[int]


class DemonstrativoResposta(Base):
    """Respostas brutas (páginas) que compõem um demonstrativo.

    Liga o relatório ao arquivo bruto mesmo quando nenhuma linha dele foi gravada em
    `conta_demonstrativo`; é o ponto de partida para reconstruir qualquer linha.
    """

    __tablename__ = "demonstrativo_resposta"

    demonstrativo_id: Mapped[int] = mapped_column(
        ForeignKey("demonstrativo_siconfi.id", ondelete="CASCADE"), primary_key=True
    )
    resposta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resposta_bruta.id"), primary_key=True, index=True
    )


# Tabelas do módulo de políticos (pol_*), registradas no mesmo metadata
from rastro.politicos import modelos as _politicos  # noqa: E402, F401
