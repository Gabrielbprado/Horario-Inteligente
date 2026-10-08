"""Propostas de alteração vindas do chat.

Regra da especificação (6.3): **toda mutação pedida ao assistente vira uma
proposta**, mostrada como cartão "antes → depois" com os avisos que ela cria e
os botões Aplicar / Descartar. O modelo nunca grava nada; ele só descreve o que
quer, e a aplicação passa pelo mesmo `app/scheduling/apply.py` de sempre.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app import models as m
from app.scheduling import apply
from app.scheduling.domain import GradeState, Violacao
from app.schemas import ConfigRegras

MAX_PROPOSTAS = 200


@dataclass(frozen=True, slots=True)
class Mudanca:
    """Uma linha do cartão "antes → depois"."""

    rotulo: str
    antes: str
    depois: str


@dataclass(slots=True)
class Proposta:
    id: str
    grade_id: int
    tipo: str
    """mover | trocar | fixar | disponibilidade | regenerar | desfazer"""
    descricao: str
    argumentos: dict[str, Any]
    mudancas: list[Mudanca] = field(default_factory=list)
    violacoes: list[Violacao] = field(default_factory=list)
    permitido: bool = True
    aplicada: bool = False
    descartada: bool = False
    criada_em: datetime = field(default_factory=datetime.now)

    @property
    def pendente(self) -> bool:
        return not self.aplicada and not self.descartada

    def resumo(self) -> str:
        """O texto que volta para o modelo. Curto de propósito: o cartão
        completo quem mostra é a tela."""
        linhas = [
            f"{mudanca.rotulo}: {mudanca.antes} -> {mudanca.depois}"
            for mudanca in self.mudancas[:6]
        ]
        if len(self.mudancas) > 6:
            linhas.append(f"... e mais {len(self.mudancas) - 6} alteração(ões)")
        avisos = [f"{v.severidade.value}: {v.mensagem}" for v in self.violacoes[:4]]
        partes = [f"proposta {self.id} criada: {self.descricao}", *linhas]
        if avisos:
            partes.append("Avisos que isso cria: " + " | ".join(avisos))
        if not self.permitido:
            partes.append(
                "ATENÇÃO: viola uma regra rígida. Diga isso ao usuário; "
                "ele decide se aplica mesmo assim."
            )
        partes.append("Aguardando o usuário clicar em Aplicar.")
        return "\n".join(partes)


class _Registro:
    def __init__(self, maximo: int = MAX_PROPOSTAS):
        self._itens: OrderedDict[str, Proposta] = OrderedDict()
        self._lock = threading.Lock()
        self._maximo = maximo

    def criar(self, **kwargs) -> Proposta:
        proposta = Proposta(id=uuid4().hex[:10], **kwargs)
        with self._lock:
            self._itens[proposta.id] = proposta
            while len(self._itens) > self._maximo:
                self._itens.popitem(last=False)
        return proposta

    def por_id(self, proposta_id: str) -> Proposta | None:
        with self._lock:
            return self._itens.get(proposta_id)

    def da_grade(self, grade_id: int) -> list[Proposta]:
        with self._lock:
            return [p for p in self._itens.values() if p.grade_id == grade_id]


REGISTRO = _Registro()


# --------------------------------------------------------------- construcao


def _rotulo_slot(estado: GradeState, slot_id: int | None) -> str:
    slot = estado.slots.get(slot_id) if slot_id is not None else None
    return slot.rotulo if slot else "—"


def _rotulo_espaco(estado: GradeState, espaco_id: int | None) -> str:
    espaco = estado.espacos.get(espaco_id) if espaco_id is not None else None
    return espaco.nome if espaco else "sem sala"


def de_resultado(
    estado: GradeState,
    grade_id: int,
    tipo: str,
    resultado: apply.Resultado,
    argumentos: dict,
) -> Proposta:
    """Transforma o que `apply` simulou num cartão "antes → depois"."""
    por_id = {a.id: a for a in estado.alocacoes}
    mudancas = []
    for alteracao in resultado.alteracoes:
        aula = por_id.get(alteracao.alocacao_id)
        rotulo = (
            estado.rotulo_oferta(estado.ofertas[aula.oferta_id])
            if aula and aula.oferta_id in estado.ofertas
            else f"aula {alteracao.alocacao_id}"
        )
        if "slot_id" in alteracao.depois:
            mudancas.append(
                Mudanca(
                    rotulo=rotulo,
                    antes=f"{_rotulo_slot(estado, alteracao.antes.get('slot_id'))}"
                    f" · {_rotulo_espaco(estado, alteracao.antes.get('espaco_id'))}",
                    depois=f"{_rotulo_slot(estado, alteracao.depois.get('slot_id'))}"
                    f" · {_rotulo_espaco(estado, alteracao.depois.get('espaco_id'))}",
                )
            )
        elif "fixada" in alteracao.depois:
            mudancas.append(
                Mudanca(
                    rotulo=rotulo,
                    antes="livre" if not alteracao.antes.get("fixada") else "fixada",
                    depois="fixada" if alteracao.depois.get("fixada") else "livre",
                )
            )

    return REGISTRO.criar(
        grade_id=grade_id,
        tipo=tipo,
        descricao=resultado.descricao,
        argumentos=argumentos,
        mudancas=mudancas,
        violacoes=resultado.violacoes,
        permitido=resultado.permitido,
    )


# ---------------------------------------------------------------- aplicacao


class PropostaInvalida(Exception):
    pass


def aplicar(
    db: Session,
    proposta: Proposta,
    estado: GradeState,
    config: ConfigRegras,
    grade: m.Grade,
    *,
    autor: str | None = None,
    forcar: bool = False,
) -> apply.Resultado:
    """Executa a proposta pelo caminho normal de escrita, com origem CHAT."""
    if not proposta.pendente:
        raise PropostaInvalida(
            "Esta proposta já foi aplicada ou descartada; peça outra ao assistente."
        )
    if not proposta.permitido and not forcar:
        raise PropostaInvalida(
            "A proposta viola uma regra rígida. Confirme que quer aplicar mesmo assim."
        )

    args = proposta.argumentos
    comum = {"origem": m.OrigemAlteracao.CHAT, "autor": autor or "assistente"}

    if proposta.tipo == "mover":
        resultado = apply.mover(
            db,
            grade,
            estado,
            config,
            apply.Bloco(args["oferta_id"], args["bloco_idx"]),
            args["slot_inicial"],
            args.get("espaco_id"),
            forcar=True,
            **comum,
        )
    elif proposta.tipo == "trocar":
        resultado = apply.trocar(
            db,
            grade,
            estado,
            config,
            apply.Bloco(args["a"]["oferta_id"], args["a"]["bloco_idx"]),
            apply.Bloco(args["b"]["oferta_id"], args["b"]["bloco_idx"]),
            forcar=True,
            **comum,
        )
    elif proposta.tipo == "fixar":
        resultado = apply.fixar(
            db,
            grade,
            estado,
            config,
            apply.Bloco(args["oferta_id"], args["bloco_idx"]),
            args["fixada"],
            **comum,
        )
    elif proposta.tipo == "regenerar":
        resultado = apply.substituir_alocacoes(
            db,
            grade,
            estado,
            config,
            [tuple(x) for x in args["posicoes"]],
            proposta.descricao,
            **comum,
        )
    elif proposta.tipo == "disponibilidade":
        resultado = _aplicar_disponibilidade(db, args, grade)
    elif proposta.tipo == "desfazer":
        desfeitos = apply.desfazer(
            db, grade, estado, config, args.get("passos", 1), autor=comum["autor"]
        )
        resultado = apply.Resultado(descricao="; ".join(desfeitos))
    else:  # pragma: no cover - tipo novo sem tratamento
        raise PropostaInvalida(f"Tipo de proposta desconhecido: {proposta.tipo}")

    proposta.aplicada = True
    return resultado


def _aplicar_disponibilidade(db: Session, args: dict, grade: m.Grade) -> apply.Resultado:
    """Disponibilidade não é alocação: mexe no cadastro do professor.

    Por isso não entra no diff de `Alocacao`, mas registra histórico com origem
    CHAT para o usuário ver o que o assistente fez.
    """
    status = m.StatusDisponibilidade(args["status"])
    atuais = {
        d.slot_id: d
        for d in db.query(m.Disponibilidade).filter(
            m.Disponibilidade.professor_id == args["professor_id"],
            m.Disponibilidade.slot_id.in_(args["slot_ids"]),
        )
    }
    for slot_id in args["slot_ids"]:
        atual = atuais.get(slot_id)
        if status == m.StatusDisponibilidade.DISPONIVEL:
            if atual is not None:
                db.delete(atual)
            continue
        if atual is None:
            db.add(
                m.Disponibilidade(
                    professor_id=args["professor_id"],
                    unidade_id=grade.unidade_id,
                    slot_id=slot_id,
                    status=status,
                )
            )
        else:
            atual.status = status

    descricao = args.get("descricao", "disponibilidade alterada")
    db.add(
        m.HistoricoAlteracao(
            grade_id=grade.id,
            origem=m.OrigemAlteracao.CHAT,
            autor="assistente",
            diff={"tipo": "disponibilidade", "descricao": descricao, "alteracoes": []},
        )
    )
    db.flush()
    return apply.Resultado(descricao=descricao)
