"""Ferramentas que o assistente pode chamar (seção 6.2 da especificação).

As de leitura respondem na hora. As que **mudam** a grade não gravam nada: elas
simulam e devolvem uma proposta, que só vira alteração quando o usuário clica em
Aplicar. O modelo nunca toca no banco.

Todos os esquemas usam `strict: true`, que exige `additionalProperties: false` e
todo campo em `required` — parâmetros opcionais viram tipos anuláveis.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.orm import Session

from app import models as m
from app.chat import propostas
from app.scheduling import apply
from app.scheduling.domain import DIAS, AlocacaoInfo, GradeState
from app.scheduling.solver import Parametros, resolver
from app.schemas import ConfigRegras

LIMITE_RESULTADOS = 60
"""Teto de itens por resposta: a janela de contexto do modelo é finita, e uma
grade inteira em texto empurra o resto para fora dela."""


@dataclass(slots=True)
class Contexto:
    db: Session
    grade: m.Grade
    estado: GradeState
    config: ConfigRegras
    autor: str | None = None
    propostas_criadas: list[propostas.Proposta] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.propostas_criadas is None:
            self.propostas_criadas = []


def _sem_acento(texto: str) -> str:
    sem = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem if not unicodedata.combining(c))


def _bloco_da_alocacao(ctx: Contexto, alocacao_id: int) -> apply.Bloco:
    aula = next((a for a in ctx.estado.alocacoes if a.id == alocacao_id), None)
    if aula is None:
        raise ValueError(
            f"Não existe aula com id {alocacao_id} nesta grade. "
            "Use buscar_grade para ver os ids reais."
        )
    return apply.Bloco(aula.oferta_id, aula.bloco_idx)


# ------------------------------------------------------------------ leitura


def buscar_grade(ctx: Contexto, filtro: dict) -> dict:
    """Aulas da grade, filtradas. Uma linha por hora-aula."""
    aulas = ctx.estado.alocacoes
    if (turma_id := filtro.get("turma_id")) is not None:
        aulas = [a for a in aulas if ctx.estado.ofertas[a.oferta_id].turma_id == turma_id]
    if (professor_id := filtro.get("professor_id")) is not None:
        aulas = [a for a in aulas if a.professor_id == professor_id]
    if (espaco_id := filtro.get("espaco_id")) is not None:
        aulas = [a for a in aulas if a.espaco_id == espaco_id]
    if (dia := filtro.get("dia")) is not None:
        aulas = [a for a in aulas if ctx.estado.slots[a.slot_id].dia == dia]

    aulas = sorted(
        aulas,
        key=lambda a: (ctx.estado.slots[a.slot_id].dia, ctx.estado.slots[a.slot_id].ordem),
    )
    total = len(aulas)
    return {
        "total": total,
        "mostrando": min(total, LIMITE_RESULTADOS),
        "aulas": [
            {
                "alocacao_id": a.id,
                "oferta_id": a.oferta_id,
                "bloco_idx": a.bloco_idx,
                "disciplina": ctx.estado.disciplina_da(ctx.estado.ofertas[a.oferta_id]).sigla,
                "turma": ctx.estado.turma_da(ctx.estado.ofertas[a.oferta_id]).rotulo,
                "subturma": ctx.estado.ofertas[a.oferta_id].subturma,
                "professor": ctx.estado.nome_professor(a.professor_id),
                "professor_id": a.professor_id,
                "slot_id": a.slot_id,
                "horario": ctx.estado.slots[a.slot_id].rotulo,
                "espaco": ctx.estado.espacos[a.espaco_id].nome if a.espaco_id else None,
                "fixada": a.fixada,
            }
            for a in aulas[:LIMITE_RESULTADOS]
        ],
    }


def buscar_entidades(ctx: Contexto, texto: str) -> dict:
    """Resolve nomes citados pelo usuário em ids.

    Cobre professor, turma, disciplina, espaço e **horário** — "quinta 20h50" é
    tão citável quanto "Luciana", e sem o id do horário o modelo não consegue
    mover nada.
    """
    alvo = _sem_acento(texto).strip()
    if not alvo:
        return {"encontrados": []}

    achados: list[dict] = []

    for pid, prof in ctx.estado.professores.items():
        if alvo in _sem_acento(prof.nome):
            achados.append({"tipo": "professor", "id": pid, "rotulo": prof.nome})
    for tid, turma in ctx.estado.turmas.items():
        if alvo in _sem_acento(turma.rotulo):
            achados.append({"tipo": "turma", "id": tid, "rotulo": turma.rotulo})
    for did, disciplina in ctx.estado.disciplinas.items():
        if alvo in _sem_acento(disciplina.nome) or alvo in _sem_acento(disciplina.sigla):
            achados.append(
                {
                    "tipo": "disciplina",
                    "id": did,
                    "rotulo": f"{disciplina.sigla} — {disciplina.nome}",
                }
            )
    for eid, espaco in ctx.estado.espacos.items():
        if alvo in _sem_acento(espaco.nome):
            achados.append({"tipo": "espaco", "id": eid, "rotulo": espaco.nome})

    # Horarios: casa pelo nome do dia e/ou pela hora escrita como 20:50 ou 20h50
    hora = alvo.replace("h", ":")
    for slot in sorted(ctx.estado.slots.values(), key=lambda s: (s.dia, s.ordem)):
        rotulo = _sem_acento(slot.rotulo).replace("h", ":")
        dia_citado = any(alvo.startswith(_sem_acento(d)[:3]) for d in DIAS)
        if (dia_citado and _sem_acento(DIAS[slot.dia]) in alvo) or (":" in hora and hora in rotulo):
            achados.append({"tipo": "horario", "id": slot.id, "rotulo": slot.rotulo})

    return {
        "encontrados": achados[:LIMITE_RESULTADOS],
        "total": len(achados),
        "dica": (
            "Nada encontrado. Peça ao usuário para escrever o nome como está no "
            "cadastro, ou use buscar_grade para listar o que existe."
            if not achados
            else None
        ),
    }


def validar_movimento(
    ctx: Contexto, alocacao_id: int, novo_slot_id: int, novo_espaco_id: int | None
) -> dict:
    """O que o movimento quebraria, sem propor nem aplicar nada."""
    bloco = _bloco_da_alocacao(ctx, alocacao_id)
    try:
        resultado = apply.simular_movimento(
            ctx.estado, ctx.config, bloco, novo_slot_id, novo_espaco_id
        )
    except apply.MovimentoInvalido as erro:
        return {"possivel": False, "motivo": str(erro)}
    return {
        "possivel": resultado.permitido,
        "descricao": resultado.descricao,
        "violacoes": [
            {"severidade": v.severidade.value, "mensagem": v.mensagem} for v in resultado.violacoes
        ],
    }


def explicar(ctx: Contexto, alocacao_id: int | None, aviso_id: int | None) -> dict:
    """Dados estruturados para o modelo explicar por que algo está assim."""
    if aviso_id is not None:
        aviso = ctx.db.get(m.Aviso, aviso_id)
        if aviso is None or aviso.grade_id != ctx.grade.id:
            return {"erro": f"Não existe aviso {aviso_id} nesta grade."}
        return {
            "tipo": aviso.tipo,
            "severidade": aviso.severidade.value,
            "mensagem": aviso.mensagem,
            "entidades": aviso.entidades,
            "ciente": aviso.ciente,
        }

    if alocacao_id is None:
        return {"erro": "Informe alocacao_id ou aviso_id."}

    aula = next((a for a in ctx.estado.alocacoes if a.id == alocacao_id), None)
    if aula is None:
        return {"erro": f"Não existe aula com id {alocacao_id} nesta grade."}

    bloco = apply.Bloco(aula.oferta_id, aula.bloco_idx)
    oferta = ctx.estado.ofertas[aula.oferta_id]
    disciplina = ctx.estado.disciplina_da(oferta)
    destinos = apply.destinos_possiveis(ctx.estado, ctx.config, bloco)
    livres = [
        ctx.estado.slots[slot_id].rotulo
        for slot_id, r in sorted(destinos.items())
        if r.permitido and slot_id != aula.slot_id
    ]

    return {
        "aula": ctx.estado.rotulo_oferta(oferta),
        "professor": ctx.estado.nome_professor(aula.professor_id),
        "horario": ctx.estado.slots[aula.slot_id].rotulo,
        "espaco": ctx.estado.espacos[aula.espaco_id].nome if aula.espaco_id else None,
        "fixada": aula.fixada,
        "aulas_semanais": disciplina.aulas_semanais,
        "blocos_por_dia": disciplina.max_blocos_por_dia,
        "concentrar_no_dia": disciplina.concentrar_no_dia,
        "precisa_laboratorio": disciplina.tipo_laboratorio
        if disciplina.precisa_laboratorio
        else None,
        "remota": disciplina.remota,
        "outros_horarios_possiveis": livres[:12],
        "quantos_horarios_possiveis": len(livres),
    }


# -------------------------------------------------------------- proposicoes


def mover_aula(
    ctx: Contexto, alocacao_id: int, novo_slot_id: int, novo_espaco_id: int | None
) -> dict:
    bloco = _bloco_da_alocacao(ctx, alocacao_id)
    try:
        resultado = apply.simular_movimento(
            ctx.estado, ctx.config, bloco, novo_slot_id, novo_espaco_id
        )
    except apply.MovimentoInvalido as erro:
        return {"erro": str(erro)}
    if not resultado.alteracoes:
        return {"erro": "A aula já está nesse horário; não há o que mudar."}

    proposta = propostas.de_resultado(
        ctx.estado,
        ctx.grade.id,
        "mover",
        resultado,
        {
            "oferta_id": bloco.oferta_id,
            "bloco_idx": bloco.bloco_idx,
            "slot_inicial": novo_slot_id,
            "espaco_id": novo_espaco_id,
        },
    )
    ctx.propostas_criadas.append(proposta)
    return {"proposta_id": proposta.id, "resumo": proposta.resumo()}


def trocar_aulas(ctx: Contexto, alocacao_id_a: int, alocacao_id_b: int) -> dict:
    a, b = _bloco_da_alocacao(ctx, alocacao_id_a), _bloco_da_alocacao(ctx, alocacao_id_b)
    try:
        resultado = apply.simular_troca(ctx.estado, ctx.config, a, b)
    except apply.MovimentoInvalido as erro:
        return {"erro": str(erro)}

    proposta = propostas.de_resultado(
        ctx.estado,
        ctx.grade.id,
        "trocar",
        resultado,
        {
            "a": {"oferta_id": a.oferta_id, "bloco_idx": a.bloco_idx},
            "b": {"oferta_id": b.oferta_id, "bloco_idx": b.bloco_idx},
        },
    )
    ctx.propostas_criadas.append(proposta)
    return {"proposta_id": proposta.id, "resumo": proposta.resumo()}


def fixar_aula(ctx: Contexto, alocacao_id: int, fixada: bool) -> dict:
    bloco = _bloco_da_alocacao(ctx, alocacao_id)
    aulas = apply.aulas_do_bloco(ctx.estado, bloco)
    if all(a.fixada == fixada for a in aulas):
        return {"erro": f"A aula já está {'fixada' if fixada else 'livre'}."}

    resultado = apply.Resultado(
        alteracoes=[
            apply.Alteracao(alocacao_id=a.id, antes={"fixada": a.fixada}, depois={"fixada": fixada})
            for a in aulas
            if a.fixada != fixada
        ],
        descricao=(
            f"{'fixar' if fixada else 'liberar'} "
            f"{ctx.estado.rotulo_oferta(ctx.estado.ofertas[bloco.oferta_id])}"
        ),
    )
    proposta = propostas.de_resultado(
        ctx.estado,
        ctx.grade.id,
        "fixar",
        resultado,
        {"oferta_id": bloco.oferta_id, "bloco_idx": bloco.bloco_idx, "fixada": fixada},
    )
    ctx.propostas_criadas.append(proposta)
    return {"proposta_id": proposta.id, "resumo": proposta.resumo()}


def alterar_disponibilidade(
    ctx: Contexto, professor_id: int, slot_ids: list[int], status: str
) -> dict:
    if professor_id not in ctx.estado.professores:
        return {"erro": f"Não existe professor {professor_id} nesta unidade."}
    desconhecidos = [s for s in slot_ids if s not in ctx.estado.slots]
    if desconhecidos:
        return {"erro": f"Horários inexistentes: {desconhecidos}"}
    try:
        m.StatusDisponibilidade(status)
    except ValueError:
        return {"erro": "status deve ser DISPONIVEL, PREFERENCIAL ou INDISPONIVEL."}

    nome = ctx.estado.nome_professor(professor_id)
    descricao = f"marcar {len(slot_ids)} horário(s) de {nome} como {status.lower()}"
    proposta = propostas.REGISTRO.criar(
        grade_id=ctx.grade.id,
        tipo="disponibilidade",
        descricao=descricao,
        argumentos={
            "professor_id": professor_id,
            "slot_ids": slot_ids,
            "status": status,
            "descricao": descricao,
        },
        mudancas=[
            propostas.Mudanca(
                rotulo=f"{nome} · {ctx.estado.slots[s].rotulo}",
                antes=ctx.estado.status_disponibilidade(professor_id, s).value.lower(),
                depois=status.lower(),
            )
            for s in slot_ids[:12]
        ],
    )
    ctx.propostas_criadas.append(proposta)
    return {
        "proposta_id": proposta.id,
        "resumo": proposta.resumo()
        + "\nAviso: mudar a disponibilidade não remaneja as aulas já alocadas; "
        "use regenerar_parcial depois, se for o caso.",
    }


def regenerar_parcial(
    ctx: Contexto,
    turma_ids: list[int] | None,
    professor_ids: list[int] | None,
    dias: list[int] | None,
) -> dict:
    """Roda o solver só na vizinhança pedida, com o resto congelado.

    Congelar é literal: as aulas de fora do escopo entram no modelo como
    fixadas, então o solver não pode mexer nelas.
    """
    if not any([turma_ids, professor_ids, dias]):
        return {"erro": "Diga o escopo: turmas, professores ou dias a remanejar."}

    def no_escopo(a: AlocacaoInfo) -> bool:
        oferta = ctx.estado.ofertas[a.oferta_id]
        if turma_ids and oferta.turma_id in turma_ids:
            return True
        if professor_ids and a.professor_id in professor_ids:
            return True
        if dias and ctx.estado.slots[a.slot_id].dia in dias:
            return True
        return False

    alvo = [a for a in ctx.estado.alocacoes if no_escopo(a)]
    if not alvo:
        return {"erro": "Nenhuma aula cai nesse escopo."}

    congelado = replace(
        ctx.estado,
        alocacoes=[
            replace(a, fixada=True) if not no_escopo(a) else a for a in ctx.estado.alocacoes
        ],
    )
    solucao = resolver(
        congelado,
        ctx.config,
        Parametros(tempo_limite_s=20, manter_fixadas=True, grade_anterior=ctx.estado.alocacoes),
    )
    if not solucao.viavel:
        return {
            "erro": "Não há solução mantendo o resto da grade fixo. "
            "Tente um escopo maior ou libere alguma restrição."
        }

    posicoes = [
        [a.oferta_id, a.bloco_idx, a.slot_id, a.espaco_id, i]
        for i, a in enumerate(solucao.alocacoes)
    ]
    mudancas = _diferenca(ctx.estado, solucao.alocacoes)
    if not mudancas:
        return {"erro": "O solver devolveu exatamente a mesma grade; nada a propor."}

    proposta = propostas.REGISTRO.criar(
        grade_id=ctx.grade.id,
        tipo="regenerar",
        descricao=f"remanejar {len(alvo)} aula(s) do escopo pedido",
        argumentos={"posicoes": posicoes},
        mudancas=mudancas,
        permitido=True,
    )
    ctx.propostas_criadas.append(proposta)
    return {"proposta_id": proposta.id, "resumo": proposta.resumo()}


def _diferenca(estado: GradeState, novas) -> list[propostas.Mudanca]:
    """Compara a grade atual com a proposta pelo solver, bloco a bloco."""

    def posicoes(itens) -> dict[tuple[int, int], list[int]]:
        agrupado: dict[tuple[int, int], list[int]] = {}
        for a in itens:
            agrupado.setdefault((a.oferta_id, a.bloco_idx), []).append(a.slot_id)
        return {k: sorted(v) for k, v in agrupado.items()}

    antes, depois = posicoes(estado.alocacoes), posicoes(novas)
    mudancas = []
    for chave in sorted(set(antes) | set(depois)):
        if antes.get(chave) == depois.get(chave):
            continue
        oferta = estado.ofertas.get(chave[0])
        rotulo = estado.rotulo_oferta(oferta) if oferta else f"oferta {chave[0]}"
        mudancas.append(
            propostas.Mudanca(
                rotulo=rotulo,
                antes=_faixa(estado, antes.get(chave, [])),
                depois=_faixa(estado, depois.get(chave, [])),
            )
        )
    return mudancas


def _faixa(estado: GradeState, slot_ids: list[int]) -> str:
    if not slot_ids:
        return "—"
    slots = [estado.slots[s] for s in slot_ids if s in estado.slots]
    if not slots:
        return "—"
    return f"{DIAS[slots[0].dia]} {slots[0].rotulo.split(' ', 1)[1]}"


def desfazer(ctx: Contexto, passos: int) -> dict:
    pendentes = [
        r
        for r in ctx.db.query(m.HistoricoAlteracao)
        .filter(
            m.HistoricoAlteracao.grade_id == ctx.grade.id,
            m.HistoricoAlteracao.desfeito.is_(False),
        )
        .order_by(m.HistoricoAlteracao.id.desc())
        .limit(max(1, passos))
    ]
    if not pendentes:
        return {"erro": "Não há nada para desfazer nesta grade."}

    proposta = propostas.REGISTRO.criar(
        grade_id=ctx.grade.id,
        tipo="desfazer",
        descricao=f"desfazer {len(pendentes)} alteração(ões)",
        argumentos={"passos": len(pendentes)},
        mudancas=[
            propostas.Mudanca(
                rotulo=r.diff.get("descricao", "alteração"), antes="aplicada", depois="desfeita"
            )
            for r in pendentes
        ],
    )
    ctx.propostas_criadas.append(proposta)
    return {"proposta_id": proposta.id, "resumo": proposta.resumo()}


# ------------------------------------------------------------------ esquemas


def _obj(propriedades: dict[str, Any]) -> dict:
    """Objeto no formato que `strict: true` exige."""
    return {
        "type": "object",
        "properties": propriedades,
        "required": list(propriedades),
        "additionalProperties": False,
    }


_INT_OPC = {"type": ["integer", "null"]}
_LISTA_INT_OPC = {"type": ["array", "null"], "items": {"type": "integer"}}

ESQUEMAS: list[dict] = [
    {
        "name": "buscar_grade",
        "description": (
            "Lista as aulas da grade atual. Use antes de qualquer alteração para "
            "descobrir os ids reais de aula, oferta e horário."
        ),
        "parameters": _obj(
            {
                "turma_id": _INT_OPC,
                "professor_id": _INT_OPC,
                "espaco_id": _INT_OPC,
                "dia": {
                    "type": ["integer", "null"],
                    "description": "0 = segunda ... 5 = sábado.",
                },
            }
        ),
    },
    {
        "name": "buscar_entidades",
        "description": (
            "Resolve um nome citado pelo usuário em ids: professor, turma, "
            "disciplina, sala ou horário. SEMPRE use isto antes de agir; nunca "
            "invente ids."
        ),
        "parameters": _obj({"texto": {"type": "string"}}),
    },
    {
        "name": "validar_movimento",
        "description": "Diz o que um movimento quebraria, sem propor nem aplicar.",
        "parameters": _obj(
            {
                "alocacao_id": {"type": "integer"},
                "novo_slot_id": {"type": "integer"},
                "novo_espaco_id": _INT_OPC,
            }
        ),
    },
    {
        "name": "mover_aula",
        "description": (
            "Propõe mover o bloco de aulas para outro horário. Cria uma proposta "
            "que o usuário precisa aplicar; não altera a grade sozinha."
        ),
        "parameters": _obj(
            {
                "alocacao_id": {"type": "integer"},
                "novo_slot_id": {"type": "integer"},
                "novo_espaco_id": _INT_OPC,
            }
        ),
    },
    {
        "name": "trocar_aulas",
        "description": "Propõe trocar dois blocos de lugar. Eles precisam ter o mesmo tamanho.",
        "parameters": _obj(
            {"alocacao_id_a": {"type": "integer"}, "alocacao_id_b": {"type": "integer"}}
        ),
    },
    {
        "name": "fixar_aula",
        "description": "Propõe fixar ou liberar um bloco. Aula fixada não sai do lugar ao regerar.",
        "parameters": _obj({"alocacao_id": {"type": "integer"}, "fixada": {"type": "boolean"}}),
    },
    {
        "name": "alterar_disponibilidade",
        "description": (
            "Propõe mudar a disponibilidade de um professor em certos horários. "
            "Não remaneja as aulas já alocadas."
        ),
        "parameters": _obj(
            {
                "professor_id": {"type": "integer"},
                "slot_ids": {"type": "array", "items": {"type": "integer"}},
                "status": {
                    "type": "string",
                    "enum": ["DISPONIVEL", "PREFERENCIAL", "INDISPONIVEL"],
                },
            }
        ),
    },
    {
        "name": "regenerar_parcial",
        "description": (
            "Propõe rodar o solver só na vizinhança indicada, congelando o resto "
            "da grade. Informe ao menos um entre turmas, professores e dias."
        ),
        "parameters": _obj(
            {
                "turma_ids": _LISTA_INT_OPC,
                "professor_ids": _LISTA_INT_OPC,
                "dias": _LISTA_INT_OPC,
            }
        ),
    },
    {
        "name": "explicar",
        "description": (
            "Dados sobre uma aula ou um aviso, para você explicar ao usuário por "
            "que a grade está assim. Informe alocacao_id OU aviso_id."
        ),
        "parameters": _obj({"alocacao_id": _INT_OPC, "aviso_id": _INT_OPC}),
    },
    {
        "name": "desfazer",
        "description": "Propõe desfazer as últimas alterações da grade.",
        "parameters": _obj({"passos": {"type": "integer"}}),
    },
]

IMPLEMENTACOES: dict[str, Callable[..., dict]] = {
    "buscar_grade": lambda ctx, **kw: buscar_grade(ctx, kw),
    "buscar_entidades": buscar_entidades,
    "validar_movimento": validar_movimento,
    "mover_aula": mover_aula,
    "trocar_aulas": trocar_aulas,
    "fixar_aula": fixar_aula,
    "alterar_disponibilidade": alterar_disponibilidade,
    "regenerar_parcial": regenerar_parcial,
    "explicar": explicar,
    "desfazer": desfazer,
}


def definicoes_openai() -> list[dict]:
    """Os esquemas no formato da Responses API, com `strict`."""
    return [{"type": "function", "strict": True, **e} for e in ESQUEMAS]


def executar(ctx: Contexto, nome: str, argumentos_json: str) -> str:
    """Executa a ferramenta e devolve o resultado como JSON para o modelo.

    Erro de ferramenta não derruba a conversa: volta como texto para o modelo
    poder se corrigir ou explicar a limitação ao usuário.
    """
    funcao = IMPLEMENTACOES.get(nome)
    if funcao is None:
        return json.dumps({"erro": f"Ferramenta desconhecida: {nome}"}, ensure_ascii=False)
    try:
        argumentos = json.loads(argumentos_json or "{}")
    except json.JSONDecodeError:
        return json.dumps({"erro": "Argumentos não são JSON válido."}, ensure_ascii=False)

    try:
        resultado = funcao(ctx, **argumentos)
    except TypeError as erro:
        resultado = {"erro": f"Argumentos inválidos para {nome}: {erro}"}
    except ValueError as erro:
        resultado = {"erro": str(erro)}
    except Exception as erro:  # pragma: no cover - rede de seguranca
        resultado = {"erro": f"Falha ao executar {nome}: {erro}"}

    return json.dumps(resultado, ensure_ascii=False, default=str)
