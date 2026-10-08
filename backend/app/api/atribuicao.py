"""Atribuicao de aulas: quem da' qual oferta.

A sugestao automatica reproduz o ato de atribuicao das normas do CPS
(`app/scheduling/assignment.py`). O usuario pode sempre editar depois pela tela,
e o que ele editou a mao e' preservado por padrao.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app import models as m
from app import schemas as s
from app.crud import buscar_ou_404, gravando
from app.db import SessaoDb
from app.scheduling.assignment import classificar, sugerir_atribuicao
from app.scheduling.domain import GradeState
from app.scheduling.loader import carregar_estado
from app.schemas import ConfigRegras

router = APIRouter(tags=["atribuicao"])


def _classificacao(
    estado: GradeState, config: ConfigRegras, atribuicoes: dict[int, int]
) -> list[s.Classificado]:
    carga: dict[int, int] = dict.fromkeys(estado.vinculos, 0)
    for oferta_id, professor_id in atribuicoes.items():
        if professor_id in carga:
            carga[professor_id] += estado.disciplina_da(estado.ofertas[oferta_id]).aulas_semanais

    return [
        s.Classificado(
            posicao=posicao,
            professor_id=v.professor_id,
            professor_nome=estado.nome_professor(v.professor_id),
            tipo_contrato=v.tipo_contrato,
            pontuacao=v.pontuacao,
            pont_assiduidade=v.pont_assiduidade,
            pont_titulacao=v.pont_titulacao,
            tempo_exercicio_meses=v.tempo_exercicio_meses,
            num_filhos=v.num_filhos,
            carga_max=v.carga_max(config.carga_max_semanal),
            aulas_atribuidas=carga[v.professor_id],
        )
        for posicao, v in enumerate(classificar(estado, config), start=1)
    ]


@router.get("/unidades/{unidade_id}/atribuicao/classificacao", response_model=list[s.Classificado])
def classificacao(unidade_id: int, db: SessaoDb):
    """A lista de classificacao docente da unidade, na ordem em que as aulas sao
    oferecidas no ato de atribuicao."""
    buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    estado, config = carregar_estado(db, unidade_id)
    atuais = {o.id: o.professor_id for o in estado.ofertas.values() if o.professor_id}
    return _classificacao(estado, config, atuais)


@router.post("/unidades/{unidade_id}/atribuicao/sugerir", response_model=s.ResultadoAtribuicao)
def sugerir(
    unidade_id: int,
    db: SessaoDb,
    substituir: Annotated[
        bool,
        Query(description="Refaz tudo, descartando as atribuições feitas a mão."),
    ] = False,
):
    """Distribui as ofertas sem professor seguindo a regra da unidade.

    Grava as atribuicoes e devolve os avisos de prioridade, que dizem quem
    perdeu cada disputa e por qual critério.
    """
    buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    estado, config = carregar_estado(db, unidade_id)

    preservar = (
        {}
        if substituir
        else {o.id: o.professor_id for o in estado.ofertas.values() if o.professor_id}
    )
    resultado = sugerir_atribuicao(estado, config, preservar=preservar)

    with gravando(db, "Atribuicao"):
        if substituir:
            for atribuicao in db.query(m.Atribuicao).filter(
                m.Atribuicao.oferta_id.in_(list(estado.ofertas))
            ):
                db.delete(atribuicao)
            db.flush()
        for oferta_id, professor_id in resultado.novas.items():
            db.add(m.Atribuicao(oferta_id=oferta_id, professor_id=professor_id))

    return s.ResultadoAtribuicao(
        atribuidas=len(resultado.novas),
        preservadas=len(preservar),
        sem_professor=resultado.sem_professor,
        avisos=[
            s.Violacao(
                tipo=v.tipo,
                severidade=v.severidade,
                mensagem=v.mensagem,
                entidades=v.entidades,
            )
            for v in resultado.avisos
        ],
        classificacao=_classificacao(estado, config, resultado.atribuicoes),
    )


@router.delete("/unidades/{unidade_id}/atribuicao", status_code=204)
def limpar(unidade_id: int, db: SessaoDb):
    """Desfaz toda a atribuicao da unidade."""
    buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    estado, _ = carregar_estado(db, unidade_id)
    with gravando(db, "Atribuicao"):
        for atribuicao in db.query(m.Atribuicao).filter(
            m.Atribuicao.oferta_id.in_(list(estado.ofertas))
        ):
            db.delete(atribuicao)
