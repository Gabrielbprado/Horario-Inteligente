"""Pre-validacao e validacao de uma grade.

Expoe o **mesmo** motor usado pelo solver, pelo arrastar-e-soltar e pelo chat,
para a UI poder avisar antes de o usuario clicar em "Gerar grade".
"""

from __future__ import annotations

from fastapi import APIRouter

from app import models as m
from app import schemas as s
from app.crud import buscar_ou_404
from app.db import SessaoDb
from app.scheduling.loader import carregar_estado
from app.scheduling.prevalidate import prevalidar
from app.scheduling.validator import validar

router = APIRouter(tags=["validacao"])


@router.get("/unidades/{unidade_id}/pre-validacao", response_model=list[s.Violacao])
def pre_validacao(unidade_id: int, db: SessaoDb):
    """O que impede esta unidade de gerar uma grade, sem rodar o solver."""
    buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    estado, config = carregar_estado(db, unidade_id)
    return prevalidar(estado, config)


@router.get("/grades/{grade_id}/validacao", response_model=list[s.Violacao])
def validacao_da_grade(grade_id: int, db: SessaoDb):
    """Violacoes da grade como ela esta' agora."""
    grade = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    estado, config = carregar_estado(db, grade.unidade_id, grade_id=grade.id)
    return validar(estado, config)
