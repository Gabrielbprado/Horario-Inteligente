"""Edicao manual da grade: arrastar, trocar, fixar e desfazer.

Todas as rotas passam por `app/scheduling/apply.py`, que valida antes de gravar
e registra o historico. E' o mesmo caminho que o chatbot usa na etapa 8.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import models as m
from app import schemas as s
from app.crud import HTTP_422, buscar_ou_404, gravando
from app.db import SessaoDb
from app.scheduling import apply
from app.scheduling.loader import carregar_estado

router = APIRouter(tags=["edicao"])


def _contexto(db, grade_id: int):
    grade = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    estado, config = carregar_estado(db, grade.unidade_id, grade_id=grade.id)
    return grade, estado, config


def _resposta(resultado: apply.Resultado, aplicado: bool) -> s.ResultadoMovimento:
    return s.ResultadoMovimento(
        permitido=resultado.permitido,
        severidade=resultado.severidade,
        descricao=resultado.descricao,
        alteracoes=[
            s.AlteracaoResumo(alocacao_id=a.alocacao_id, antes=a.antes, depois=a.depois)
            for a in resultado.alteracoes
        ],
        violacoes=[
            s.Violacao(
                tipo=v.tipo, severidade=v.severidade, mensagem=v.mensagem, entidades=v.entidades
            )
            for v in resultado.violacoes
        ],
        aplicado=aplicado,
    )


@router.get("/grades/{grade_id}/destinos", response_model=list[s.DestinoPossivel])
def destinos(grade_id: int, db: SessaoDb, oferta_id: int, bloco_idx: int = 0):
    """Avalia de uma vez todos os horários para onde o bloco pode ir.

    A tela pinta a semana inteira ao começar o arrasto, sem uma requisição por
    célula sobrevoada.
    """
    _, estado, config = _contexto(db, grade_id)
    try:
        avaliados = apply.destinos_possiveis(estado, config, apply.Bloco(oferta_id, bloco_idx))
    except apply.MovimentoInvalido as erro:
        raise HTTPException(HTTP_422, str(erro)) from erro

    return [
        s.DestinoPossivel(
            slot_id=slot_id,
            severidade=resultado.severidade,
            motivos=[v.mensagem for v in resultado.violacoes],
        )
        for slot_id, resultado in sorted(avaliados.items())
    ]


@router.post("/grades/{grade_id}/validar-movimento", response_model=s.ResultadoMovimento)
def validar_movimento(grade_id: int, entrada: s.MovimentoEntrada, db: SessaoDb):
    """O que o movimento quebraria, sem aplicar."""
    _, estado, config = _contexto(db, grade_id)
    try:
        resultado = apply.simular_movimento(
            estado,
            config,
            apply.Bloco(entrada.oferta_id, entrada.bloco_idx),
            entrada.slot_inicial,
            entrada.espaco_id,
        )
    except apply.MovimentoInvalido as erro:
        raise HTTPException(HTTP_422, str(erro)) from erro
    return _resposta(resultado, aplicado=False)


@router.post("/grades/{grade_id}/aplicar-movimento", response_model=s.ResultadoMovimento)
def aplicar_movimento(
    grade_id: int, entrada: s.MovimentoEntrada, db: SessaoDb, autor: str | None = None
):
    grade, estado, config = _contexto(db, grade_id)
    try:
        with gravando(db, "Grade"):
            resultado = apply.mover(
                db,
                grade,
                estado,
                config,
                apply.Bloco(entrada.oferta_id, entrada.bloco_idx),
                entrada.slot_inicial,
                entrada.espaco_id,
                autor=autor,
                forcar=entrada.forcar,
            )
    except apply.MovimentoInvalido as erro:
        raise HTTPException(HTTP_422, str(erro)) from erro

    aplicado = resultado.permitido or entrada.forcar
    if not aplicado:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensagem": "O movimento viola uma regra rígida.",
                "motivos": [v.mensagem for v in resultado.violacoes],
            },
        )
    return _resposta(resultado, aplicado=True)


@router.post("/grades/{grade_id}/trocar", response_model=s.ResultadoMovimento)
def trocar(grade_id: int, entrada: s.TrocaEntrada, db: SessaoDb, autor: str | None = None):
    grade, estado, config = _contexto(db, grade_id)
    try:
        with gravando(db, "Grade"):
            resultado = apply.trocar(
                db,
                grade,
                estado,
                config,
                apply.Bloco(entrada.a.oferta_id, entrada.a.bloco_idx),
                apply.Bloco(entrada.b.oferta_id, entrada.b.bloco_idx),
                autor=autor,
                forcar=entrada.forcar,
            )
    except apply.MovimentoInvalido as erro:
        raise HTTPException(HTTP_422, str(erro)) from erro

    if not (resultado.permitido or entrada.forcar):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensagem": "A troca viola uma regra rígida.",
                "motivos": [v.mensagem for v in resultado.violacoes],
            },
        )
    return _resposta(resultado, aplicado=True)


@router.post("/grades/{grade_id}/fixar", response_model=s.ResultadoMovimento)
def fixar(grade_id: int, entrada: s.FixarEntrada, db: SessaoDb, autor: str | None = None):
    """Cadeado do bloco: ao regerar, ele não sai do lugar."""
    grade, estado, config = _contexto(db, grade_id)
    try:
        with gravando(db, "Grade"):
            resultado = apply.fixar(
                db,
                grade,
                estado,
                config,
                apply.Bloco(entrada.oferta_id, entrada.bloco_idx),
                entrada.fixada,
                autor=autor,
            )
    except apply.MovimentoInvalido as erro:
        raise HTTPException(HTTP_422, str(erro)) from erro
    return _resposta(resultado, aplicado=True)


@router.get("/grades/{grade_id}/historico", response_model=list[s.RegistroHistorico])
def historico(grade_id: int, db: SessaoDb):
    buscar_ou_404(db, m.Grade, grade_id, "Grade")
    registros = db.scalars(
        select(m.HistoricoAlteracao)
        .where(m.HistoricoAlteracao.grade_id == grade_id)
        .order_by(m.HistoricoAlteracao.id.desc())
    ).all()
    return [
        s.RegistroHistorico(
            id=r.id,
            origem=r.origem,
            autor=r.autor,
            timestamp=r.timestamp,
            descricao=r.diff.get("descricao", "alteração"),
            desfeito=r.desfeito,
        )
        for r in registros
    ]


@router.post("/grades/{grade_id}/desfazer", response_model=list[str])
def desfazer(grade_id: int, db: SessaoDb, passos: int = 1, autor: str | None = None):
    """Reverte as últimas alterações, da mais recente para a mais antiga."""
    grade, estado, config = _contexto(db, grade_id)
    with gravando(db, "Grade"):
        desfeitos = apply.desfazer(db, grade, estado, config, passos, autor=autor)
    if not desfeitos:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não há nada para desfazer nesta grade.")
    return desfeitos
