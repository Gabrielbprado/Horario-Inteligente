"""Por que a grade nao fecha (PLANO.md secao 5.7).

`INFEASIBLE` sozinho nao ajuda ninguem. Aqui o modelo e' remontado com um
literal de suposicao por grupo de restricoes (um por professor, um por turma, um
por espaco) e o CP-SAT responde **qual subconjunto minimo** e' impossivel de
satisfazer junto. Esse subconjunto vira uma frase que nomeia os culpados e
sugere o que mudar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.scheduling.domain import GradeState
from app.scheduling.solver import ModeloGrade, Parametros, _configurar
from app.schemas import ConfigRegras

ROTULO_GRUPO = {
    "professor": "o horário de",
    "turma": "a grade da turma",
    "espaco": "a disponibilidade de",
    "oferta": "a distribuição de",
    "janela_turma": "zero janela na turma",
    "janela_professor": "zero janela para",
    "interjornada": "11 h de descanso entre as jornadas de",
}

AVISOS_RIGIDOS = {"janela_turma", "janela_professor", "interjornada"}
"""Grupos criados por `Parametros.resolver_avisos`."""

ACOES = {
    "professor": ("liberar_disponibilidade", "Liberar mais horários na disponibilidade dele"),
    "turma": ("usar_sabado", "Usar o sábado ou reduzir a carga do período"),
    "espaco": ("adicionar_espaco", "Cadastrar mais uma sala ou laboratório desse tipo"),
    "oferta": (
        "permitir_mais_blocos",
        "Permitir mais de um bloco por dia nessa disciplina",
    ),
    "janela_turma": ("aceitar_janela", "Aceitar a janela da turma ou rever a disponibilidade"),
    "janela_professor": (
        "aceitar_janela",
        "Aceitar a janela do professor ou liberar mais horários dele",
    ),
    "interjornada": (
        "aceitar_interjornada",
        "Aceitar o aviso de interjornada ou mover a aula dele na outra unidade",
    ),
}


@dataclass(slots=True)
class Diagnostico:
    mensagem: str
    culpados: list[dict] = field(default_factory=list)
    acoes: list[dict] = field(default_factory=list)


def _nome(estado: GradeState, tipo: str, id_: int) -> str:
    if tipo in ("professor", "janela_professor", "interjornada"):
        return estado.nome_professor(id_)
    if tipo in ("turma", "janela_turma"):
        turma = estado.turmas.get(id_)
        return turma.rotulo if turma else f"turma {id_}"
    if tipo == "espaco":
        espaco = estado.espacos.get(id_)
        return espaco.nome if espaco else f"espaço {id_}"
    oferta = estado.ofertas.get(id_)
    return estado.rotulo_oferta(oferta) if oferta else f"oferta {id_}"


def diagnosticar(
    estado: GradeState, config: ConfigRegras, params: Parametros | None = None
) -> Diagnostico:
    """Explica a inviabilidade em português, nomeando as entidades envolvidas."""
    params = params or Parametros()

    modelo = ModeloGrade(estado, config, params, com_suposicoes=True)

    if modelo.inviaveis:
        nomes = sorted(
            {estado.rotulo_oferta(estado.ofertas[b.oferta_id]) for b in modelo.inviaveis}
        )
        return Diagnostico(
            mensagem=(
                f"Não há nenhum horário possível para {', '.join(nomes)}. "
                "Veja as pendências da unidade para o motivo de cada uma."
            ),
            culpados=[{"tipo": "oferta", "nome": n} for n in nomes],
            acoes=[{"chave": a, "descricao": d} for a, d in [ACOES["professor"], ACOES["turma"]]],
        )

    if params.resolver_avisos:
        return _diagnosticar_avisos(estado, modelo, params)

    if not modelo.suposicoes:
        return Diagnostico(
            mensagem=(
                "A grade não fecha, mas nenhuma restrição isolada explica o problema. "
                "Reveja a carga das turmas e a disponibilidade dos professores."
            )
        )

    modelo.modelo.clear_objective()
    modelo.modelo.add_assumptions(list(modelo.suposicoes.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = min(30.0, params.tempo_limite_s)
    solver.parameters.num_search_workers = 1  # a extracao do nucleo e' sequencial
    solver.parameters.random_seed = params.semente
    status = solver.solve(modelo.modelo)

    if status != cp_model.INFEASIBLE:
        return Diagnostico(
            mensagem=(
                "A grade fecha se alguma das restrições de exclusividade for relaxada, "
                "mas o solver não conseguiu isolar qual no tempo disponível."
            )
        )

    por_literal = {v.index: chave for chave, v in modelo.suposicoes.items()}
    culpados = [
        por_literal[i]
        for i in solver.sufficient_assumptions_for_infeasibility()
        if i in por_literal
    ]

    if not culpados:
        return Diagnostico(
            mensagem=(
                "A grade é impossível mesmo sem as restrições de exclusividade: "
                "há mais aulas do que horários no turno."
            ),
            acoes=[{"chave": ACOES["turma"][0], "descricao": ACOES["turma"][1]}],
        )

    return Diagnostico(
        mensagem=_frase(estado, culpados),
        culpados=[
            {"tipo": tipo, "id": id_, "nome": _nome(estado, tipo, id_)} for tipo, id_ in culpados
        ],
        acoes=[
            {"chave": ACOES[tipo][0], "descricao": ACOES[tipo][1]}
            for tipo in dict.fromkeys(tipo for tipo, _ in culpados)
        ],
    )


def _diagnosticar_avisos(
    estado: GradeState, modelo: ModeloGrade, params: Parametros
) -> Diagnostico:
    """Quais avisos nao tem como ser resolvidos.

    A grade sem os avisos rigidos fecha (foi gerada), entao os culpados estao
    entre os grupos de janela/interjornada. Com todos os workers o CP-SAT prova
    a inviabilidade em menos de um segundo, mas a extracao de nucleo por
    suposicoes exige um worker so' e nao termina no tempo. Em vez disso,
    crescimento guloso: endurece um grupo por vez e guarda o maior conjunto que
    ainda fecha. O que ficou de fora e' o que o job relaxa para entregar a grade
    — e e' o que a mensagem nomeia. Turma antes de professor, professor antes de
    interjornada: a mesma ordem dos pesos do objetivo.
    """
    grupos = {k: v for k, v in modelo.suposicoes.items() if k[0] in AVISOS_RIGIDOS}
    base = modelo.modelo
    base.clear_objective()
    for chave, literal in modelo.suposicoes.items():
        if chave[0] not in AVISOS_RIGIDOS:
            base.add(literal == 1)

    por_tentativa = max(2.0, min(10.0, params.tempo_limite_s / max(1, len(grupos))))

    def fecha(rigidos: set[tuple[str, int]]) -> bool:
        tentativa = base.clone()
        for chave, literal in grupos.items():
            tentativa.add(literal == (1 if chave in rigidos else 0))
        solver = cp_model.CpSolver()
        _configurar(solver, params)
        solver.parameters.max_time_in_seconds = por_tentativa
        return solver.solve(tentativa) in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    # ponytail: O(n) solves; nucleo por suposicoes se um dia o CP-SAT provar
    # inviabilidade com varios workers.
    prioridade = {"janela_turma": 0, "janela_professor": 1, "interjornada": 2}
    rigidos: set[tuple[str, int]] = set()
    culpados: list[tuple[str, int]] = []
    for chave in sorted(grupos, key=lambda c: (prioridade[c[0]], c[1])):
        if fecha(rigidos | {chave}):
            rigidos.add(chave)
        else:
            culpados.append(chave)

    if not culpados:
        return Diagnostico(
            mensagem=(
                "Não foi possível eliminar os avisos no tempo disponível. "
                "Tente de novo com um tempo limite maior."
            )
        )
    return Diagnostico(
        mensagem=_frase(estado, culpados),
        culpados=[{"tipo": t, "id": i, "nome": _nome(estado, t, i)} for t, i in culpados],
        acoes=[
            {"chave": ACOES[tipo][0], "descricao": ACOES[tipo][1]}
            for tipo in dict.fromkeys(tipo for tipo, _ in culpados)
        ],
    )


def _frase(estado: GradeState, culpados: list[tuple[str, int]]) -> str:
    por_tipo: dict[str, list[str]] = {}
    for tipo, id_ in culpados:
        por_tipo.setdefault(tipo, []).append(_nome(estado, tipo, id_))

    partes = [
        f"{ROTULO_GRUPO[tipo]} {', '.join(sorted(nomes))}"
        for tipo, nomes in sorted(por_tipo.items())
    ]
    if len(partes) == 1:
        alvo = partes[0]
    else:
        alvo = ", ".join(partes[:-1]) + " e " + partes[-1]

    if any(tipo in AVISOS_RIGIDOS for tipo in por_tipo):
        # Veio do "Resolver avisos": o que nao fecha e' o aviso virado regra.
        return (
            f"Não há grade que garanta ao mesmo tempo {alvo}. Os outros avisos foram "
            "resolvidos; para estes, dê ciência ou mude o que os causa (disponibilidade, "
            "tamanho do bloco, carga no sábado)."
        )
    return (
        f"Não é possível montar a grade sem que duas aulas caiam no mesmo horário "
        f"em {alvo}. Esse é o conjunto mínimo de restrições que não cabem juntas."
    )
