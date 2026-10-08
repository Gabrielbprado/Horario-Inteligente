"""Geracao, acompanhamento e publicacao de grades."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import schemas as s
from app.crud import buscar_ou_404, gravando
from app.db import SessaoDb
from app.export.visao import montar_visao
from app.scheduling import jobs
from app.scheduling.avisos import marcar_ciente, pendencias_para_publicar
from app.scheduling.loader import carregar_estado
from app.scheduling.prevalidate import prevalidar
from app.scheduling.solver import Parametros

router = APIRouter(tags=["grades"])


def _parametros(entrada: s.ParametrosSolver, grade_anterior: list | None) -> Parametros:
    return Parametros(
        tempo_limite_s=entrada.tempo_limite_s,
        workers=entrada.workers,
        semente=entrada.semente,
        manter_fixadas=entrada.manter_fixadas,
        modo_objetivo=entrada.modo_objetivo,
        grade_anterior=grade_anterior,
        resolver_avisos=entrada.resolver_avisos,
    )


def _job_para_schema(job: jobs.Job) -> s.Progresso:
    return s.Progresso(
        job_id=job.id,
        grade_id=job.grade_id,
        status=job.status,
        terminado=job.terminado,
        solucoes=job.solucoes,
        objetivo=job.objetivo,
        limite_inferior=job.limite_inferior,
        tempo_s=round(job.tempo_s, 2),
        mensagem=job.mensagem,
        diagnostico=job.diagnostico,
        metricas=job.metricas,
        alocacoes=[
            s.AlocacaoParcial(
                oferta_id=a.oferta_id,
                professor_id=a.professor_id,
                slot_id=a.slot_id,
                espaco_id=a.espaco_id,
                bloco_idx=a.bloco_idx,
            )
            for a in job.parcial
        ],
    )


# ------------------------------------------------------------------- listagem


@router.get("/grades", response_model=list[s.Grade])
def listar(db: SessaoDb, unidade_id: int | None = None):
    consulta = select(m.Grade).order_by(m.Grade.id.desc())
    if unidade_id is not None:
        consulta = consulta.where(m.Grade.unidade_id == unidade_id)
    return db.scalars(consulta).all()


@router.get("/grades/{grade_id}", response_model=s.Grade)
def ler(grade_id: int, db: SessaoDb):
    return buscar_ou_404(db, m.Grade, grade_id, "Grade")


@router.delete("/grades/{grade_id}", status_code=status.HTTP_204_NO_CONTENT)
def apagar(grade_id: int, db: SessaoDb):
    grade = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    with gravando(db, "Grade"):
        db.delete(grade)


# -------------------------------------------------------------------- geracao


@router.post(
    "/unidades/{unidade_id}/grades/gerar",
    response_model=s.GradeGerada,
    status_code=status.HTTP_202_ACCEPTED,
)
def gerar(
    unidade_id: int,
    entrada: s.ParametrosSolver,
    tarefas: BackgroundTasks,
    db: SessaoDb,
):
    """Cria a grade e dispara o solver em segundo plano.

    Responde 202 na hora com `grade_id` e `job_id`: o usuário continua usando o
    sistema e acompanha por `GET /grades/{id}/progresso`.
    """
    unidade = buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")

    estado, config = carregar_estado(db, unidade_id)
    impedimentos = [
        v for v in prevalidar(estado, config) if v.severidade == m.Severidade.BLOQUEANTE
    ]
    if impedimentos:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensagem": "A unidade ainda não pode gerar a grade.",
                "pendencias": [
                    {"tipo": v.tipo, "mensagem": v.mensagem, "entidades": v.entidades}
                    for v in impedimentos
                ],
            },
        )

    anterior = _grade_base(db, unidade_id, entrada.partir_de)

    with gravando(db, "Grade"):
        grade = m.Grade(
            unidade_id=unidade_id,
            nome=entrada.nome or _proximo_nome(db, unidade),
            parametros_solver=entrada.model_dump(),
        )
        db.add(grade)
        db.flush()
        # Lido antes do commit: uma leitura depois dele reabriria a transacao
        # da requisicao, e o job (sessao propria) comeca logo em seguida.
        alocacoes_anteriores = _alocacoes_de(db, anterior) if anterior else None
        if anterior:
            _copiar_fixadas(db, anterior, grade)
        grade_id = grade.id

    job = jobs.REGISTRO.criar(grade_id, unidade_id)
    params = _parametros(entrada, alocacoes_anteriores)
    tarefas.add_task(jobs.executar, job.id, params)

    return s.GradeGerada(grade_id=grade_id, job_id=job.id)


def _proximo_nome(db: Session, unidade: m.Unidade) -> str:
    total = db.query(m.Grade).filter(m.Grade.unidade_id == unidade.id).count()
    return f"Grade {total + 1}"


def _grade_base(db: Session, unidade_id: int, partir_de: int | None) -> m.Grade | None:
    if partir_de is None:
        return None
    grade = buscar_ou_404(db, m.Grade, partir_de, "Grade")
    if grade.unidade_id != unidade_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "A grade de origem é de outra unidade.")
    return grade


def _alocacoes_de(db: Session, grade: m.Grade) -> list:
    from app.scheduling.domain import AlocacaoInfo

    return [
        AlocacaoInfo(
            id=a.id,
            oferta_id=a.oferta_id,
            professor_id=a.professor_id,
            slot_id=a.slot_id,
            espaco_id=a.espaco_id,
            bloco_idx=a.bloco_idx,
            fixada=a.fixada,
        )
        for a in db.scalars(select(m.Alocacao).where(m.Alocacao.grade_id == grade.id))
    ]


def _copiar_fixadas(db: Session, origem: m.Grade, destino: m.Grade) -> None:
    """Regenerar mantendo as fixadas: as aulas com cadeado vao junto."""
    for a in db.scalars(
        select(m.Alocacao).where(m.Alocacao.grade_id == origem.id, m.Alocacao.fixada.is_(True))
    ):
        db.add(
            m.Alocacao(
                grade_id=destino.id,
                oferta_id=a.oferta_id,
                professor_id=a.professor_id,
                slot_id=a.slot_id,
                espaco_id=a.espaco_id,
                bloco_idx=a.bloco_idx,
                fixada=True,
            )
        )
    db.flush()


@router.get("/grades/{grade_id}/progresso", response_model=s.Progresso)
def progresso(grade_id: int, db: SessaoDb):
    """Status do solver e a melhor solução encontrada até agora."""
    buscar_ou_404(db, m.Grade, grade_id, "Grade")
    job = jobs.REGISTRO.da_grade(grade_id)
    if job is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Não há execução recente do solver para esta grade.",
        )
    return _job_para_schema(job)


# --------------------------------------------------------------------- avisos


@router.get("/grades/{grade_id}/avisos", response_model=list[s.Aviso])
def listar_avisos(grade_id: int, db: SessaoDb):
    buscar_ou_404(db, m.Grade, grade_id, "Grade")
    return db.scalars(
        select(m.Aviso).where(m.Aviso.grade_id == grade_id).order_by(m.Aviso.id)
    ).all()


@router.post("/avisos/{aviso_id}/ciente", response_model=s.Aviso)
def dar_ciencia(aviso_id: int, db: SessaoDb, autor: str | None = None):
    aviso = buscar_ou_404(db, m.Aviso, aviso_id, "Aviso")
    with gravando(db, "Aviso"):
        marcar_ciente(aviso, autor)
    return aviso


@router.post("/grades/{grade_id}/avisos/ciente-todos", response_model=list[s.Aviso])
def dar_ciencia_em_todos(grade_id: int, db: SessaoDb, autor: str | None = None):
    buscar_ou_404(db, m.Grade, grade_id, "Grade")
    avisos = db.scalars(
        select(m.Aviso).where(
            m.Aviso.grade_id == grade_id,
            m.Aviso.severidade == m.Severidade.ALERTA,
            m.Aviso.ciente.is_(False),
        )
    ).all()
    with gravando(db, "Aviso"):
        for aviso in avisos:
            marcar_ciente(aviso, autor)
    return avisos


# ------------------------------------------------------------------ publicacao


@router.post("/grades/{grade_id}/publicar", response_model=s.Grade)
def publicar(grade_id: int, db: SessaoDb):
    """Publica a grade. Falha se houver bloqueantes ou alertas sem ciência."""
    grade = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    avisos = db.scalars(select(m.Aviso).where(m.Aviso.grade_id == grade_id)).all()

    motivos = pendencias_para_publicar(avisos)
    if motivos:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"mensagem": "A grade ainda não pode ser publicada.", "motivos": motivos},
        )

    with gravando(db, "Grade"):
        grade.status = m.StatusGrade.PUBLICADA
    return grade


# --------------------------------------------------------------------- visoes


@router.get("/grades/{grade_id}/visao", response_model=s.VisaoGrade)
def visao(grade_id: int, db: SessaoDb, tipo: s.TipoVisao = "turma"):
    """A grade pronta para desenhar, por turma, por professor ou por espaço."""
    grade = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    return montar_visao(db, grade, tipo)
