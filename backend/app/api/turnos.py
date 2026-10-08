"""Modelos de turno.

Nao usa a fabrica CRUD porque o modelo e' sempre manipulado junto dos seus slots:
o editor da tela troca a semana inteira de uma vez.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app import schemas as s
from app.crud import HTTP_422, buscar_ou_404, gravando
from app.db import SessaoDb
from app.presets import PRESETS_TURNO, construir_modelo_turno

router = APIRouter(prefix="/modelos-turno", tags=["modelos-turno"])

DIAS = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")


def _validar_slots(slots: list[s.SlotEntrada]) -> None:
    """Coerencia da semana: ordens sequenciais por dia, sem sobreposicao de
    horario, e `bloco_id` agrupando apenas slots realmente contiguos."""
    por_dia: dict[int, list[s.SlotEntrada]] = {}
    for slot in slots:
        por_dia.setdefault(slot.dia_semana, []).append(slot)

    for dia, do_dia in por_dia.items():
        do_dia.sort(key=lambda x: x.ordem)
        ordens = [x.ordem for x in do_dia]
        if ordens != list(range(1, len(ordens) + 1)):
            raise HTTPException(
                HTTP_422,
                f"As aulas de {DIAS[dia]} precisam ser numeradas de 1 a {len(ordens)} "
                f"sem furos (recebido: {ordens}).",
            )
        for anterior, atual in zip(do_dia, do_dia[1:], strict=False):
            if atual.inicio < anterior.fim:
                raise HTTPException(
                    HTTP_422,
                    f"Na {DIAS[dia]}, a {atual.ordem}a aula ({atual.inicio:%H:%M}) comeca "
                    f"antes de a {anterior.ordem}a terminar ({anterior.fim:%H:%M}).",
                )
            # Slots do mesmo bloco sao geminados: nao pode haver intervalo entre eles.
            if atual.bloco_id == anterior.bloco_id and atual.inicio != anterior.fim:
                raise HTTPException(
                    HTTP_422,
                    f"Na {DIAS[dia]}, as aulas {anterior.ordem} e {atual.ordem} estao no mesmo "
                    f"bloco mas ha um intervalo entre {anterior.fim:%H:%M} e "
                    f"{atual.inicio:%H:%M}. Um bloco geminado nao atravessa intervalo.",
                )
            if atual.bloco_id != anterior.bloco_id and atual.bloco_id <= anterior.bloco_id:
                raise HTTPException(
                    HTTP_422,
                    f"Na {DIAS[dia]}, os blocos precisam ser numerados em ordem crescente.",
                )


def _com_slots(db: Session, id_: int) -> m.ModeloTurno:
    modelo = db.scalar(
        select(m.ModeloTurno)
        .options(selectinload(m.ModeloTurno.slots))
        .where(m.ModeloTurno.id == id_)
    )
    if modelo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Modelo de turno {id_} nao encontrado.")
    return modelo


@router.get("", response_model=list[s.ModeloTurno])
def listar(db: SessaoDb, unidade_id: int | None = None):
    consulta = select(m.ModeloTurno).options(selectinload(m.ModeloTurno.slots))
    if unidade_id is not None:
        consulta = consulta.where(m.ModeloTurno.unidade_id == unidade_id)
    return db.scalars(consulta.order_by(m.ModeloTurno.nome)).all()


@router.post("", response_model=s.ModeloTurno, status_code=status.HTTP_201_CREATED)
def criar(dados: s.ModeloTurnoEntrada, db: SessaoDb):
    buscar_ou_404(db, m.Unidade, dados.unidade_id, "Unidade")

    if dados.preset_origem and not dados.slots:
        preset = PRESETS_TURNO.get(dados.preset_origem)
        if preset is None:
            raise HTTPException(
                HTTP_422,
                f"Preset {dados.preset_origem!r} nao existe.",
            )
        modelo = construir_modelo_turno(preset, dados.unidade_id)
        modelo.nome = dados.nome
    else:
        _validar_slots(dados.slots)
        modelo = m.ModeloTurno(
            unidade_id=dados.unidade_id,
            nome=dados.nome,
            preset_origem=dados.preset_origem,
            dias_semana=sorted({x.dia_semana for x in dados.slots}),
            slots=[m.Slot(**x.model_dump()) for x in dados.slots],
        )

    with gravando(db, "Modelo de turno"):
        db.add(modelo)
    return _com_slots(db, modelo.id)


@router.get("/{id_}", response_model=s.ModeloTurno)
def ler(id_: int, db: SessaoDb):
    return _com_slots(db, id_)


@router.put("/{id_}", response_model=s.ModeloTurno)
def substituir(id_: int, dados: s.ModeloTurnoEntrada, db: SessaoDb):
    """Grava o modelo e **substitui a semana inteira**.

    Slots referenciados por alocacoes nao podem sumir: a grade perderia o horario.
    """
    modelo = _com_slots(db, id_)
    _validar_slots(dados.slots)

    novos = {(x.dia_semana, x.ordem): x for x in dados.slots}
    em_uso = {
        linha[0]
        for linha in db.execute(
            select(m.Alocacao.slot_id).where(m.Alocacao.slot_id.in_([x.id for x in modelo.slots]))
        )
    }

    # A checagem de slot em uso roda antes de qualquer escrita, para a requisicao
    # falhar inteira em vez de deixar a semana pela metade.
    sobrando = [
        slot
        for slot in modelo.slots
        if (slot.dia_semana, slot.ordem) not in novos and slot.id in em_uso
    ]
    if sobrando:
        slot = sobrando[0]
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A {slot.ordem}a aula de {DIAS[slot.dia_semana]} ja tem aulas alocadas em "
            "alguma grade. Apague ou regenere a grade antes de remover esse horario.",
        )

    with gravando(db, "Modelo de turno"):
        for slot in list(modelo.slots):
            entrada = novos.pop((slot.dia_semana, slot.ordem), None)
            if entrada is None:
                modelo.slots.remove(slot)
            else:
                slot.inicio, slot.fim, slot.bloco_id = (
                    entrada.inicio,
                    entrada.fim,
                    entrada.bloco_id,
                )

        for entrada in novos.values():
            modelo.slots.append(m.Slot(**entrada.model_dump()))

        modelo.nome = dados.nome
        modelo.preset_origem = dados.preset_origem
        modelo.dias_semana = sorted({x.dia_semana for x in dados.slots})

    return _com_slots(db, id_)


@router.delete("/{id_}", status_code=status.HTTP_204_NO_CONTENT)
def apagar(id_: int, db: SessaoDb):
    modelo = _com_slots(db, id_)
    turmas = db.scalar(select(m.Turma.periodo).where(m.Turma.modelo_turno_id == id_).limit(1))
    if turmas:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"O modelo {modelo.nome!r} esta em uso por turmas. Mude o turno delas antes.",
        )
    with gravando(db, "Modelo de turno"):
        db.delete(modelo)
