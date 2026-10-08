"""Estruturas puras compartilhadas pelo validador e pelo solver.

Nada aqui conhece SQLAlchemy. O `loader` traduz o banco para ca'; o validador e o
solver so' enxergam estes tipos. E' o que permite testar os dois com cenarios
montados a mao e garantir que enxergam exatamente o mesmo estado.

Horarios viram minutos desde a meia-noite: comparar interjornada entre dias com
`datetime.time` exigiria aritmetica de data, e nenhum turno do CPS passa da
meia-noite (o mais tarde termina 23:00).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

from app.models import (
    ModalidadeAula,
    ModoDivisao,
    OrigemHabilitacao,
    Severidade,
    StatusDisponibilidade,
    TipoContrato,
    TipoEspaco,
)

DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def minutos(hora: time) -> int:
    return hora.hour * 60 + hora.minute


def hhmm(minuto: int) -> str:
    return f"{minuto // 60:02d}h{minuto % 60:02d}"


# --------------------------------------------------------------------- entidades


@dataclass(frozen=True, slots=True)
class SlotInfo:
    id: int
    modelo_turno_id: int
    dia: int
    ordem: int
    bloco_id: int
    inicio_min: int
    fim_min: int

    @property
    def rotulo(self) -> str:
        return f"{DIAS[self.dia]} {hhmm(self.inicio_min)}–{hhmm(self.fim_min)}"


@dataclass(frozen=True, slots=True)
class DisciplinaInfo:
    id: int
    nome: str
    sigla: str
    aulas_semanais: int
    tamanho_bloco: int
    modalidade: ModalidadeAula
    precisa_laboratorio: bool
    tipo_laboratorio: str | None
    divisao_turma: bool
    modo_divisao: ModoDivisao
    max_blocos_por_dia: int
    concentrar_no_dia: bool = False
    """Todas as aulas da semana no mesmo dia e seguidas (o "4" do 4 + 2)."""

    @property
    def remota(self) -> bool:
        return self.modalidade == ModalidadeAula.REMOTA

    @property
    def limite_blocos_por_dia(self) -> int:
        """Concentrar manda mais que o limite: todos os blocos vao no mesmo dia."""
        return 99 if self.concentrar_no_dia else self.max_blocos_por_dia


@dataclass(frozen=True, slots=True)
class TurmaInfo:
    id: int
    curso_id: int
    curso_sigla: str
    periodo: str
    modelo_turno_id: int
    qtd_alunos: int
    turno: str = ""
    """Nome do turno da turma ("Manhã", "Noturno"): so' para rotular a tela."""

    @property
    def rotulo(self) -> str:
        return f"{self.curso_sigla} {self.periodo}"


@dataclass(frozen=True, slots=True)
class OfertaInfo:
    id: int
    turma_id: int
    disciplina_id: int
    subturma: str | None
    professor_id: int | None


@dataclass(frozen=True, slots=True)
class EspacoInfo:
    id: int
    nome: str
    tipo: TipoEspaco
    tipo_laboratorio: str | None
    capacidade: int

    def atende(self, disciplina: DisciplinaInfo, alunos: int) -> bool:
        if disciplina.precisa_laboratorio:
            if self.tipo != TipoEspaco.LABORATORIO:
                return False
            exigido = (disciplina.tipo_laboratorio or "").strip().lower()
            if exigido and (self.tipo_laboratorio or "").strip().lower() != exigido:
                return False
        return self.capacidade >= alunos


@dataclass(frozen=True, slots=True)
class ProfessorInfo:
    id: int
    nome: str


@dataclass(frozen=True, slots=True)
class VinculoInfo:
    professor_id: int
    unidade_id: int
    tipo_contrato: TipoContrato
    pontuacao: float
    pont_assiduidade: float
    pont_titulacao: float
    tempo_exercicio_meses: int
    num_filhos: int
    carga_max_semanal: int | None

    def carga_max(self, padrao: int) -> int:
        return self.carga_max_semanal if self.carga_max_semanal is not None else padrao


@dataclass(frozen=True, slots=True)
class AlocacaoInfo:
    """Uma hora-aula posicionada nesta unidade."""

    id: int
    oferta_id: int
    professor_id: int
    slot_id: int
    espaco_id: int | None
    bloco_idx: int
    fixada: bool = False


@dataclass(frozen=True, slots=True)
class OcupacaoExterna:
    """Aula de um professor em **outra** unidade do mesmo escopo.

    Entra no estado ja' resolvida em dia/minutos porque o modelo de turno de la'
    nao e' carregado: so' interessa quando o professor esta' ocupado.
    """

    professor_id: int
    unidade_id: int
    unidade_nome: str
    dia: int
    inicio_min: int
    fim_min: int
    rotulo: str


# ------------------------------------------------------------------ estado inteiro


@dataclass(slots=True)
class GradeState:
    unidade_id: int
    unidade_nome: str
    slots: dict[int, SlotInfo] = field(default_factory=dict)
    turmas: dict[int, TurmaInfo] = field(default_factory=dict)
    disciplinas: dict[int, DisciplinaInfo] = field(default_factory=dict)
    ofertas: dict[int, OfertaInfo] = field(default_factory=dict)
    espacos: dict[int, EspacoInfo] = field(default_factory=dict)
    professores: dict[int, ProfessorInfo] = field(default_factory=dict)
    vinculos: dict[int, VinculoInfo] = field(default_factory=dict)
    """Por `professor_id`, apenas os vinculos desta unidade."""
    disponibilidade: dict[tuple[int, int], StatusDisponibilidade] = field(default_factory=dict)
    """Por `(professor_id, slot_id)`. Ausencia significa DISPONIVEL."""
    habilitacoes: dict[tuple[int, int], OrigemHabilitacao] = field(default_factory=dict)
    """Por `(professor_id, disciplina_id)`. Ausencia significa nao habilitado."""
    alocacoes: list[AlocacaoInfo] = field(default_factory=list)
    ocupacoes_externas: list[OcupacaoExterna] = field(default_factory=list)

    # ---------------------------------------------------------------- consultas

    def disciplina_da(self, oferta: OfertaInfo) -> DisciplinaInfo:
        return self.disciplinas[oferta.disciplina_id]

    def turma_da(self, oferta: OfertaInfo) -> TurmaInfo:
        return self.turmas[oferta.turma_id]

    def status_disponibilidade(self, professor_id: int, slot_id: int) -> StatusDisponibilidade:
        return self.disponibilidade.get((professor_id, slot_id), StatusDisponibilidade.DISPONIVEL)

    def nome_professor(self, professor_id: int) -> str:
        prof = self.professores.get(professor_id)
        return prof.nome if prof else f"professor {professor_id}"

    def rotulo_oferta(self, oferta: OfertaInfo) -> str:
        disciplina = self.disciplina_da(oferta)
        turma = self.turma_da(oferta)
        sufixo = f", turma {oferta.subturma}" if oferta.subturma else ""
        return f"{disciplina.sigla} ({turma.rotulo}{sufixo})"

    def slots_do_modelo(self, modelo_turno_id: int) -> list[SlotInfo]:
        return sorted(
            (s for s in self.slots.values() if s.modelo_turno_id == modelo_turno_id),
            key=lambda s: (s.dia, s.ordem),
        )

    def habilitacao(self, professor_id: int, disciplina_id: int) -> OrigemHabilitacao | None:
        return self.habilitacoes.get((professor_id, disciplina_id))

    def fluxos_da_oferta(self, oferta: OfertaInfo) -> tuple[tuple[int, str], ...]:
        """Fluxos de alunos que a oferta ocupa.

        Uma oferta de turma inteira ocupa os dois fluxos (A e B); uma subturma
        ocupa so' o seu. E' o que faz a divisao PARALELA poder coexistir no mesmo
        horario sem deixar uma aula de turma inteira coincidir com uma subturma.
        """
        if oferta.subturma is None:
            return ((oferta.turma_id, "A"), (oferta.turma_id, "B"))
        return ((oferta.turma_id, oferta.subturma),)


# ------------------------------------------------------------------- violacoes


@dataclass(frozen=True, slots=True)
class Violacao:
    tipo: str
    severidade: Severidade
    mensagem: str
    entidades: dict = field(default_factory=dict)

    @property
    def bloqueante(self) -> bool:
        return self.severidade == Severidade.BLOQUEANTE


def bloqueantes(violacoes: list[Violacao]) -> list[Violacao]:
    return [v for v in violacoes if v.bloqueante]
