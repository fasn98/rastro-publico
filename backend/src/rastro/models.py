from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    """Um RREO ou RGF entregue por um ente em um período (cabeçalho)."""

    __tablename__ = "demonstrativo_siconfi"
    __table_args__ = (
        UniqueConstraint(
            "cod_ibge",
            "exercicio",
            "demonstrativo",
            "periodicidade",
            "periodo",
            "poder",
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
    instituicao: Mapped[str | None] = mapped_column(String(200))
    # Data do último status no extrato de entregas; muda quando o ente retifica o relatório.
    data_status: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linhas: Mapped[int]
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    contas: Mapped[list["ContaDemonstrativo"]] = relationship(
        back_populates="demonstrativo", cascade="all, delete-orphan", passive_deletes=True
    )


class ContaDemonstrativo(Base):
    """Uma célula de um anexo do RREO/RGF: conta x coluna = valor."""

    __tablename__ = "conta_demonstrativo"

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

    demonstrativo: Mapped[DemonstrativoSiconfi] = relationship(back_populates="contas")
