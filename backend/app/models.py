"""Modelo de dados completo (secao 3 da especificacao).

Convencoes:
- `dia_semana`: 0 = segunda ... 5 = sabado, 6 = domingo.
- Enums sao gravados como VARCHAR + CHECK (`native_enum=False`) para funcionar
  igual em SQLite e PostgreSQL sem migration de tipo.
- Campos JSON usam `sqlalchemy.JSON` (ver DECISOES.md D7).
"""

from __future__ import annotations

import enum
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(py_enum: type[enum.Enum], name: str) -> Enum:
    return Enum(py_enum, name=name, native_enum=False, validate_strings=True)


# --------------------------------------------------------------------------- enums


class TipoUnidade(enum.StrEnum):
    FATEC = "FATEC"
    ETEC = "ETEC"


class Modalidade(enum.StrEnum):
    CST = "CST"
    TECNICO_MODULAR = "TECNICO_MODULAR"
    ETIM = "ETIM"
    MTEC = "MTEC"


class ModalidadeAula(enum.StrEnum):
    PRESENCIAL = "PRESENCIAL"
    REMOTA = "REMOTA"


class ModoDivisao(enum.StrEnum):
    PARALELA = "PARALELA"
    SEQUENCIAL = "SEQUENCIAL"
    INDIFERENTE = "INDIFERENTE"


class TipoEspaco(enum.StrEnum):
    SALA = "SALA"
    LABORATORIO = "LABORATORIO"


class TipoContrato(enum.StrEnum):
    INDETERMINADO = "INDETERMINADO"
    DETERMINADO = "DETERMINADO"


class OrigemHabilitacao(enum.StrEnum):
    CONCURSO = "CONCURSO"
    ANTERIOR = "ANTERIOR"
    HABILITADO = "HABILITADO"


class StatusDisponibilidade(enum.StrEnum):
    DISPONIVEL = "DISPONIVEL"
    PREFERENCIAL = "PREFERENCIAL"
    INDISPONIVEL = "INDISPONIVEL"


class StatusGrade(enum.StrEnum):
    RASCUNHO = "RASCUNHO"
    AGUARDANDO_CIENCIA = "AGUARDANDO_CIENCIA"
    PUBLICADA = "PUBLICADA"


class Severidade(enum.StrEnum):
    INFO = "INFO"
    ALERTA = "ALERTA"
    BLOQUEANTE = "BLOQUEANTE"


class OrigemAlteracao(enum.StrEnum):
    MANUAL = "MANUAL"
    CHAT = "CHAT"
    SOLVER = "SOLVER"


# ------------------------------------------------------------------ escopo/unidade


class Escopo(Base):
    __tablename__ = "escopo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)

    unidades: Mapped[list[Unidade]] = relationship(
        back_populates="escopo", cascade="all, delete-orphan"
    )
    professores: Mapped[list[Professor]] = relationship(
        back_populates="escopo", cascade="all, delete-orphan"
    )


class Unidade(Base):
    __tablename__ = "unidade"
    __table_args__ = (UniqueConstraint("escopo_id", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    escopo_id: Mapped[int] = mapped_column(ForeignKey("escopo.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[TipoUnidade] = mapped_column(_enum(TipoUnidade, "tipo_unidade"))
    cidade: Mapped[str | None] = mapped_column(String(120))
    carga_max_semanal_padrao: Mapped[int] = mapped_column(Integer, default=29)
    config_regras: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    escopo: Mapped[Escopo] = relationship(back_populates="unidades")
    modelos_turno: Mapped[list[ModeloTurno]] = relationship(
        back_populates="unidade", cascade="all, delete-orphan"
    )
    cursos: Mapped[list[Curso]] = relationship(
        back_populates="unidade", cascade="all, delete-orphan"
    )
    espacos: Mapped[list[Espaco]] = relationship(
        back_populates="unidade", cascade="all, delete-orphan"
    )
    vinculos: Mapped[list[VinculoUnidade]] = relationship(
        back_populates="unidade", cascade="all, delete-orphan"
    )
    grades: Mapped[list[Grade]] = relationship(
        back_populates="unidade", cascade="all, delete-orphan"
    )


# --------------------------------------------------------------------- turno/slots


class ModeloTurno(Base):
    __tablename__ = "modelo_turno"
    __table_args__ = (UniqueConstraint("unidade_id", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(120))
    dias_semana: Mapped[list[int]] = mapped_column(JSON, default=list)
    preset_origem: Mapped[str | None] = mapped_column(String(80))

    unidade: Mapped[Unidade] = relationship(back_populates="modelos_turno")
    slots: Mapped[list[Slot]] = relationship(
        back_populates="modelo_turno",
        cascade="all, delete-orphan",
        order_by="(Slot.dia_semana, Slot.ordem)",
    )


class Slot(Base):
    """Uma hora-aula de um dia. `bloco_id` agrupa slots contiguos sem intervalo."""

    __tablename__ = "slot"
    __table_args__ = (UniqueConstraint("modelo_turno_id", "dia_semana", "ordem"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    modelo_turno_id: Mapped[int] = mapped_column(ForeignKey("modelo_turno.id", ondelete="CASCADE"))
    dia_semana: Mapped[int] = mapped_column(Integer)
    ordem: Mapped[int] = mapped_column(Integer)
    inicio: Mapped[time] = mapped_column(Time)
    fim: Mapped[time] = mapped_column(Time)
    bloco_id: Mapped[int] = mapped_column(Integer)

    modelo_turno: Mapped[ModeloTurno] = relationship(back_populates="slots")


# ------------------------------------------------------------ curso/turma/disciplina


class Curso(Base):
    __tablename__ = "curso"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(160))
    sigla: Mapped[str] = mapped_column(String(20))
    modalidade: Mapped[Modalidade] = mapped_column(_enum(Modalidade, "modalidade_curso"))

    unidade: Mapped[Unidade] = relationship(back_populates="cursos")
    turmas: Mapped[list[Turma]] = relationship(back_populates="curso", cascade="all, delete-orphan")
    disciplinas: Mapped[list[Disciplina]] = relationship(
        back_populates="curso", cascade="all, delete-orphan"
    )


class Turma(Base):
    __tablename__ = "turma"

    id: Mapped[int] = mapped_column(primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("curso.id", ondelete="CASCADE"))
    periodo: Mapped[str] = mapped_column(String(40))
    turno: Mapped[str] = mapped_column(String(40))
    modelo_turno_id: Mapped[int] = mapped_column(ForeignKey("modelo_turno.id"))
    qtd_alunos: Mapped[int] = mapped_column(Integer, default=40)

    curso: Mapped[Curso] = relationship(back_populates="turmas")
    modelo_turno: Mapped[ModeloTurno] = relationship()
    ofertas: Mapped[list[Oferta]] = relationship(
        back_populates="turma", cascade="all, delete-orphan"
    )


class Disciplina(Base):
    """Disciplina (Fatec) ou componente curricular (Etec)."""

    __tablename__ = "disciplina"

    id: Mapped[int] = mapped_column(primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("curso.id", ondelete="CASCADE"))
    periodo: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str] = mapped_column(String(160))
    sigla: Mapped[str] = mapped_column(String(20))
    aulas_semanais: Mapped[int] = mapped_column(Integer)
    tamanho_bloco: Mapped[int] = mapped_column(Integer, default=2)
    modalidade: Mapped[ModalidadeAula] = mapped_column(
        _enum(ModalidadeAula, "modalidade_aula"), default=ModalidadeAula.PRESENCIAL
    )
    precisa_laboratorio: Mapped[bool] = mapped_column(Boolean, default=False)
    tipo_laboratorio: Mapped[str | None] = mapped_column(String(60))
    divisao_turma: Mapped[bool] = mapped_column(Boolean, default=False)
    modo_divisao: Mapped[ModoDivisao] = mapped_column(
        _enum(ModoDivisao, "modo_divisao"), default=ModoDivisao.INDIFERENTE
    )
    max_blocos_por_dia: Mapped[int] = mapped_column(Integer, default=1)
    concentrar_no_dia: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """Todas as aulas da semana no mesmo dia e seguidas (o "4" do 4 + 2)."""

    curso: Mapped[Curso] = relationship(back_populates="disciplinas")
    ofertas: Mapped[list[Oferta]] = relationship(
        back_populates="disciplina", cascade="all, delete-orphan"
    )


class Espaco(Base):
    __tablename__ = "espaco"
    __table_args__ = (UniqueConstraint("unidade_id", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[TipoEspaco] = mapped_column(_enum(TipoEspaco, "tipo_espaco"))
    tipo_laboratorio: Mapped[str | None] = mapped_column(String(60))
    capacidade: Mapped[int] = mapped_column(Integer, default=40)

    unidade: Mapped[Unidade] = relationship(back_populates="espacos")


class Oferta(Base):
    """Instancia concreta de uma disciplina para uma turma.

    Disciplina com divisao de turma gera duas ofertas (subturma "A" e "B").
    """

    __tablename__ = "oferta"
    __table_args__ = (UniqueConstraint("turma_id", "disciplina_id", "subturma"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turma.id", ondelete="CASCADE"))
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id", ondelete="CASCADE"))
    subturma: Mapped[str | None] = mapped_column(String(2))

    turma: Mapped[Turma] = relationship(back_populates="ofertas")
    disciplina: Mapped[Disciplina] = relationship(back_populates="ofertas")
    atribuicao: Mapped[Atribuicao | None] = relationship(
        back_populates="oferta", cascade="all, delete-orphan", uselist=False
    )


# ------------------------------------------------------------------------ professor


class Professor(Base):
    __tablename__ = "professor"
    __table_args__ = (UniqueConstraint("escopo_id", "identificador"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    escopo_id: Mapped[int] = mapped_column(ForeignKey("escopo.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(160))
    identificador: Mapped[str] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(160))

    escopo: Mapped[Escopo] = relationship(back_populates="professores")
    vinculos: Mapped[list[VinculoUnidade]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )
    habilitacoes: Mapped[list[Habilitacao]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )
    disponibilidades: Mapped[list[Disponibilidade]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )


class VinculoUnidade(Base):
    __tablename__ = "vinculo_unidade"
    __table_args__ = (UniqueConstraint("professor_id", "unidade_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(ForeignKey("professor.id", ondelete="CASCADE"))
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"))
    tipo_contrato: Mapped[TipoContrato] = mapped_column(
        _enum(TipoContrato, "tipo_contrato"), default=TipoContrato.INDETERMINADO
    )
    pontuacao: Mapped[float] = mapped_column(Float, default=0.0)
    pont_assiduidade: Mapped[float] = mapped_column(Float, default=0.0)
    pont_titulacao: Mapped[float] = mapped_column(Float, default=0.0)
    tempo_exercicio_meses: Mapped[int] = mapped_column(Integer, default=0)
    num_filhos: Mapped[int] = mapped_column(Integer, default=0)
    carga_max_semanal: Mapped[int | None] = mapped_column(Integer)

    professor: Mapped[Professor] = relationship(back_populates="vinculos")
    unidade: Mapped[Unidade] = relationship(back_populates="vinculos")


class Habilitacao(Base):
    __tablename__ = "habilitacao"
    __table_args__ = (UniqueConstraint("professor_id", "disciplina_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(ForeignKey("professor.id", ondelete="CASCADE"))
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id", ondelete="CASCADE"))
    origem: Mapped[OrigemHabilitacao] = mapped_column(
        _enum(OrigemHabilitacao, "origem_habilitacao"), default=OrigemHabilitacao.HABILITADO
    )

    professor: Mapped[Professor] = relationship(back_populates="habilitacoes")
    disciplina: Mapped[Disciplina] = relationship()


class Atribuicao(Base):
    """Quem da qual aula. Uma oferta tem no maximo um professor."""

    __tablename__ = "atribuicao"
    __table_args__ = (UniqueConstraint("oferta_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(ForeignKey("professor.id", ondelete="CASCADE"))
    oferta_id: Mapped[int] = mapped_column(ForeignKey("oferta.id", ondelete="CASCADE"))

    professor: Mapped[Professor] = relationship()
    oferta: Mapped[Oferta] = relationship(back_populates="atribuicao")


class Disponibilidade(Base):
    __tablename__ = "disponibilidade"
    __table_args__ = (UniqueConstraint("professor_id", "slot_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(ForeignKey("professor.id", ondelete="CASCADE"))
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("slot.id", ondelete="CASCADE"))
    status: Mapped[StatusDisponibilidade] = mapped_column(
        _enum(StatusDisponibilidade, "status_disponibilidade")
    )

    professor: Mapped[Professor] = relationship(back_populates="disponibilidades")
    slot: Mapped[Slot] = relationship()


# ---------------------------------------------------------------------------- grade


class Grade(Base):
    __tablename__ = "grade"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(120))
    status: Mapped[StatusGrade] = mapped_column(
        _enum(StatusGrade, "status_grade"), default=StatusGrade.RASCUNHO
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    parametros_solver: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    unidade: Mapped[Unidade] = relationship(back_populates="grades")
    alocacoes: Mapped[list[Alocacao]] = relationship(
        back_populates="grade", cascade="all, delete-orphan"
    )
    avisos: Mapped[list[Aviso]] = relationship(back_populates="grade", cascade="all, delete-orphan")
    historico: Mapped[list[HistoricoAlteracao]] = relationship(
        back_populates="grade", cascade="all, delete-orphan", order_by="HistoricoAlteracao.id"
    )


class Alocacao(Base):
    """Uma hora-aula posicionada. Um bloco geminado vira N linhas com o mesmo
    `bloco_idx` (ver DECISOES.md D4)."""

    __tablename__ = "alocacao"
    __table_args__ = (
        UniqueConstraint("grade_id", "oferta_id", "slot_id"),
        CheckConstraint("bloco_idx >= 0", name="ck_alocacao_bloco_idx"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grade_id: Mapped[int] = mapped_column(ForeignKey("grade.id", ondelete="CASCADE"))
    oferta_id: Mapped[int] = mapped_column(ForeignKey("oferta.id", ondelete="CASCADE"))
    professor_id: Mapped[int] = mapped_column(ForeignKey("professor.id", ondelete="CASCADE"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("slot.id", ondelete="CASCADE"))
    espaco_id: Mapped[int | None] = mapped_column(ForeignKey("espaco.id", ondelete="SET NULL"))
    bloco_idx: Mapped[int] = mapped_column(Integer, default=0)
    fixada: Mapped[bool] = mapped_column(Boolean, default=False)

    grade: Mapped[Grade] = relationship(back_populates="alocacoes")
    oferta: Mapped[Oferta] = relationship()
    professor: Mapped[Professor] = relationship()
    slot: Mapped[Slot] = relationship()
    espaco: Mapped[Espaco | None] = relationship()


class Aviso(Base):
    __tablename__ = "aviso"

    id: Mapped[int] = mapped_column(primary_key=True)
    grade_id: Mapped[int] = mapped_column(ForeignKey("grade.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(60))
    severidade: Mapped[Severidade] = mapped_column(_enum(Severidade, "severidade"))
    mensagem: Mapped[str] = mapped_column(Text)
    entidades: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ciente: Mapped[bool] = mapped_column(Boolean, default=False)
    ciente_por: Mapped[str | None] = mapped_column(String(160))
    ciente_em: Mapped[datetime | None] = mapped_column(DateTime)

    grade: Mapped[Grade] = relationship(back_populates="avisos")


class HistoricoAlteracao(Base):
    __tablename__ = "historico_alteracao"

    id: Mapped[int] = mapped_column(primary_key=True)
    grade_id: Mapped[int] = mapped_column(ForeignKey("grade.id", ondelete="CASCADE"))
    origem: Mapped[OrigemAlteracao] = mapped_column(_enum(OrigemAlteracao, "origem_alteracao"))
    diff: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    autor: Mapped[str | None] = mapped_column(String(160))
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    desfeito: Mapped[bool] = mapped_column(Boolean, default=False)

    grade: Mapped[Grade] = relationship(back_populates="historico")
