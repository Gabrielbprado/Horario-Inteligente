"""Servicos de dominio que mantem tabelas derivadas coerentes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Disciplina, Oferta, Turma

SUBTURMAS = ("A", "B")


def subturmas_de(disciplina: Disciplina) -> tuple[str | None, ...]:
    return SUBTURMAS if disciplina.divisao_turma else (None,)


def sincronizar_ofertas(db: Session, turma: Turma) -> list[Oferta]:
    """Garante uma `Oferta` por (turma, disciplina do periodo, subturma).

    Cria as que faltam e remove as que sobraram (ex.: a disciplina deixou de ter
    divisao de turma). Nao faz commit.
    """
    disciplinas = db.scalars(
        select(Disciplina).where(
            Disciplina.curso_id == turma.curso_id,
            Disciplina.periodo == turma.periodo,
        )
    ).all()

    esperadas = {(d.id, sub) for d in disciplinas for sub in subturmas_de(d)}
    atuais = {(o.disciplina_id, o.subturma): o for o in turma.ofertas}

    for chave in atuais.keys() - esperadas:
        db.delete(atuais[chave])
        turma.ofertas.remove(atuais[chave])

    criadas = []
    faltantes = sorted(esperadas - atuais.keys(), key=lambda k: (k[0], k[1] or ""))
    for disciplina_id, subturma in faltantes:
        oferta = Oferta(turma_id=turma.id, disciplina_id=disciplina_id, subturma=subturma)
        turma.ofertas.append(oferta)
        criadas.append(oferta)

    db.flush()
    return criadas


def blocos_de(aulas_semanais: int, tamanho_bloco: int) -> list[int]:
    """Decompoe a carga semanal de uma oferta em blocos (PLANO.md 5.2).

    >>> blocos_de(4, 2)
    [2, 2]
    >>> blocos_de(5, 2)
    [2, 2, 1]
    >>> blocos_de(3, 1)
    [1, 1, 1]
    """
    if aulas_semanais <= 0:
        return []
    tamanho = max(1, tamanho_bloco)
    inteiros, resto = divmod(aulas_semanais, tamanho)
    return [tamanho] * inteiros + ([resto] if resto else [])
