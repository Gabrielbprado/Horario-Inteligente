"""Monta a `VisaoGrade` — a grade pronta para desenhar.

Mora aqui, e nao no router, porque a tela, o PDF e o Excel desenham exatamente
a mesma coisa. Uma segunda montagem para exportar seria uma segunda chance de
divergir da tela.
"""

from __future__ import annotations

from datetime import time

from sqlalchemy.orm import Session

from app import models as m
from app import schemas as s
from app.scheduling.loader import carregar_estado


def montar_visao(db: Session, grade: m.Grade, tipo: str = "turma") -> s.VisaoGrade:
    """As linhas sao faixas de horario `(dia, inicio, fim)`, e nao o numero da
    aula: a mesma unidade pode ter turnos com horarios diferentes, e duas
    "1a aula" em horarios distintos nao sao a mesma linha."""
    estado, _ = carregar_estado(db, grade.unidade_id, grade_id=grade.id)

    celulas = [
        s.CelulaGrade(
            alocacao_id=a.id,
            oferta_id=a.oferta_id,
            disciplina_id=disciplina.id,
            disciplina_sigla=disciplina.sigla,
            disciplina_nome=disciplina.nome,
            turma_id=turma.id,
            turma_rotulo=turma.rotulo,
            subturma=oferta.subturma,
            professor_id=a.professor_id,
            professor_nome=estado.nome_professor(a.professor_id),
            espaco_id=a.espaco_id,
            espaco_nome=espaco.nome if espaco else None,
            slot_id=a.slot_id,
            modelo_turno_id=slot.modelo_turno_id,
            dia=slot.dia,
            ordem=slot.ordem,
            inicio=hora(slot.inicio_min),
            fim=hora(slot.fim_min),
            bloco_id=slot.bloco_id,
            bloco_idx=a.bloco_idx,
            remota=disciplina.remota,
            precisa_laboratorio=disciplina.precisa_laboratorio,
            fixada=a.fixada,
        )
        for a in estado.alocacoes
        if (slot := estado.slots.get(a.slot_id)) is not None
        and (oferta := estado.ofertas.get(a.oferta_id)) is not None
        for disciplina in [estado.disciplina_da(oferta)]
        for turma in [estado.turma_da(oferta)]
        for espaco in [estado.espacos.get(a.espaco_id) if a.espaco_id else None]
    ]

    return s.VisaoGrade(
        grade_id=grade.id,
        tipo=tipo,
        colunas=_colunas(estado, celulas, tipo),
        horarios=_horarios(estado),
        slots=_slots(estado),
        celulas=celulas,
    )


def hora(minutos: int) -> time:
    return time(minutos // 60, minutos % 60)


def _slots(estado) -> list:
    """Horarios dos turnos em uso, para a tela resolver onde a aula foi solta."""
    modelos = {t.modelo_turno_id for t in estado.turmas.values()}
    return [
        s.SlotRef(
            id=slot.id,
            modelo_turno_id=slot.modelo_turno_id,
            dia=slot.dia,
            ordem=slot.ordem,
            inicio=hora(slot.inicio_min),
            fim=hora(slot.fim_min),
            bloco_id=slot.bloco_id,
        )
        for slot in sorted(
            (x for x in estado.slots.values() if x.modelo_turno_id in modelos),
            key=lambda x: (x.dia, x.ordem),
        )
    ]


def _colunas(estado, celulas: list, tipo: str) -> list:
    if tipo == "turma":
        # Turno mais cedo primeiro (manha, tarde, noite), depois curso e periodo:
        # duas "DSM 1o sem" em turnos diferentes nao ficam lado a lado iguais.
        def inicio_do_turno(modelo_turno_id: int) -> int:
            slots = estado.slots_do_modelo(modelo_turno_id)
            return min((x.inicio_min for x in slots), default=0)

        turmas = sorted(
            estado.turmas.values(),
            key=lambda t: (inicio_do_turno(t.modelo_turno_id), t.curso_sigla, t.periodo),
        )
        return [
            s.ColunaVisao(
                id=t.id,
                titulo=t.rotulo,
                subtitulo=" · ".join(x for x in (t.turno, f"{t.qtd_alunos} alunos") if x),
                modelo_turno_id=t.modelo_turno_id,
            )
            for t in turmas
        ]
    if tipo == "professor":
        usados = {c.professor_id for c in celulas}
        return [
            s.ColunaVisao(
                id=pid,
                titulo=estado.nome_professor(pid),
                subtitulo=(
                    f"{v.pontuacao:.1f}".replace(".", ",")
                    if (v := estado.vinculos.get(pid))
                    else None
                ),
            )
            for pid in sorted(usados, key=estado.nome_professor)
        ]
    espacos = sorted(estado.espacos.values(), key=lambda e: (e.tipo.value, e.nome))
    return [
        s.ColunaVisao(
            id=e.id,
            titulo=e.nome,
            subtitulo=e.tipo_laboratorio or f"{e.capacidade} lugares",
            tipo=e.tipo.value,
        )
        for e in espacos
    ]


def _horarios(estado) -> list:
    """Faixas de horario que a visao precisa mostrar.

    Só entram os turnos que alguma turma realmente usa. Uma unidade costuma ter
    modelos cadastrados e ociosos (a Fatec do seed tem o de manhã sem nenhuma
    turma); incluí-los enchia a visão por professor de linhas vazias que a tela
    marcava como "janela" — um buraco em horário no qual ninguém poderia ter
    aula. Um docente com turmas em turnos diferentes continua aparecendo nos
    dois, porque os dois turnos têm turma.
    """
    modelos = {t.modelo_turno_id for t in estado.turmas.values()}

    faixas: dict[tuple[int, int, int], set[int]] = {}
    for slot in estado.slots.values():
        if slot.modelo_turno_id in modelos:
            faixas.setdefault((slot.dia, slot.inicio_min, slot.fim_min), set()).add(slot.ordem)

    return [
        s.LinhaHorario(dia=dia, inicio=hora(ini), fim=hora(fim), ordens=sorted(ordens))
        for (dia, ini, fim), ordens in sorted(faixas.items())
    ]
