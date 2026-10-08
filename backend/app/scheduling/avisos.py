"""Avisos de uma grade pronta.

Junta o que o validador unico encontrou com a analise de **prioridade de
horario** (spec 5.7): quando dois docentes marcaram o mesmo horario como
preferencial e so' um ficou com ele, o aviso diz quem levou, por que, e onde o
outro acabou.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app import models as m
from app.scheduling.assignment import chave_classificacao, criterio_decisivo
from app.scheduling.domain import GradeState, Violacao
from app.scheduling.validator import validar
from app.schemas import ConfigRegras


def prioridade_de_horario(estado: GradeState, config: ConfigRegras) -> list[Violacao]:
    """Disputas por horario resolvidas pela classificacao docente."""
    preferem: dict[int, list[int]] = defaultdict(list)
    for (professor_id, slot_id), status in estado.disponibilidade.items():
        if status == m.StatusDisponibilidade.PREFERENCIAL and slot_id in estado.slots:
            preferem[slot_id].append(professor_id)

    ocupados: dict[int, set[int]] = defaultdict(set)
    for a in estado.alocacoes:
        ocupados[a.slot_id].add(a.professor_id)

    onde_ficou: dict[int, list[int]] = defaultdict(list)
    for a in estado.alocacoes:
        if a.slot_id in estado.slots:
            onde_ficou[a.professor_id].append(a.slot_id)

    avisos: list[Violacao] = []
    ja_vistos: set[tuple[int, int, int]] = set()

    for slot_id, interessados in sorted(preferem.items()):
        if len(interessados) < 2:
            continue
        vencedores = [p for p in interessados if p in ocupados[slot_id]]
        perdedores = [p for p in interessados if p not in ocupados[slot_id]]
        if not vencedores or not perdedores:
            continue

        for perdedor_id in sorted(perdedores):
            perdedor = estado.vinculos.get(perdedor_id)
            if perdedor is None:
                continue
            melhores = [
                estado.vinculos[v]
                for v in vencedores
                if v in estado.vinculos
                and chave_classificacao(estado.vinculos[v], config)
                < chave_classificacao(perdedor, config)
            ]
            if not melhores:
                continue
            vencedor = min(melhores, key=lambda v: chave_classificacao(v, config))

            chave = (slot_id, vencedor.professor_id, perdedor_id)
            if chave in ja_vistos:
                continue
            ja_vistos.add(chave)

            destino = sorted({estado.slots[s].rotulo for s in onde_ficou.get(perdedor_id, [])})
            complemento = (
                f" {estado.nome_professor(perdedor_id)} ficou com {', '.join(destino[:2])}."
                if destino
                else f" {estado.nome_professor(perdedor_id)} não recebeu aula nesse dia."
            )
            avisos.append(
                Violacao(
                    "PRIORIDADE_DE_HORARIO",
                    m.Severidade.ALERTA,
                    f"{estado.nome_professor(vencedor.professor_id)} e "
                    f"{estado.nome_professor(perdedor_id)} queriam "
                    f"{estado.slots[slot_id].rotulo}. A prioridade ficou com "
                    f"{estado.nome_professor(vencedor.professor_id)} por "
                    f"{criterio_decisivo(vencedor, perdedor, config)} "
                    f"(Portaria CETEC 1.263/2017, art. 7º).{complemento}",
                    {
                        "slot_id": slot_id,
                        "vencedor_id": vencedor.professor_id,
                        "perdedor_id": perdedor_id,
                    },
                )
            )
    return avisos


def avisos_da_grade(estado: GradeState, config: ConfigRegras) -> list[Violacao]:
    """Tudo que o usuario precisa ver sobre uma grade recem-gerada."""
    return validar(estado, config) + prioridade_de_horario(estado, config)


# ------------------------------------------------------------------ persistencia

EXIGEM_CIENCIA = {"PRIORIDADE_DE_HORARIO", "PRIORIDADE_NA_ATRIBUICAO"}
"""Avisos que a spec manda o usuario reconhecer explicitamente (secao 4.10)."""


def gravar_avisos(db: Session, grade_id: int, violacoes: list[Violacao]) -> list[m.Aviso]:
    """Substitui os avisos da grade, preservando a ciencia ja' registrada.

    Regenerar a grade nao deve apagar um "estou ciente" de um aviso que continua
    valendo — seria fazer o usuario reconhecer a mesma coisa de novo.
    """
    anteriores = {
        (a.tipo, a.mensagem): a for a in db.query(m.Aviso).filter(m.Aviso.grade_id == grade_id)
    }
    for aviso in anteriores.values():
        db.delete(aviso)
    db.flush()

    criados = []
    for v in violacoes:
        antigo = anteriores.get((v.tipo, v.mensagem))
        aviso = m.Aviso(
            grade_id=grade_id,
            tipo=v.tipo,
            severidade=v.severidade,
            mensagem=v.mensagem,
            entidades=v.entidades,
            ciente=antigo.ciente if antigo else False,
            ciente_por=antigo.ciente_por if antigo else None,
            ciente_em=antigo.ciente_em if antigo else None,
        )
        db.add(aviso)
        criados.append(aviso)
    db.flush()
    return criados


def pendencias_para_publicar(avisos: list[m.Aviso]) -> list[str]:
    """Motivos que impedem a publicacao (secao 4.10 da spec)."""
    motivos = []
    bloqueantes = [a for a in avisos if a.severidade == m.Severidade.BLOQUEANTE]
    if bloqueantes:
        motivos.append(f"{len(bloqueantes)} aviso(s) bloqueante(s) precisam ser resolvidos antes.")
    sem_ciencia = [a for a in avisos if a.severidade == m.Severidade.ALERTA and not a.ciente]
    if sem_ciencia:
        motivos.append(f"{len(sem_ciencia)} alerta(s) ainda sem “Estou ciente”.")
    return motivos


def marcar_ciente(aviso: m.Aviso, autor: str | None) -> None:
    aviso.ciente = True
    aviso.ciente_por = autor or "usuário"
    aviso.ciente_em = datetime.now()
