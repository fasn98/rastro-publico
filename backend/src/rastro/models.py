from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

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
    status: Mapped[str] = mapped_column(String(20))  # executando | sucesso | falha
    registros: Mapped[int | None]
    erro: Mapped[str | None] = mapped_column(Text)
    iniciada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finalizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
