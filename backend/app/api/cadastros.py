"""Routers de cadastro. As entidades regulares vem da fabrica `router_crud`;
o que foge do CRUD puro esta nos ganchos e nas rotas extras deste modulo."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app import schemas as s
from app.crud import buscar_ou_404, gravando, router_crud
from app.db import SessaoDb
from app.presets import PRESETS_POR_TIPO, PRESETS_TURNO, aplicar_preset_unidade
from app.services import sincronizar_ofertas

# --------------------------------------------------------------------- ganchos


def _preset_na_criacao(db: Session, unidade: m.Unidade) -> None:
    """Unidade nova ja nasce com as regras e os modelos de turno do seu tipo.
    Se o cliente mandou `config_regras`, respeita o que veio."""
    if not unidade.config_regras:
        aplicar_preset_unidade(unidade)
        db.flush()


def _sincronizar_turma(db: Session, turma: m.Turma) -> None:
    sincronizar_ofertas(db, turma)


def _sincronizar_curso_da_disciplina(db: Session, disciplina: m.Disciplina) -> None:
    """Mudou a matriz: recria as ofertas de todas as turmas do curso.

    Todas, e nao so as do periodo atual, porque a disciplina pode ter acabado de
    mudar de periodo e as turmas do periodo antigo tambem ficaram desatualizadas.
    """
    turmas = db.scalars(select(m.Turma).where(m.Turma.curso_id == disciplina.curso_id)).all()
    for turma in turmas:
        sincronizar_ofertas(db, turma)


def _bloquear_se_tem_grade(db: Session, unidade: m.Unidade) -> None:
    if db.scalar(select(m.Grade.id).where(m.Grade.unidade_id == unidade.id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{unidade.nome} tem grades salvas. Apague as grades antes de remover a unidade.",
        )


# ------------------------------------------------------------------- CRUD simples

escopos = router_crud(
    prefixo="/escopos",
    rotulo="Escopo",
    modelo=m.Escopo,
    leitura=s.Escopo,
    entrada=s.EscopoEntrada,
    parcial=s.EscopoParcial,
    ordem=("nome",),
)

unidades = router_crud(
    prefixo="/unidades",
    rotulo="Unidade",
    modelo=m.Unidade,
    leitura=s.Unidade,
    entrada=s.UnidadeEntrada,
    parcial=s.UnidadeParcial,
    filtros=("escopo_id",),
    ordem=("nome",),
    apos_criar=_preset_na_criacao,
    antes_apagar=_bloquear_se_tem_grade,
)

cursos = router_crud(
    prefixo="/cursos",
    rotulo="Curso",
    modelo=m.Curso,
    leitura=s.Curso,
    entrada=s.CursoEntrada,
    parcial=s.CursoParcial,
    filtros=("unidade_id",),
    ordem=("sigla",),
)

turmas = router_crud(
    prefixo="/turmas",
    rotulo="Turma",
    modelo=m.Turma,
    leitura=s.Turma,
    entrada=s.TurmaEntrada,
    parcial=s.TurmaParcial,
    filtros=("curso_id", "modelo_turno_id"),
    ordem=("curso_id", "periodo"),
    apos_criar=_sincronizar_turma,
    apos_atualizar=_sincronizar_turma,
)

disciplinas = router_crud(
    prefixo="/disciplinas",
    rotulo="Disciplina",
    modelo=m.Disciplina,
    leitura=s.Disciplina,
    entrada=s.DisciplinaEntrada,
    parcial=s.DisciplinaParcial,
    filtros=("curso_id",),
    ordem=("curso_id", "periodo", "sigla"),
    apos_criar=_sincronizar_curso_da_disciplina,
    apos_atualizar=_sincronizar_curso_da_disciplina,
)

espacos = router_crud(
    prefixo="/espacos",
    rotulo="Espaco",
    modelo=m.Espaco,
    leitura=s.Espaco,
    entrada=s.EspacoEntrada,
    parcial=s.EspacoParcial,
    filtros=("unidade_id",),
    ordem=("tipo", "nome"),
)

professores = router_crud(
    prefixo="/professores",
    rotulo="Professor",
    modelo=m.Professor,
    leitura=s.Professor,
    entrada=s.ProfessorEntrada,
    parcial=s.ProfessorParcial,
    filtros=("escopo_id",),
    ordem=("nome",),
)

vinculos = router_crud(
    prefixo="/vinculos",
    rotulo="Vinculo",
    modelo=m.VinculoUnidade,
    leitura=s.Vinculo,
    entrada=s.VinculoEntrada,
    parcial=s.VinculoParcial,
    filtros=("professor_id", "unidade_id"),
    ordem=("unidade_id", "id"),
)

habilitacoes = router_crud(
    prefixo="/habilitacoes",
    rotulo="Habilitacao",
    modelo=m.Habilitacao,
    leitura=s.Habilitacao,
    entrada=s.HabilitacaoEntrada,
    parcial=s.HabilitacaoParcial,
    filtros=("professor_id", "disciplina_id"),
)

atribuicoes = router_crud(
    prefixo="/atribuicoes",
    rotulo="Atribuicao",
    modelo=m.Atribuicao,
    leitura=s.Atribuicao,
    entrada=s.AtribuicaoEntrada,
    parcial=s.AtribuicaoParcial,
    filtros=("professor_id", "oferta_id"),
)

disponibilidades = router_crud(
    prefixo="/disponibilidades",
    rotulo="Disponibilidade",
    modelo=m.Disponibilidade,
    leitura=s.Disponibilidade,
    entrada=s.DisponibilidadeEntrada,
    parcial=s.DisponibilidadeParcial,
    filtros=("professor_id", "unidade_id", "slot_id"),
)


# ------------------------------------------------------------------- rotas extras

extras = APIRouter()


@extras.get("/presets/turno", response_model=list[s.PresetTurnoResumo], tags=["presets"])
def listar_presets_turno(tipo: m.TipoUnidade | None = None):
    """Presets de modelo de turno, opcionalmente filtrados pelo tipo de unidade."""
    chaves = PRESETS_POR_TIPO[tipo] if tipo else list(PRESETS_TURNO)
    return [
        s.PresetTurnoResumo(
            chave=p.chave,
            nome=p.nome,
            dias_semana=sorted(p.dias),
            aulas_por_dia={dia: sum(len(b) for b in blocos) for dia, blocos in p.dias.items()},
        )
        for p in (PRESETS_TURNO[c] for c in chaves)
    ]


# A rota da spec e' minuscula: POST /unidades/{id}/presets/{fatec|etec}
TIPO_POR_ROTA = {"fatec": m.TipoUnidade.FATEC, "etec": m.TipoUnidade.ETEC}


@extras.post("/unidades/{unidade_id}/presets/{tipo}", response_model=s.Unidade, tags=["unidades"])
def aplicar_preset(
    unidade_id: int,
    tipo: Literal["fatec", "etec"],
    db: SessaoDb,
    substituir_regras: Annotated[
        bool, Query(description="Sobrescreve config_regras com os padroes do tipo.")
    ] = True,
):
    """(Re)aplica os padroes de um tipo de unidade. Modelos de turno ja existentes
    com o mesmo `preset_origem` sao preservados."""
    unidade = buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    regras_atuais = dict(unidade.config_regras or {})
    with gravando(db, "Unidade"):
        aplicar_preset_unidade(unidade, tipo=TIPO_POR_ROTA[tipo])
        if not substituir_regras and regras_atuais:
            unidade.config_regras = regras_atuais
    db.refresh(unidade)
    return unidade


@extras.get(
    "/unidades/{unidade_id}/config-regras", response_model=s.ConfigRegras, tags=["unidades"]
)
def ler_config_regras(unidade_id: int, db: SessaoDb):
    unidade = buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    return s.ConfigRegras.model_validate(unidade.config_regras or {})


@extras.put(
    "/unidades/{unidade_id}/config-regras", response_model=s.ConfigRegras, tags=["unidades"]
)
def gravar_config_regras(unidade_id: int, regras: s.ConfigRegras, db: SessaoDb):
    """Valida antes de gravar: o solver nunca deve ler uma chave ausente."""
    unidade = buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    with gravando(db, "Unidade"):
        unidade.config_regras = regras.model_dump()
        unidade.carga_max_semanal_padrao = regras.carga_max_semanal
    return regras


@extras.get("/ofertas", response_model=list[s.OfertaDetalhe], tags=["ofertas"])
def listar_ofertas(
    db: SessaoDb,
    unidade_id: int | None = None,
    turma_id: int | None = None,
    curso_id: int | None = None,
):
    """Ofertas com disciplina, turma e professor atribuido ja resolvidos.

    A tela de atribuicao precisa das tres coisas juntas; devolver so os ids faria
    o frontend disparar uma consulta por linha.
    """
    consulta = (
        select(m.Oferta)
        .join(m.Turma)
        .join(m.Curso)
        .options(
            selectinload(m.Oferta.disciplina),
            selectinload(m.Oferta.turma).selectinload(m.Turma.curso),
            selectinload(m.Oferta.atribuicao).selectinload(m.Atribuicao.professor),
        )
        .order_by(m.Curso.sigla, m.Turma.periodo, m.Oferta.id)
    )
    if unidade_id is not None:
        consulta = consulta.where(m.Curso.unidade_id == unidade_id)
    if curso_id is not None:
        consulta = consulta.where(m.Turma.curso_id == curso_id)
    if turma_id is not None:
        consulta = consulta.where(m.Oferta.turma_id == turma_id)

    return [
        s.OfertaDetalhe(
            id=o.id,
            turma_id=o.turma_id,
            disciplina_id=o.disciplina_id,
            subturma=o.subturma,
            disciplina_nome=o.disciplina.nome,
            disciplina_sigla=o.disciplina.sigla,
            aulas_semanais=o.disciplina.aulas_semanais,
            turma_periodo=o.turma.periodo,
            curso_sigla=o.turma.curso.sigla,
            professor_id=o.atribuicao.professor_id if o.atribuicao else None,
            professor_nome=o.atribuicao.professor.nome if o.atribuicao else None,
        )
        for o in db.scalars(consulta)
    ]


@extras.put("/cursos/{curso_id}/blocos", response_model=list[s.Disciplina], tags=["cursos"])
def aplicar_blocos_do_curso(curso_id: int, dados: s.BlocosDoCurso, db: SessaoDb):
    """Grava tamanho do bloco, blocos por dia e/ou concentracao em todas as
    disciplinas do curso. A escola decide isso por curso; o solver le na
    disciplina, que continua editavel uma a uma como excecao."""
    curso = buscar_ou_404(db, m.Curso, curso_id, "Curso")
    mudancas = dados.model_dump(exclude_none=True)
    with gravando(db, "Disciplina"):
        for disciplina in curso.disciplinas:
            for campo, valor in mudancas.items():
                setattr(disciplina, campo, valor)
    return sorted(curso.disciplinas, key=lambda d: (d.periodo, d.sigla))


@extras.put(
    "/disponibilidades/lote",
    response_model=list[s.Disponibilidade],
    tags=["disponibilidades"],
)
def gravar_disponibilidade_em_lote(lote: s.DisponibilidadeLote, db: SessaoDb):
    """Marca varios slots de uma vez ("noite inteira", "copiar de outro dia").

    `DISPONIVEL` apaga o registro: ausencia de linha ja significa disponivel
    (ver DECISOES.md D16).
    """
    buscar_ou_404(db, m.Professor, lote.professor_id, "Professor")
    buscar_ou_404(db, m.Unidade, lote.unidade_id, "Unidade")

    existentes = {
        d.slot_id: d
        for d in db.scalars(
            select(m.Disponibilidade).where(
                m.Disponibilidade.professor_id == lote.professor_id,
                m.Disponibilidade.slot_id.in_(lote.slot_ids),
            )
        )
    }

    resultado: list[m.Disponibilidade] = []
    with gravando(db, "Disponibilidade"):
        for slot_id in lote.slot_ids:
            atual = existentes.get(slot_id)
            if lote.status == m.StatusDisponibilidade.DISPONIVEL:
                if atual is not None:
                    db.delete(atual)
                continue
            if atual is None:
                atual = m.Disponibilidade(
                    professor_id=lote.professor_id,
                    unidade_id=lote.unidade_id,
                    slot_id=slot_id,
                    status=lote.status,
                )
                db.add(atual)
            else:
                atual.status = lote.status
                atual.unidade_id = lote.unidade_id
            resultado.append(atual)
    return resultado


ROUTERS = [
    escopos,
    unidades,
    cursos,
    turmas,
    disciplinas,
    espacos,
    professores,
    vinculos,
    habilitacoes,
    atribuicoes,
    disponibilidades,
    extras,
]
