"""Schemas Pydantic v2 de entrada e saida.

Padrao por entidade:
- `XEntrada`  -> campos gravaveis (POST)
- `X`         -> `XEntrada` + `id` (GET)
- `XParcial`  -> tudo opcional, gerado por `parcial()` (PATCH)
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

from app.models import (
    Modalidade,
    ModalidadeAula,
    ModoDivisao,
    OrigemAlteracao,
    OrigemHabilitacao,
    Severidade,
    StatusDisponibilidade,
    StatusGrade,
    TipoContrato,
    TipoEspaco,
    TipoUnidade,
)

ModoObjetivo = Literal["ponderado", "lexicografico"]
TipoVisao = Literal["turma", "professor", "espaco"]


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def parcial[T: BaseModel](base: type[T]) -> type[BaseModel]:
    """Versao PATCH de um schema: todos os campos opcionais, default `None`.

    Evita reescrever a mao uma classe espelho por entidade.
    """
    campos: dict[str, Any] = {
        nome: (campo.annotation | None, None) for nome, campo in base.model_fields.items()
    }
    return create_model(f"{base.__name__}Parcial", __base__=Base, **campos)


# ------------------------------------------------------------------ escopo/unidade


class EscopoEntrada(Base):
    nome: str = Field(min_length=1, max_length=120)


class Escopo(EscopoEntrada):
    id: int


class UnidadeEntrada(Base):
    escopo_id: int
    nome: str = Field(min_length=1, max_length=120)
    tipo: TipoUnidade
    cidade: str | None = None
    carga_max_semanal_padrao: int = Field(default=29, ge=1, le=60)
    config_regras: dict[str, Any] = Field(default_factory=dict)


class Unidade(UnidadeEntrada):
    id: int


# --------------------------------------------------------------------- turno/slots


class SlotEntrada(Base):
    dia_semana: int = Field(ge=0, le=6)
    ordem: int = Field(ge=1)
    inicio: time
    fim: time
    bloco_id: int = Field(ge=1)

    @field_validator("fim")
    @classmethod
    def _fim_depois_do_inicio(cls, fim: time, info) -> time:
        inicio = info.data.get("inicio")
        if inicio is not None and fim <= inicio:
            raise ValueError("o fim da aula precisa ser depois do inicio")
        return fim


class Slot(SlotEntrada):
    id: int
    modelo_turno_id: int


class ModeloTurnoEntrada(Base):
    unidade_id: int
    nome: str = Field(min_length=1, max_length=120)
    preset_origem: str | None = None
    slots: list[SlotEntrada] = Field(default_factory=list)


class ModeloTurno(Base):
    id: int
    unidade_id: int
    nome: str
    dias_semana: list[int]
    preset_origem: str | None
    slots: list[Slot]


class PresetTurnoResumo(Base):
    chave: str
    nome: str
    dias_semana: list[int]
    aulas_por_dia: dict[int, int]


# ------------------------------------------------------------ curso/turma/oferta


class CursoEntrada(Base):
    unidade_id: int
    nome: str = Field(min_length=1, max_length=160)
    sigla: str = Field(min_length=1, max_length=20)
    modalidade: Modalidade


class BlocosDoCurso(Base):
    """Tamanho do bloco, blocos por dia e concentracao aplicados a todas as
    disciplinas do curso de uma vez. Todos opcionais, mas ao menos um precisa vir."""

    tamanho_bloco: int | None = Field(default=None, ge=1, le=8)
    max_blocos_por_dia: int | None = Field(default=None, ge=1, le=8)
    concentrar_no_dia: bool | None = None

    @model_validator(mode="after")
    def _ao_menos_um(self):
        if not self.model_fields_set or all(
            getattr(self, campo) is None for campo in self.model_fields_set
        ):
            raise ValueError("informe tamanho_bloco, max_blocos_por_dia ou concentrar_no_dia")
        return self


class Curso(CursoEntrada):
    id: int


class TurmaEntrada(Base):
    curso_id: int
    periodo: str = Field(min_length=1, max_length=40)
    turno: str = Field(min_length=1, max_length=40)
    modelo_turno_id: int
    qtd_alunos: int = Field(default=40, ge=1, le=300)


class Turma(TurmaEntrada):
    id: int


class DisciplinaEntrada(Base):
    curso_id: int
    periodo: str = Field(min_length=1, max_length=40)
    nome: str = Field(min_length=1, max_length=160)
    sigla: str = Field(min_length=1, max_length=20)
    aulas_semanais: int = Field(ge=1, le=40)
    tamanho_bloco: int = Field(default=2, ge=1, le=8)
    modalidade: ModalidadeAula = ModalidadeAula.PRESENCIAL
    precisa_laboratorio: bool = False
    tipo_laboratorio: str | None = None
    divisao_turma: bool = False
    modo_divisao: ModoDivisao = ModoDivisao.INDIFERENTE
    max_blocos_por_dia: int = Field(default=1, ge=1, le=8)
    concentrar_no_dia: bool = False
    """Todas as aulas da semana no mesmo dia e seguidas."""


class Disciplina(DisciplinaEntrada):
    id: int


class OfertaEntrada(Base):
    turma_id: int
    disciplina_id: int
    subturma: str | None = None


class Oferta(OfertaEntrada):
    id: int


class OfertaDetalhe(Oferta):
    """Oferta com o que a tela de atribuicao precisa mostrar sem N+1."""

    disciplina_nome: str
    disciplina_sigla: str
    aulas_semanais: int
    turma_periodo: str
    curso_sigla: str
    professor_id: int | None = None
    professor_nome: str | None = None


class EspacoEntrada(Base):
    unidade_id: int
    nome: str = Field(min_length=1, max_length=80)
    tipo: TipoEspaco
    tipo_laboratorio: str | None = None
    capacidade: int = Field(default=40, ge=1, le=300)


class Espaco(EspacoEntrada):
    id: int


# ------------------------------------------------------------------------ professor


class ProfessorEntrada(Base):
    escopo_id: int
    nome: str = Field(min_length=1, max_length=160)
    identificador: str = Field(min_length=1, max_length=40)
    email: str | None = None


class Professor(ProfessorEntrada):
    id: int


class VinculoEntrada(Base):
    professor_id: int
    unidade_id: int
    tipo_contrato: TipoContrato = TipoContrato.INDETERMINADO
    pontuacao: float = Field(default=0.0, ge=0)
    pont_assiduidade: float = Field(default=0.0, ge=0)
    pont_titulacao: float = Field(default=0.0, ge=0)
    tempo_exercicio_meses: int = Field(default=0, ge=0)
    num_filhos: int = Field(default=0, ge=0)
    carga_max_semanal: int | None = Field(default=None, ge=1, le=60)


class Vinculo(VinculoEntrada):
    id: int


class HabilitacaoEntrada(Base):
    professor_id: int
    disciplina_id: int
    origem: OrigemHabilitacao = OrigemHabilitacao.HABILITADO


class Habilitacao(HabilitacaoEntrada):
    id: int


class AtribuicaoEntrada(Base):
    professor_id: int
    oferta_id: int


class Atribuicao(AtribuicaoEntrada):
    id: int


class DisponibilidadeEntrada(Base):
    professor_id: int
    unidade_id: int
    slot_id: int
    status: StatusDisponibilidade


class Disponibilidade(DisponibilidadeEntrada):
    id: int


class DisponibilidadeLote(Base):
    """Marcacao em massa da grade clicavel (uma noite inteira, copiar de outro dia)."""

    professor_id: int
    unidade_id: int
    slot_ids: list[int] = Field(min_length=1)
    status: StatusDisponibilidade


# ---------------------------------------------------------------------------- grade


class GradeEntrada(Base):
    unidade_id: int
    nome: str = Field(min_length=1, max_length=120)
    parametros_solver: dict[str, Any] = Field(default_factory=dict)


class Grade(Base):
    id: int
    unidade_id: int
    nome: str
    status: StatusGrade
    criada_em: datetime
    parametros_solver: dict[str, Any]
    score: dict[str, Any]


class Alocacao(Base):
    id: int
    grade_id: int
    oferta_id: int
    professor_id: int
    slot_id: int
    espaco_id: int | None
    bloco_idx: int
    fixada: bool


class Violacao(Base):
    """Saida do validador unico e da pre-validacao (app/scheduling/validator.py)."""

    tipo: str
    severidade: Severidade
    mensagem: str
    entidades: dict[str, Any] = Field(default_factory=dict)


class Classificado(Base):
    """Uma posicao na lista de classificacao docente da unidade."""

    posicao: int
    professor_id: int
    professor_nome: str
    tipo_contrato: TipoContrato
    pontuacao: float
    pont_assiduidade: float
    pont_titulacao: float
    tempo_exercicio_meses: int
    num_filhos: int
    carga_max: int
    aulas_atribuidas: int


class ResultadoAtribuicao(Base):
    atribuidas: int
    """Quantas ofertas esta sugestao preencheu."""
    preservadas: int
    """Atribuicoes manuais que ficaram como estavam."""
    sem_professor: list[int]
    avisos: list[Violacao]
    classificacao: list[Classificado]


class ParametrosSolver(Base):
    nome: str | None = None
    tempo_limite_s: float = Field(default=60.0, ge=1, le=900)
    workers: int = Field(default=0, ge=0, le=64)
    """0 usa todos os nucleos da maquina."""
    semente: int = Field(default=42, ge=0)
    manter_fixadas: bool = True
    modo_objetivo: ModoObjetivo | None = None
    """Em branco usa o que estiver em config_regras."""
    partir_de: int | None = None
    """Id da grade anterior: entra como hint e como termo de estabilidade."""
    resolver_avisos: bool = False
    """Janelas e interjornada viram regra rígida em vez de custo."""


class GradeGerada(Base):
    grade_id: int
    job_id: str


class AlocacaoParcial(Base):
    oferta_id: int
    professor_id: int
    slot_id: int
    espaco_id: int | None
    bloco_idx: int


class Progresso(Base):
    job_id: str
    grade_id: int
    status: str
    terminado: bool
    solucoes: int
    objetivo: int | None
    limite_inferior: int | None
    tempo_s: float
    mensagem: str | None
    diagnostico: dict[str, Any] | None
    metricas: dict[str, Any]
    alocacoes: list[AlocacaoParcial]
    """Melhor solucao ate' agora, para a tela desenhar ao vivo."""


class CelulaGrade(Base):
    """Uma hora-aula posicionada, com tudo que a tela precisa para desenhar
    sem disparar uma consulta por celula."""

    alocacao_id: int
    oferta_id: int
    disciplina_id: int
    disciplina_sigla: str
    disciplina_nome: str
    turma_id: int
    turma_rotulo: str
    subturma: str | None
    professor_id: int
    professor_nome: str
    espaco_id: int | None
    espaco_nome: str | None
    slot_id: int
    modelo_turno_id: int
    dia: int
    ordem: int
    inicio: time
    fim: time
    bloco_id: int
    bloco_idx: int
    remota: bool
    precisa_laboratorio: bool
    fixada: bool


class SlotRef(Base):
    """Todo horario da semana, ocupado ou nao.

    A tela precisa disto para saber em qual `slot_id` o usuario soltou a aula:
    uma celula vazia nao tem `CelulaGrade` para consultar.
    """

    id: int
    modelo_turno_id: int
    dia: int
    ordem: int
    inicio: time
    fim: time
    bloco_id: int


class ColunaVisao(Base):
    id: int
    titulo: str
    subtitulo: str | None = None
    tipo: str | None = None
    modelo_turno_id: int | None = None
    """Turno da coluna, quando ela e' uma turma. A tela precisa disto para nao
    chamar de "janela" um horario que o turno daquela turma nem tem."""


class LinhaHorario(Base):
    dia: int
    inicio: time
    fim: time
    ordens: list[int]
    """Que "numero de aula" esta faixa ocupa em cada modelo de turno."""


class VisaoGrade(Base):
    grade_id: int
    tipo: TipoVisao
    colunas: list[ColunaVisao]
    horarios: list[LinhaHorario]
    slots: list[SlotRef]
    celulas: list[CelulaGrade]


class BlocoRef(Base):
    """Um bloco de aulas geminadas: a unidade que o usuario arrasta."""

    oferta_id: int
    bloco_idx: int = 0


class MovimentoEntrada(BlocoRef):
    slot_inicial: int
    espaco_id: int | None = None
    forcar: bool = False
    """Aplica mesmo criando violacao bloqueante; o aviso fica e impede publicar."""


class TrocaEntrada(Base):
    a: BlocoRef
    b: BlocoRef
    forcar: bool = False


class FixarEntrada(BlocoRef):
    fixada: bool = True


class AlteracaoResumo(Base):
    alocacao_id: int
    antes: dict[str, Any]
    depois: dict[str, Any]


class ResultadoMovimento(Base):
    permitido: bool
    severidade: Severidade | None
    descricao: str
    alteracoes: list[AlteracaoResumo]
    violacoes: list[Violacao]
    aplicado: bool = False


class DestinoPossivel(Base):
    slot_id: int
    severidade: Severidade | None
    """`None` = movimento limpo (verde)."""
    motivos: list[str]


class RegistroHistorico(Base):
    id: int
    origem: OrigemAlteracao
    autor: str | None
    timestamp: datetime
    descricao: str
    desfeito: bool


class EstadoChat(Base):
    ativo: bool
    mensagem: str | None = None


class MensagemHistorico(Base):
    papel: Literal["user", "assistant"]
    texto: str


class MensagemChat(Base):
    texto: str = Field(min_length=1, max_length=4000)
    historico: list[MensagemHistorico] = Field(default_factory=list, max_length=40)


class MudancaProposta(Base):
    rotulo: str
    antes: str
    depois: str


class Proposta(Base):
    """Alteracao sugerida pelo assistente, aguardando o clique do usuario."""

    id: str
    grade_id: int
    tipo: str
    descricao: str
    permitido: bool
    aplicada: bool
    descartada: bool
    mudancas: list[MudancaProposta]
    violacoes: list[Violacao]


class Aviso(Base):
    id: int
    grade_id: int
    tipo: str
    severidade: Severidade
    mensagem: str
    entidades: dict[str, Any]
    ciente: bool
    ciente_por: str | None
    ciente_em: datetime | None


# -------------------------------------------------------------------- config_regras
# Validado na escrita da unidade para o solver nunca ler uma chave ausente.


class LimiteDiario(Base):
    ativo: bool = False
    max_consecutivas: int = Field(default=4, ge=1, le=12)
    max_intercaladas: int = Field(default=6, ge=1, le=12)


class Interjornada(Base):
    modo: str = Field(default="aviso", pattern="^(off|aviso|rigida)$")
    horas: int = Field(default=11, ge=0, le=24)


class RegraAtribuicao(Base):
    regra: str = Field(default="FATEC", pattern="^(FATEC|ETEC)$")
    desempates: list[str] = Field(
        default_factory=lambda: ["assiduidade", "titulacao", "tempo_exercicio", "filhos"]
    )


class Pesos(Base):
    nao_concentradas: int = Field(default=100_000, ge=0)
    """Por disciplina marcada para concentrar que nao coube concentrada. Bem
    acima dos outros de proposito: na pratica e' regra sempre que couber."""
    janela_turma: int = Field(default=1000, ge=0)
    janela_professor: int = Field(default=100, ge=0)
    preferencia: int = Field(default=40, ge=0)
    dias_professor: int = Field(default=25, ge=0)
    estabilidade: int = Field(default=10, ge=0)
    dia_curto_no_fim: int = Field(default=5, ge=0)


class ConfigRegras(Base):
    carga_max_semanal: int = Field(default=29, ge=1, le=60)
    limite_diario: LimiteDiario = Field(default_factory=LimiteDiario)
    interjornada: Interjornada = Field(default_factory=Interjornada)
    deslocamento_entre_unidades_min: int = Field(default=0, ge=0, le=600)
    usa_sabado: bool = False
    atribuicao: RegraAtribuicao = Field(default_factory=RegraAtribuicao)
    pesos: Pesos = Field(default_factory=Pesos)
    modo_objetivo: ModoObjetivo = "ponderado"


# --------------------------------------------------------------------------- PATCH

EscopoParcial = parcial(EscopoEntrada)
UnidadeParcial = parcial(UnidadeEntrada)
ModeloTurnoParcial = parcial(ModeloTurnoEntrada)
CursoParcial = parcial(CursoEntrada)
TurmaParcial = parcial(TurmaEntrada)
DisciplinaParcial = parcial(DisciplinaEntrada)
EspacoParcial = parcial(EspacoEntrada)
ProfessorParcial = parcial(ProfessorEntrada)
VinculoParcial = parcial(VinculoEntrada)
HabilitacaoParcial = parcial(HabilitacaoEntrada)
AtribuicaoParcial = parcial(AtribuicaoEntrada)
DisponibilidadeParcial = parcial(DisponibilidadeEntrada)


# ---------------------------------------------------------------------- versoes


class DuplicarGrade(Base):
    nome: str | None = Field(None, max_length=120)


class DiferencaGrade(Base):
    """Uma linha da comparacao entre duas versoes."""

    tipo: Literal["igual", "horario", "espaco", "professor", "removida", "adicionada"]
    rotulo_tipo: str
    oferta_id: int
    bloco_idx: int
    rotulo: str
    antes: str | None
    depois: str | None


class MetricaComparada(Base):
    nome: str
    primeira: float | None
    segunda: float | None


class ComparacaoGrades(Base):
    primeira: Grade
    segunda: Grade
    resumo: dict[str, int]
    metricas: list[MetricaComparada]
    diferencas: list[DiferencaGrade]


# -------------------------------------------------------------------- importar


class ColunaModelo(Base):
    nome: str
    ajuda: str
    exemplo: str
    obrigatoria: bool


class ModeloImportacao(Base):
    tipo: str
    titulo: str
    descricao: str
    colunas: list[ColunaModelo]


class LinhaImportacao(Base):
    numero: int
    acao: Literal["criar", "atualizar", "ignorar", "erro"]
    descricao: str
    erro: str | None


class RelatorioImportacao(Base):
    tipo: str
    aplicado: bool
    """Falso na conferencia: nada foi gravado."""
    total: int
    resumo: dict[str, int]
    linhas: list[LinhaImportacao]
