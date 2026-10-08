"""Traducao do banco para `GradeState`.

Unico ponto do sistema que sabe, ao mesmo tempo, de SQLAlchemy e do dominio do
solver. Carrega tambem as aulas ja' **publicadas** nas outras unidades do mesmo
escopo — e' o que permite detectar choque entre a Fatec e a Etec da mesma cidade
e conferir a interjornada somando as duas.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.scheduling.domain import (
    DIAS,
    AlocacaoInfo,
    DisciplinaInfo,
    EspacoInfo,
    GradeState,
    OcupacaoExterna,
    OfertaInfo,
    ProfessorInfo,
    SlotInfo,
    TurmaInfo,
    VinculoInfo,
    hhmm,
    minutos,
)
from app.schemas import ConfigRegras


def config_da_unidade(unidade: m.Unidade) -> ConfigRegras:
    """As regras da unidade ja' validadas, com os padroes preenchidos.

    Uma unidade criada antes de um campo novo existir nao tem a chave gravada;
    passar pelo schema garante que o validador e o solver nunca leiam `None`.
    """
    return ConfigRegras.model_validate(unidade.config_regras or {})


def carregar_estado(
    db: Session, unidade_id: int, grade_id: int | None = None
) -> tuple[GradeState, ConfigRegras]:
    """Estado completo da unidade. Sem `grade_id`, o estado vem sem alocacoes —
    e' a forma usada pela pre-validacao, antes de existir qualquer grade."""
    unidade = db.get(m.Unidade, unidade_id)
    if unidade is None:
        raise LookupError(f"Unidade {unidade_id} nao encontrada.")

    estado = GradeState(unidade_id=unidade.id, unidade_nome=unidade.nome)

    cursos = db.scalars(select(m.Curso).where(m.Curso.unidade_id == unidade_id)).all()
    sigla_do_curso = {c.id: c.sigla for c in cursos}
    ids_cursos = list(sigla_do_curso)

    for turma in db.scalars(select(m.Turma).where(m.Turma.curso_id.in_(ids_cursos))):
        estado.turmas[turma.id] = TurmaInfo(
            id=turma.id,
            curso_id=turma.curso_id,
            curso_sigla=sigla_do_curso[turma.curso_id],
            periodo=turma.periodo,
            modelo_turno_id=turma.modelo_turno_id,
            qtd_alunos=turma.qtd_alunos,
            turno=turma.turno,
        )

    for d in db.scalars(select(m.Disciplina).where(m.Disciplina.curso_id.in_(ids_cursos))):
        estado.disciplinas[d.id] = DisciplinaInfo(
            id=d.id,
            nome=d.nome,
            sigla=d.sigla,
            aulas_semanais=d.aulas_semanais,
            tamanho_bloco=d.tamanho_bloco,
            modalidade=d.modalidade,
            precisa_laboratorio=d.precisa_laboratorio,
            tipo_laboratorio=d.tipo_laboratorio,
            divisao_turma=d.divisao_turma,
            modo_divisao=d.modo_divisao,
            max_blocos_por_dia=d.max_blocos_por_dia,
            concentrar_no_dia=d.concentrar_no_dia,
        )

    # Modelos de turno: so' os que as turmas realmente usam, mais todos os da
    # unidade (a tela de disponibilidade pode marcar horario de um turno vazio).
    for slot in db.scalars(
        select(m.Slot).join(m.ModeloTurno).where(m.ModeloTurno.unidade_id == unidade_id)
    ):
        estado.slots[slot.id] = SlotInfo(
            id=slot.id,
            modelo_turno_id=slot.modelo_turno_id,
            dia=slot.dia_semana,
            ordem=slot.ordem,
            bloco_id=slot.bloco_id,
            inicio_min=minutos(slot.inicio),
            fim_min=minutos(slot.fim),
        )

    for e in db.scalars(select(m.Espaco).where(m.Espaco.unidade_id == unidade_id)):
        estado.espacos[e.id] = EspacoInfo(
            id=e.id,
            nome=e.nome,
            tipo=e.tipo,
            tipo_laboratorio=e.tipo_laboratorio,
            capacidade=e.capacidade,
        )

    for oferta in db.scalars(
        select(m.Oferta)
        .where(m.Oferta.turma_id.in_(list(estado.turmas)))
        .options(selectinload(m.Oferta.atribuicao))
    ):
        estado.ofertas[oferta.id] = OfertaInfo(
            id=oferta.id,
            turma_id=oferta.turma_id,
            disciplina_id=oferta.disciplina_id,
            subturma=oferta.subturma,
            professor_id=oferta.atribuicao.professor_id if oferta.atribuicao else None,
        )

    for vinculo in db.scalars(
        select(m.VinculoUnidade)
        .where(m.VinculoUnidade.unidade_id == unidade_id)
        .options(selectinload(m.VinculoUnidade.professor))
    ):
        estado.vinculos[vinculo.professor_id] = VinculoInfo(
            professor_id=vinculo.professor_id,
            unidade_id=unidade_id,
            tipo_contrato=vinculo.tipo_contrato,
            pontuacao=vinculo.pontuacao,
            pont_assiduidade=vinculo.pont_assiduidade,
            pont_titulacao=vinculo.pont_titulacao,
            tempo_exercicio_meses=vinculo.tempo_exercicio_meses,
            num_filhos=vinculo.num_filhos,
            carga_max_semanal=vinculo.carga_max_semanal,
        )
        estado.professores[vinculo.professor_id] = ProfessorInfo(
            id=vinculo.professor_id, nome=vinculo.professor.nome
        )

    # Professores atribuidos sem vinculo aparecem nas mensagens mesmo assim; a
    # falta do vinculo e' reportada pela pre-validacao.
    faltando = {
        o.professor_id
        for o in estado.ofertas.values()
        if o.professor_id is not None and o.professor_id not in estado.professores
    }
    for prof in db.scalars(select(m.Professor).where(m.Professor.id.in_(faltando))):
        estado.professores[prof.id] = ProfessorInfo(id=prof.id, nome=prof.nome)

    for hab in db.scalars(
        select(m.Habilitacao).where(m.Habilitacao.disciplina_id.in_(list(estado.disciplinas)))
    ):
        estado.habilitacoes[(hab.professor_id, hab.disciplina_id)] = hab.origem

    for disp in db.scalars(
        select(m.Disponibilidade).where(m.Disponibilidade.slot_id.in_(list(estado.slots)))
    ):
        estado.disponibilidade[(disp.professor_id, disp.slot_id)] = disp.status

    if grade_id is not None:
        for a in db.scalars(select(m.Alocacao).where(m.Alocacao.grade_id == grade_id)):
            estado.alocacoes.append(
                AlocacaoInfo(
                    id=a.id,
                    oferta_id=a.oferta_id,
                    professor_id=a.professor_id,
                    slot_id=a.slot_id,
                    espaco_id=a.espaco_id,
                    bloco_idx=a.bloco_idx,
                    fixada=a.fixada,
                )
            )

    estado.ocupacoes_externas = _ocupacoes_de_outras_unidades(db, unidade)
    return estado, config_da_unidade(unidade)


def _ocupacoes_de_outras_unidades(db: Session, unidade: m.Unidade) -> list[OcupacaoExterna]:
    """Aulas publicadas nas demais unidades do escopo.

    So' grades PUBLICADAS: rascunho de outra unidade ainda pode mudar, e travar
    horario por causa de um rascunho alheio bloquearia a unidade sem motivo.
    """
    linhas = db.execute(
        select(
            m.Alocacao.professor_id,
            m.Unidade.id,
            m.Unidade.nome,
            m.Slot.dia_semana,
            m.Slot.inicio,
            m.Slot.fim,
            m.Disciplina.sigla,
            m.Curso.sigla,
            m.Turma.periodo,
        )
        .join(m.Grade, m.Alocacao.grade_id == m.Grade.id)
        .join(m.Unidade, m.Grade.unidade_id == m.Unidade.id)
        .join(m.Slot, m.Alocacao.slot_id == m.Slot.id)
        .join(m.Oferta, m.Alocacao.oferta_id == m.Oferta.id)
        .join(m.Disciplina, m.Oferta.disciplina_id == m.Disciplina.id)
        .join(m.Turma, m.Oferta.turma_id == m.Turma.id)
        .join(m.Curso, m.Turma.curso_id == m.Curso.id)
        .where(
            m.Unidade.escopo_id == unidade.escopo_id,
            m.Unidade.id != unidade.id,
            m.Grade.status == m.StatusGrade.PUBLICADA,
        )
    ).all()

    return [
        OcupacaoExterna(
            professor_id=professor_id,
            unidade_id=unidade_id,
            unidade_nome=unidade_nome,
            dia=dia,
            inicio_min=minutos(inicio),
            fim_min=minutos(fim),
            rotulo=f"{sigla_disciplina} ({sigla_curso} {periodo})",
        )
        for (
            professor_id,
            unidade_id,
            unidade_nome,
            dia,
            inicio,
            fim,
            sigla_disciplina,
            sigla_curso,
            periodo,
        ) in linhas
    ]


__all__ = ["DIAS", "carregar_estado", "config_da_unidade", "hhmm"]
