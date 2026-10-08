"""Onde um bloco de aulas pode comecar.

Fonte unica para o filtro `S(b)` descrito em PLANO.md 5.3. O solver usa isto para
**nao criar** as variaveis impossiveis (menos variaveis e' a alavanca principal de
desempenho) e a pre-validacao usa o mesmo codigo para dizer, antes de rodar o
solver, que uma oferta nao tem nenhum horario possivel — e por quê.

Se os dois divergissem, o solver acharia soluções que a pre-validacao declarou
inviaveis, ou o contrario.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.models import StatusDisponibilidade
from app.scheduling.domain import GradeState, OfertaInfo, SlotInfo
from app.schemas import ConfigRegras


@dataclass(frozen=True, slots=True)
class Recusa:
    """Por que um horario inicial foi descartado. Alimenta o diagnostico."""

    motivo: str
    detalhe: str


MOTIVOS = {
    "sem_sequencia": "não há aulas seguidas suficientes sem intervalo no meio",
    "dia_nao_usado": "o dia não é usado por esta unidade",
    "indisponivel": "o professor marcou o horário como indisponível",
    "outra_unidade": "o professor tem aula em outra unidade nesse horário",
    "deslocamento": "não há tempo de deslocamento suficiente entre as unidades",
}


def sequencia(estado: GradeState, inicio: SlotInfo, tamanho: int) -> list[SlotInfo] | None:
    """Os `tamanho` horarios geminados a partir de `inicio`, ou `None`.

    Exige mesmo dia, mesmo `bloco_id` e `ordem` consecutiva — e' assim que um
    bloco geminado nunca atravessa um intervalo.
    """
    do_modelo = {
        (s.dia, s.ordem): s
        for s in estado.slots.values()
        if s.modelo_turno_id == inicio.modelo_turno_id
    }
    janela = []
    for passo in range(tamanho):
        slot = do_modelo.get((inicio.dia, inicio.ordem + passo))
        if slot is None or slot.bloco_id != inicio.bloco_id:
            return None
        janela.append(slot)
    return janela


def _ocupacoes_por_professor_dia(estado: GradeState) -> dict[tuple[int, int], list]:
    indice: dict[tuple[int, int], list] = defaultdict(list)
    for o in estado.ocupacoes_externas:
        indice[(o.professor_id, o.dia)].append(o)
    return indice


def slots_iniciais(
    estado: GradeState,
    config: ConfigRegras,
    oferta: OfertaInfo,
    tamanho: int,
    *,
    recusas: dict[int, Recusa] | None = None,
) -> list[SlotInfo]:
    """Horarios em que um bloco de `tamanho` aulas desta oferta pode comecar.

    Passe `recusas` para receber, por `slot_id` descartado, o motivo — e' o que
    permite a mensagem "o Prof. X só está disponível às terças".
    """
    turma = estado.turma_da(oferta)
    professor_id = oferta.professor_id
    externas = _ocupacoes_por_professor_dia(estado)

    candidatos: list[SlotInfo] = []
    for inicio in estado.slots_do_modelo(turma.modelo_turno_id):
        recusa = _recusar(estado, config, inicio, tamanho, professor_id, externas)
        if recusa is None:
            candidatos.append(inicio)
        elif recusas is not None:
            recusas[inicio.id] = recusa
    return candidatos


def _recusar(
    estado: GradeState,
    config: ConfigRegras,
    inicio: SlotInfo,
    tamanho: int,
    professor_id: int | None,
    externas: dict[tuple[int, int], list],
) -> Recusa | None:
    if inicio.dia >= 5 and not config.usa_sabado:
        return Recusa("dia_nao_usado", MOTIVOS["dia_nao_usado"])

    janela = sequencia(estado, inicio, tamanho)
    if janela is None:
        return Recusa("sem_sequencia", MOTIVOS["sem_sequencia"])

    if professor_id is None:
        return None

    for slot in janela:
        if (
            estado.status_disponibilidade(professor_id, slot.id)
            == StatusDisponibilidade.INDISPONIVEL
        ):
            return Recusa("indisponivel", MOTIVOS["indisponivel"])

    inicio_min, fim_min = janela[0].inicio_min, janela[-1].fim_min
    folga = config.deslocamento_entre_unidades_min
    for outra in externas.get((professor_id, inicio.dia), ()):
        if inicio_min < outra.fim_min and outra.inicio_min < fim_min:
            return Recusa("outra_unidade", f"{MOTIVOS['outra_unidade']} ({outra.unidade_nome})")
        if folga:
            intervalo = (
                outra.inicio_min - fim_min
                if outra.inicio_min >= fim_min
                else inicio_min - outra.fim_min
            )
            if intervalo < folga:
                return Recusa("deslocamento", f"{MOTIVOS['deslocamento']} ({outra.unidade_nome})")
    return None
