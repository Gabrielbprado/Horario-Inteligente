"""Versões de uma grade: duplicar e comparar."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import models as m
from app import schemas as s
from app.crud import buscar_ou_404, gravando
from app.db import SessaoDb
from app.scheduling.avisos import avisos_da_grade, gravar_avisos
from app.scheduling.diff import ROTULO, comparar, resumo
from app.scheduling.loader import carregar_estado

router = APIRouter(tags=["versoes"])

METRICAS = {
    "janela_turma": "Janelas de turma",
    "janela_professor": "Janelas de professor",
    "dias_professor": "Idas à unidade",
    "preferencia": "Preferências não atendidas",
    "dia_curto_no_fim": "Aulas longe do fim do dia",
    "estabilidade": "Distância da grade anterior",
    "objetivo": "Custo total do objetivo",
    "tempo_s": "Tempo do solver (s)",
}
"""Os mesmos rótulos da lista de grades na tela; a ordem é a de importância."""


@router.post(
    "/grades/{grade_id}/duplicar",
    response_model=s.Grade,
    status_code=status.HTTP_201_CREATED,
)
def duplicar(grade_id: int, entrada: s.DuplicarGrade, db: SessaoDb):
    """Cria uma versão nova com as mesmas aulas, para experimentar sem perder o
    que já estava bom.

    A cópia nasce fora de PUBLICADA: publicada é a versão que a unidade
    divulgou, e esta ainda não é. Os avisos são recalculados em vez de copiados
    — inclusive a ciência, que foi dada sobre a outra versão.
    """
    original = buscar_ou_404(db, m.Grade, grade_id, "Grade")

    with gravando(db, "Grade"):
        copia = m.Grade(
            unidade_id=original.unidade_id,
            nome=entrada.nome or _nome_da_copia(db, original),
            parametros_solver=dict(original.parametros_solver),
            score=dict(original.score),
        )
        db.add(copia)
        db.flush()

        for a in db.scalars(select(m.Alocacao).where(m.Alocacao.grade_id == original.id)):
            db.add(
                m.Alocacao(
                    grade_id=copia.id,
                    oferta_id=a.oferta_id,
                    professor_id=a.professor_id,
                    slot_id=a.slot_id,
                    espaco_id=a.espaco_id,
                    bloco_idx=a.bloco_idx,
                    fixada=a.fixada,
                )
            )
        db.flush()

        estado, config = carregar_estado(db, copia.unidade_id, grade_id=copia.id)
        avisos = gravar_avisos(db, copia.id, avisos_da_grade(estado, config))
        copia.status = (
            m.StatusGrade.AGUARDANDO_CIENCIA
            if any(a.severidade != m.Severidade.INFO for a in avisos)
            else m.StatusGrade.RASCUNHO
        )

    db.refresh(copia)
    return copia


def _nome_da_copia(db, original: m.Grade) -> str:
    """ "Grade 2 (cópia)", "Grade 2 (cópia 2)"... — o nome não é único no banco,
    mas repetido na lista não ajuda ninguém."""
    usados = {
        nome
        for (nome,) in db.execute(
            select(m.Grade.nome).where(m.Grade.unidade_id == original.unidade_id)
        )
    }
    nome = f"{original.nome} (cópia)"
    n = 2
    while nome in usados:
        nome = f"{original.nome} (cópia {n})"
        n += 1
    return nome


@router.get("/grades/{grade_id}/comparar", response_model=s.ComparacaoGrades)
def comparar_versoes(grade_id: int, com: int, db: SessaoDb):
    """O que mudou entre duas versões da mesma unidade."""
    primeira = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    segunda = buscar_ou_404(db, m.Grade, com, "Grade")
    if primeira.unidade_id != segunda.unidade_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "As duas grades são de unidades diferentes; não há o que comparar.",
        )
    if primeira.id == segunda.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Escolha duas grades diferentes.")

    estado_a, _ = carregar_estado(db, primeira.unidade_id, grade_id=primeira.id)
    estado_b, _ = carregar_estado(db, segunda.unidade_id, grade_id=segunda.id)
    diferencas = comparar(estado_a, estado_b)

    return s.ComparacaoGrades(
        primeira=primeira,
        segunda=segunda,
        resumo=resumo(diferencas),
        metricas=[
            s.MetricaComparada(
                nome=rotulo,
                primeira=_numero(primeira.score.get(chave)),
                segunda=_numero(segunda.score.get(chave)),
            )
            for chave, rotulo in METRICAS.items()
            if chave in primeira.score or chave in segunda.score
        ],
        diferencas=[
            s.DiferencaGrade(
                tipo=d.tipo,
                rotulo_tipo=ROTULO[d.tipo],
                oferta_id=d.oferta_id,
                bloco_idx=d.bloco_idx,
                rotulo=d.rotulo,
                antes=d.antes,
                depois=d.depois,
            )
            for d in diferencas
        ],
    )


def _numero(valor) -> float | None:
    return float(valor) if isinstance(valor, int | float) else None
