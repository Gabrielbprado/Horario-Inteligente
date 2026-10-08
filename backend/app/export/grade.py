"""Reorganiza a `VisaoGrade` no formato de quadro que vai para o papel.

A tela compara turmas lado a lado (colunas = turmas). O que se entrega na mão de
uma turma ou de um professor é o outro corte: **dias nas colunas, horários nas
linhas** — um quadro por turma, um por professor. PDF e Excel partem daqui, para
não existirem duas ideias diferentes de "a grade da turma X".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

from app import schemas as s
from app.export.cores import cores_disciplina
from app.scheduling.domain import DIAS


@dataclass(slots=True)
class Aula:
    """Uma célula do quadro, já com o texto pronto."""

    sigla: str
    nome: str
    linhas: tuple[str, ...]
    """Detalhes sob a sigla: professor/turma e sala, conforme o corte."""
    fundo: str
    borda: str
    texto: str
    fixada: bool
    remota: bool


@dataclass(slots=True)
class Quadro:
    """A grade de uma turma, de um professor ou de uma sala."""

    id: int
    titulo: str
    subtitulo: str | None
    dias: list[int]
    faixas: list[tuple[time, time]]
    aulas: dict[tuple[int, int], Aula] = field(default_factory=dict)
    """(índice da faixa, dia) -> aula."""

    def aula(self, linha: int, dia: int) -> Aula | None:
        return self.aulas.get((linha, dia))

    @property
    def vazio(self) -> bool:
        return not self.aulas


def _detalhes(celula: s.CelulaGrade, tipo: str) -> tuple[str, ...]:
    """O que interessa saber depende de quem está lendo o quadro."""
    sala = celula.espaco_nome or ("remota" if celula.remota else "sem sala")
    turma = celula.turma_rotulo + (f" · {celula.subturma}" if celula.subturma else "")
    if tipo == "turma":
        return (celula.professor_nome, sala)
    if tipo == "professor":
        return (turma, sala)
    return (turma, celula.professor_nome)


def _chave_da_coluna(celula: s.CelulaGrade, tipo: str) -> int | None:
    if tipo == "turma":
        return celula.turma_id
    if tipo == "professor":
        return celula.professor_id
    return celula.espaco_id


def _faixas_do_turno(visao: s.VisaoGrade, modelos: set[int]) -> list[tuple[time, time]]:
    """Todas as faixas dos turnos indicados, tenham aula ou não.

    Tirar as faixas só das aulas da coluna esconderia exatamente o que o quadro
    precisa mostrar: o horário vago. A 1ª série do ETIM tem aula às 07h50 e às
    09h50, e é a linha vazia das 08h40 que informa a janela.
    """
    return sorted(
        {(slot.inicio, slot.fim) for slot in visao.slots if slot.modelo_turno_id in modelos}
    )


def montar_quadros(visao: s.VisaoGrade) -> list[Quadro]:
    """Um quadro por coluna da visão, na mesma ordem que a tela usa."""
    tipo = visao.tipo
    dias = sorted({h.dia for h in visao.horarios})

    por_coluna: dict[int, list[s.CelulaGrade]] = {}
    for celula in visao.celulas:
        chave = _chave_da_coluna(celula, tipo)
        if chave is not None:
            por_coluna.setdefault(chave, []).append(celula)

    quadros = []
    for coluna in visao.colunas:
        celulas = por_coluna.get(coluna.id, [])
        # A turma tem um turno declarado; o professor e a sala herdam os turnos
        # em que de fato têm aula. Um docente só do noturno não ganha a manhã
        # inteira em branco — o mesmo critério da tela (DECISOES D68).
        modelos = (
            {coluna.modelo_turno_id}
            if coluna.modelo_turno_id is not None
            else {c.modelo_turno_id for c in celulas}
        )
        faixas = _faixas_do_turno(visao, modelos)
        indice = {faixa: i for i, faixa in enumerate(faixas)}

        quadro = Quadro(
            id=coluna.id,
            titulo=coluna.titulo,
            subtitulo=coluna.subtitulo,
            dias=dias,
            faixas=faixas,
        )
        for celula in celulas:
            fundo, borda, texto = cores_disciplina(celula.disciplina_sigla)
            quadro.aulas[(indice[(celula.inicio, celula.fim)], celula.dia)] = Aula(
                sigla=celula.disciplina_sigla,
                nome=celula.disciplina_nome,
                linhas=_detalhes(celula, tipo),
                fundo=fundo,
                borda=borda,
                texto=texto,
                fixada=celula.fixada,
                remota=celula.remota,
            )
        quadros.append(quadro)
    return quadros


def rotulo_dia(dia: int) -> str:
    return DIAS[dia].capitalize()


def faixa_texto(inicio: time, fim: time) -> str:
    return f"{inicio:%H:%M}–{fim:%H:%M}"
