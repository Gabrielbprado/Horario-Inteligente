"""O unico caminho de escrita em `Alocacao`.

Invariante do PLANO.md: nada altera a grade sem passar por aqui, e aqui sempre
se roda o validador antes de gravar e se registra `HistoricoAlteracao`. Vale
para o arrastar-e-soltar, para as ferramentas do chatbot e para o desfazer.

A unidade de edicao e' o **bloco**, nao a aula solta: arrastar uma disciplina de
4 aulas geminadas move as duas aulas juntas.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.scheduling.avisos import avisos_da_grade, gravar_avisos
from app.scheduling.candidatos import sequencia
from app.scheduling.domain import AlocacaoInfo, GradeState, SlotInfo, Violacao
from app.scheduling.validator import ORDEM_SEVERIDADE, validar
from app.schemas import ConfigRegras


class MovimentoInvalido(Exception):
    """O movimento nem chega a ser avaliado: o destino nao existe como bloco."""


@dataclass(frozen=True, slots=True)
class Bloco:
    oferta_id: int
    bloco_idx: int


@dataclass(frozen=True, slots=True)
class Alteracao:
    alocacao_id: int
    antes: dict
    depois: dict

    def invertida(self) -> Alteracao:
        return Alteracao(self.alocacao_id, self.depois, self.antes)


def _efetivas(alteracoes: list[Alteracao]) -> list[Alteracao]:
    """Descarta o que nao muda nada.

    Soltar a aula no lugar onde ela ja' estava nao e' uma alteracao: gravaria um
    passo inutil no historico e um "desfazer" que nao desfaz nada.
    """
    return [a for a in alteracoes if a.antes != a.depois]


@dataclass(slots=True)
class Resultado:
    """O que um movimento faria (ou fez) com a grade."""

    alteracoes: list[Alteracao] = field(default_factory=list)
    violacoes: list[Violacao] = field(default_factory=list)
    descricao: str = ""

    @property
    def severidade(self) -> m.Severidade | None:
        """A pior severidade introduzida. `None` = movimento limpo."""
        if not self.violacoes:
            return None
        return min(self.violacoes, key=lambda v: ORDEM_SEVERIDADE[v.severidade]).severidade

    @property
    def permitido(self) -> bool:
        return self.severidade != m.Severidade.BLOQUEANTE


# ------------------------------------------------------------------ consultas


def aulas_do_bloco(estado: GradeState, bloco: Bloco) -> list[AlocacaoInfo]:
    return sorted(
        (
            a
            for a in estado.alocacoes
            if a.oferta_id == bloco.oferta_id and a.bloco_idx == bloco.bloco_idx
        ),
        key=lambda a: estado.slots[a.slot_id].ordem if a.slot_id in estado.slots else 0,
    )


def _destino(estado: GradeState, bloco: Bloco, slot_inicial: int) -> list[SlotInfo]:
    aulas = aulas_do_bloco(estado, bloco)
    if not aulas:
        raise MovimentoInvalido("Esse bloco não existe nesta grade.")
    inicio = estado.slots.get(slot_inicial)
    if inicio is None:
        raise MovimentoInvalido("O horário de destino não existe.")
    janela = sequencia(estado, inicio, len(aulas))
    if janela is None:
        raise MovimentoInvalido(
            f"Não cabem {len(aulas)} aulas geminadas a partir de {inicio.rotulo}: "
            "não há horários seguidos suficientes sem intervalo no meio."
        )
    return janela


def _espaco_para(
    estado: GradeState, bloco: Bloco, janela: list[SlotInfo], atual: int | None
) -> int | None:
    """Espaco a usar no destino.

    Mantem o atual se ele estiver livre la'; senao procura outro compativel e
    livre. Sem nenhum, devolve o atual e deixa o validador acusar o choque — e'
    informacao melhor do que mover para lugar nenhum.
    """
    oferta = estado.ofertas[bloco.oferta_id]
    disciplina = estado.disciplina_da(oferta)
    if disciplina.remota:
        return None

    da_propria = {a.id for a in aulas_do_bloco(estado, bloco)}
    alvo = {s.id for s in janela}
    ocupados = {
        a.espaco_id
        for a in estado.alocacoes
        if a.slot_id in alvo and a.espaco_id is not None and a.id not in da_propria
    }
    if atual is not None and atual not in ocupados:
        return atual

    turma = estado.turma_da(oferta)
    alunos = turma.qtd_alunos if oferta.subturma is None else -(-turma.qtd_alunos // 2)
    livres = [
        e.id
        for e in sorted(estado.espacos.values(), key=lambda e: e.id)
        if e.id not in ocupados and e.atende(disciplina, alunos)
    ]
    return livres[0] if livres else atual


# ------------------------------------------------------------------ simulacao


def _aplicar_em_memoria(estado: GradeState, alteracoes: list[Alteracao]) -> GradeState:
    por_id = {a.alocacao_id: a for a in alteracoes}
    novas = [replace(a, **por_id[a.id].depois) if a.id in por_id else a for a in estado.alocacoes]
    return replace(estado, alocacoes=novas)


def _novas_violacoes(
    estado: GradeState, config: ConfigRegras, alteracoes: list[Alteracao]
) -> list[Violacao]:
    """So' o que o movimento **introduz**.

    A grade pode já ter avisos; repetir os antigos a cada arrasto faria o
    usuário achar que ele mesmo causou tudo.
    """
    antes = {(v.tipo, v.mensagem) for v in validar(estado, config)}
    depois = validar(_aplicar_em_memoria(estado, alteracoes), config)
    return [v for v in depois if (v.tipo, v.mensagem) not in antes]


def simular_movimento(
    estado: GradeState,
    config: ConfigRegras,
    bloco: Bloco,
    slot_inicial: int,
    espaco_id: int | None = None,
    *,
    manter_espaco: bool = False,
) -> Resultado:
    """O que aconteceria se o bloco fosse para este horário. Não grava nada."""
    janela = _destino(estado, bloco, slot_inicial)
    aulas = aulas_do_bloco(estado, bloco)
    atual = aulas[0].espaco_id
    destino_espaco = (
        espaco_id
        if espaco_id is not None
        else (atual if manter_espaco else _espaco_para(estado, bloco, janela, atual))
    )

    alteracoes = [
        Alteracao(
            alocacao_id=aula.id,
            antes={"slot_id": aula.slot_id, "espaco_id": aula.espaco_id},
            depois={"slot_id": slot.id, "espaco_id": destino_espaco},
        )
        for aula, slot in zip(aulas, janela, strict=True)
    ]
    alteracoes = _efetivas(alteracoes)
    return Resultado(
        alteracoes=alteracoes,
        violacoes=_novas_violacoes(estado, config, alteracoes),
        descricao=(
            f"{estado.rotulo_oferta(estado.ofertas[bloco.oferta_id])} "
            f"de {estado.slots[aulas[0].slot_id].rotulo} para {janela[0].rotulo}"
        ),
    )


def simular_troca(estado: GradeState, config: ConfigRegras, a: Bloco, b: Bloco) -> Resultado:
    """Troca dois blocos de lugar. Só faz sentido com blocos do mesmo tamanho."""
    aulas_a, aulas_b = aulas_do_bloco(estado, a), aulas_do_bloco(estado, b)
    if not aulas_a or not aulas_b:
        raise MovimentoInvalido("Um dos blocos não existe nesta grade.")
    if len(aulas_a) != len(aulas_b):
        raise MovimentoInvalido(
            f"Não dá para trocar um bloco de {len(aulas_a)} aulas por um de "
            f"{len(aulas_b)}: eles ocupam quantidades diferentes de horários."
        )

    alteracoes = [
        Alteracao(
            alocacao_id=origem.id,
            antes={"slot_id": origem.slot_id, "espaco_id": origem.espaco_id},
            depois={"slot_id": destino.slot_id, "espaco_id": origem.espaco_id},
        )
        for origem, destino in [
            *zip(aulas_a, aulas_b, strict=True),
            *zip(aulas_b, aulas_a, strict=True),
        ]
    ]
    alteracoes = _efetivas(alteracoes)
    return Resultado(
        alteracoes=alteracoes,
        violacoes=_novas_violacoes(estado, config, alteracoes),
        descricao=(
            f"trocar {estado.rotulo_oferta(estado.ofertas[a.oferta_id])} com "
            f"{estado.rotulo_oferta(estado.ofertas[b.oferta_id])}"
        ),
    )


def destinos_possiveis(
    estado: GradeState, config: ConfigRegras, bloco: Bloco
) -> dict[int, Resultado]:
    """Avalia **todos** os horários de destino de uma vez.

    A tela pinta a semana inteira ao começar o arrasto (verde/amarelo/vermelho)
    sem uma requisição por célula sobrevoada.
    """
    oferta = estado.ofertas.get(bloco.oferta_id)
    if oferta is None:
        raise MovimentoInvalido("Esse bloco não existe nesta grade.")
    turma = estado.turma_da(oferta)

    resultados: dict[int, Resultado] = {}
    for slot in estado.slots_do_modelo(turma.modelo_turno_id):
        try:
            resultados[slot.id] = simular_movimento(estado, config, bloco, slot.id)
        except MovimentoInvalido:
            continue
    return resultados


# ------------------------------------------------------------------ gravacao


def _gravar(
    db: Session,
    grade: m.Grade,
    estado: GradeState,
    config: ConfigRegras,
    resultado: Resultado,
    *,
    origem: m.OrigemAlteracao,
    autor: str | None,
    tipo: str,
) -> Resultado:
    if not resultado.alteracoes:
        return resultado  # movimento nulo: nada a gravar nem a desfazer

    por_id = {
        a.id: a
        for a in db.scalars(
            select(m.Alocacao).where(
                m.Alocacao.id.in_([x.alocacao_id for x in resultado.alteracoes])
            )
        )
    }
    for alteracao in resultado.alteracoes:
        alvo = por_id.get(alteracao.alocacao_id)
        if alvo is None:
            raise MovimentoInvalido("Uma das aulas do movimento não existe mais.")
        for campo, valor in alteracao.depois.items():
            setattr(alvo, campo, valor)
    db.flush()

    db.add(
        m.HistoricoAlteracao(
            grade_id=grade.id,
            origem=origem,
            autor=autor,
            diff={
                "tipo": tipo,
                "descricao": resultado.descricao,
                "alteracoes": [
                    {"alocacao_id": x.alocacao_id, "antes": x.antes, "depois": x.depois}
                    for x in resultado.alteracoes
                ],
            },
        )
    )

    novo_estado = _aplicar_em_memoria(estado, resultado.alteracoes)
    gravar_avisos(db, grade.id, avisos_da_grade(novo_estado, config))
    _atualizar_status(db, grade)
    return resultado


def _atualizar_status(db: Session, grade: m.Grade) -> None:
    """Editar a mao tira a grade de PUBLICADA: o que foi publicado mudou."""
    avisos = db.scalars(select(m.Aviso).where(m.Aviso.grade_id == grade.id)).all()
    pendentes = any(a.severidade == m.Severidade.ALERTA and not a.ciente for a in avisos) or any(
        a.severidade == m.Severidade.BLOQUEANTE for a in avisos
    )
    grade.status = m.StatusGrade.AGUARDANDO_CIENCIA if pendentes else m.StatusGrade.RASCUNHO


def mover(
    db: Session,
    grade: m.Grade,
    estado: GradeState,
    config: ConfigRegras,
    bloco: Bloco,
    slot_inicial: int,
    espaco_id: int | None = None,
    *,
    origem: m.OrigemAlteracao = m.OrigemAlteracao.MANUAL,
    autor: str | None = None,
    forcar: bool = False,
) -> Resultado:
    """Move o bloco. Recusa se o movimento criar violação bloqueante, a menos
    que `forcar` — e aí o aviso fica gravado e impede a publicação."""
    resultado = simular_movimento(estado, config, bloco, slot_inicial, espaco_id)
    if not resultado.permitido and not forcar:
        return resultado
    return _gravar(db, grade, estado, config, resultado, origem=origem, autor=autor, tipo="mover")


def trocar(
    db: Session,
    grade: m.Grade,
    estado: GradeState,
    config: ConfigRegras,
    a: Bloco,
    b: Bloco,
    *,
    origem: m.OrigemAlteracao = m.OrigemAlteracao.MANUAL,
    autor: str | None = None,
    forcar: bool = False,
) -> Resultado:
    resultado = simular_troca(estado, config, a, b)
    if not resultado.permitido and not forcar:
        return resultado
    return _gravar(db, grade, estado, config, resultado, origem=origem, autor=autor, tipo="trocar")


def fixar(
    db: Session,
    grade: m.Grade,
    estado: GradeState,
    config: ConfigRegras,
    bloco: Bloco,
    fixada: bool,
    *,
    origem: m.OrigemAlteracao = m.OrigemAlteracao.MANUAL,
    autor: str | None = None,
) -> Resultado:
    """Liga ou desliga o cadeado do bloco. Não muda horário, então não valida."""
    aulas = aulas_do_bloco(estado, bloco)
    if not aulas:
        raise MovimentoInvalido("Esse bloco não existe nesta grade.")

    resultado = Resultado(
        alteracoes=_efetivas(
            [
                Alteracao(alocacao_id=a.id, antes={"fixada": a.fixada}, depois={"fixada": fixada})
                for a in aulas
            ]
        ),
        descricao=(
            f"{'fixar' if fixada else 'liberar'} "
            f"{estado.rotulo_oferta(estado.ofertas[bloco.oferta_id])}"
        ),
    )
    return _gravar(db, grade, estado, config, resultado, origem=origem, autor=autor, tipo="fixar")


def desfazer(
    db: Session,
    grade: m.Grade,
    estado: GradeState,
    config: ConfigRegras,
    passos: int = 1,
    *,
    autor: str | None = None,
) -> list[str]:
    """Reverte os últimos `passos` registros do histórico, do mais novo para o
    mais antigo. Devolve a descrição do que foi desfeito."""
    pendentes = db.scalars(
        select(m.HistoricoAlteracao)
        .where(
            m.HistoricoAlteracao.grade_id == grade.id,
            m.HistoricoAlteracao.desfeito.is_(False),
        )
        .order_by(m.HistoricoAlteracao.id.desc())
        .limit(max(1, passos))
    ).all()

    if not pendentes:
        return []

    desfeitos = []
    estado_atual = estado
    for registro in pendentes:
        alteracoes = [
            Alteracao(alocacao_id=x["alocacao_id"], antes=x["depois"], depois=x["antes"])
            for x in registro.diff.get("alteracoes", [])
        ]
        por_id = {
            a.id: a
            for a in db.scalars(
                select(m.Alocacao).where(m.Alocacao.id.in_([x.alocacao_id for x in alteracoes]))
            )
        }
        for alteracao in alteracoes:
            alvo = por_id.get(alteracao.alocacao_id)
            if alvo is None:
                continue  # a aula sumiu numa regeneracao; o resto do passo vale
            for campo, valor in alteracao.depois.items():
                setattr(alvo, campo, valor)
        registro.desfeito = True
        desfeitos.append(registro.diff.get("descricao", "alteração"))
        estado_atual = _aplicar_em_memoria(estado_atual, alteracoes)

    db.flush()
    gravar_avisos(db, grade.id, avisos_da_grade(estado_atual, config))
    _atualizar_status(db, grade)
    return desfeitos


def substituir_alocacoes(
    db: Session,
    grade: m.Grade,
    estado: GradeState,
    config: ConfigRegras,
    novas: list[tuple[int, int, int, int | None, int]],
    descricao: str,
    *,
    origem: m.OrigemAlteracao = m.OrigemAlteracao.SOLVER,
    autor: str | None = None,
) -> Resultado:
    """Troca as posicoes de varias aulas de uma vez, como faz a regeneracao
    parcial. `novas` sao tuplas `(oferta_id, bloco_idx, slot_id, espaco_id, ordem)`.

    Casa cada posicao nova com uma linha existente do mesmo bloco, para o
    historico continuar sendo um diff de `Alocacao` e o desfazer funcionar.
    """
    por_bloco: dict[tuple[int, int], list[AlocacaoInfo]] = {}
    for a in estado.alocacoes:
        por_bloco.setdefault((a.oferta_id, a.bloco_idx), []).append(a)
    for aulas in por_bloco.values():
        aulas.sort(key=lambda a: estado.slots[a.slot_id].ordem if a.slot_id in estado.slots else 0)

    destinos: dict[tuple[int, int], list[tuple[int, int | None]]] = {}
    for oferta_id, bloco_idx, slot_id, espaco_id, _ordem in sorted(novas, key=lambda x: x[4]):
        destinos.setdefault((oferta_id, bloco_idx), []).append((slot_id, espaco_id))

    alteracoes: list[Alteracao] = []
    for chave, posicoes in sorted(destinos.items()):
        atuais = por_bloco.get(chave, [])
        if len(atuais) != len(posicoes):
            raise MovimentoInvalido(
                "A nova grade tem um número de aulas diferente do atual neste bloco."
            )
        for aula, (slot_id, espaco_id) in zip(atuais, posicoes, strict=True):
            alteracoes.append(
                Alteracao(
                    alocacao_id=aula.id,
                    antes={"slot_id": aula.slot_id, "espaco_id": aula.espaco_id},
                    depois={"slot_id": slot_id, "espaco_id": espaco_id},
                )
            )

    resultado = Resultado(
        alteracoes=_efetivas(alteracoes),
        violacoes=_novas_violacoes(estado, config, alteracoes),
        descricao=descricao,
    )
    return _gravar(
        db, grade, estado, config, resultado, origem=origem, autor=autor, tipo="regenerar"
    )
