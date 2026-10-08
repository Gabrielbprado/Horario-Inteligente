"""Chat de edição da grade: conversa por SSE e aplicação de propostas."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app import models as m
from app import schemas as s
from app.chat import propostas, service, tools
from app.crud import buscar_ou_404, gravando
from app.db import SessaoDb, SessionLocal
from app.scheduling.loader import carregar_estado

router = APIRouter(tags=["chat"])


@router.get("/chat/estado", response_model=s.EstadoChat)
def estado_do_chat():
    """A tela pergunta isto antes de mostrar o painel."""
    ativo = service.disponivel()
    return s.EstadoChat(
        ativo=ativo,
        mensagem=None
        if ativo
        else "Chat desativado: configure OPENAI_API_KEY e OPENAI_MODEL no servidor.",
    )


def _contexto(db, grade_id: int) -> tuple[m.Grade, tools.Contexto]:
    grade = buscar_ou_404(db, m.Grade, grade_id, "Grade")
    estado, config = carregar_estado(db, grade.unidade_id, grade_id=grade.id)
    return grade, tools.Contexto(db=db, grade=grade, estado=estado, config=config)


@router.post("/grades/{grade_id}/chat")
def conversar(grade_id: int, entrada: s.MensagemChat, db: SessaoDb):
    """Responde em SSE: texto em pedaços, ferramentas chamadas e propostas.

    A sessão da requisição fecha quando a resposta começa a ser enviada, então
    o gerador abre a sua própria.
    """
    if not service.disponivel():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Chat desativado: configure OPENAI_API_KEY e OPENAI_MODEL no servidor.",
        )
    buscar_ou_404(db, m.Grade, grade_id, "Grade")

    def fluxo():
        with SessionLocal() as sessao:
            _, ctx = _contexto(sessao, grade_id)
            historico = [{"role": msg.papel, "content": msg.texto} for msg in entrada.historico]
            historico.append({"role": "user", "content": entrada.texto})
            for evento in service.conversar(ctx, historico):
                yield evento.sse()

    return StreamingResponse(
        fluxo(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/grades/{grade_id}/propostas", response_model=list[s.Proposta])
def listar_propostas(grade_id: int, db: SessaoDb):
    buscar_ou_404(db, m.Grade, grade_id, "Grade")
    return [_para_schema(p) for p in propostas.REGISTRO.da_grade(grade_id) if p.pendente]


@router.post("/propostas/{proposta_id}/aplicar", response_model=s.ResultadoMovimento)
def aplicar_proposta(
    proposta_id: str, db: SessaoDb, autor: str | None = None, forcar: bool = False
):
    """Aplica o que o assistente propôs, pelo caminho normal de escrita."""
    proposta = propostas.REGISTRO.por_id(proposta_id)
    if proposta is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Essa proposta expirou. Peça de novo ao assistente.",
        )
    grade, ctx = _contexto(db, proposta.grade_id)

    try:
        with gravando(db, "Grade"):
            resultado = propostas.aplicar(
                db, proposta, ctx.estado, ctx.config, grade, autor=autor, forcar=forcar
            )
    except propostas.PropostaInvalida as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro
    except Exception as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro

    return s.ResultadoMovimento(
        permitido=True,
        severidade=resultado.severidade,
        descricao=resultado.descricao or proposta.descricao,
        alteracoes=[
            s.AlteracaoResumo(alocacao_id=a.alocacao_id, antes=a.antes, depois=a.depois)
            for a in resultado.alteracoes
        ],
        violacoes=[
            s.Violacao(
                tipo=v.tipo,
                severidade=v.severidade,
                mensagem=v.mensagem,
                entidades=v.entidades,
            )
            for v in resultado.violacoes
        ],
        aplicado=True,
    )


@router.post("/propostas/{proposta_id}/descartar", response_model=s.Proposta)
def descartar_proposta(proposta_id: str):
    proposta = propostas.REGISTRO.por_id(proposta_id)
    if proposta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa proposta expirou.")
    proposta.descartada = True
    return _para_schema(proposta)


def _para_schema(proposta: propostas.Proposta) -> s.Proposta:
    return s.Proposta(
        id=proposta.id,
        grade_id=proposta.grade_id,
        tipo=proposta.tipo,
        descricao=proposta.descricao,
        permitido=proposta.permitido,
        aplicada=proposta.aplicada,
        descartada=proposta.descartada,
        mudancas=[
            s.MudancaProposta(rotulo=x.rotulo, antes=x.antes, depois=x.depois)
            for x in proposta.mudancas
        ],
        violacoes=[
            s.Violacao(
                tipo=v.tipo,
                severidade=v.severidade,
                mensagem=v.mensagem,
                entidades=v.entidades,
            )
            for v in proposta.violacoes
        ],
    )
