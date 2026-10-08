"""Exportação da grade em PDF e Excel."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app import models as m
from app import schemas as s
from app.crud import buscar_ou_404
from app.db import SessaoDb
from app.export import pdf, xlsx
from app.export.visao import montar_visao

router = APIRouter(tags=["exportar"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TIPOS = {"pdf": "application/pdf", "xlsx": XLSX}

ROTULO_VISAO = {"turma": "por turma", "professor": "por professor", "espaco": "por sala"}


def _sem_acento(texto: str) -> str:
    """Nome de arquivo: `Content-Disposition` só é interoperável em ASCII."""
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", plano).strip("-").lower() or "grade"


def _uma_coluna(visao: s.VisaoGrade, coluna_id: int) -> s.VisaoGrade:
    """Recorta a visão numa coluna só, para entregar a grade de um professor."""
    coluna = next((c for c in visao.colunas if c.id == coluna_id), None)
    if coluna is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"A visão {ROTULO_VISAO[visao.tipo]} não tem a coluna {coluna_id}.",
        )
    return visao.model_copy(update={"colunas": [coluna]})


@router.get(
    "/grades/{grade_id}/exportar",
    summary="Exportar a grade em PDF ou Excel",
    responses={200: {"content": {t: {} for t in TIPOS.values()}}},
)
def exportar(
    grade_id: int,
    db: SessaoDb,
    formato: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    tipo: s.TipoVisao = "turma",
    coluna_id: int | None = Query(None, description="Exporta só esta turma/professor/sala."),
):
    """Um documento por corte: uma página (ou aba) por turma, professor ou sala."""
    grade = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    unidade = buscar_ou_404(db, m.Unidade, grade.unidade_id, "Unidade")

    visao = montar_visao(db, grade, tipo)
    if coluna_id is not None:
        visao = _uma_coluna(visao, coluna_id)

    cabecalho = f"{unidade.nome} · {grade.nome} · {ROTULO_VISAO[tipo]}"
    rodape = (
        f"{unidade.nome} — {grade.nome} ({grade.status.value.lower()}) · "
        f"exportado em {datetime.now():%d/%m/%Y %H:%M}"
    )

    if formato == "pdf":
        corpo = pdf.gerar(visao, cabecalho, rodape)
    else:
        corpo = xlsx.gerar(visao, cabecalho)

    nome = f"{_sem_acento(unidade.nome)}-{_sem_acento(grade.nome)}-{tipo}.{formato}"
    return Response(
        corpo,
        media_type=TIPOS[formato],
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
