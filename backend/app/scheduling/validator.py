"""Validador unico (secao 8 da especificacao).

`validar(estado, config)` e' a **unica** definicao das regras de uma grade. Quem
usa: o pos-solver, o arrastar-e-soltar, as ferramentas do chatbot e o botao
publicar. Se o solver e o validador discordarem, o validador esta' certo por
definicao — e o teste de propriedade em `tests/test_validador_solver.py` existe
para que nao discordem.

Funcao pura: recebe `GradeState` (que ja' inclui as aulas das outras unidades do
escopo) e devolve as violacoes em pt-BR, prontas para virar `Aviso`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from app.models import ModoDivisao, Severidade, StatusDisponibilidade, TipoEspaco
from app.scheduling.domain import (
    DIAS,
    AlocacaoInfo,
    GradeState,
    SlotInfo,
    Violacao,
    hhmm,
)
from app.schemas import ConfigRegras
from app.services import blocos_de

BLOQUEANTE = Severidade.BLOQUEANTE
ALERTA = Severidade.ALERTA
INFO = Severidade.INFO


class _Contexto:
    """Indices derivados do estado, calculados uma vez e lidos por todas as
    checagens. Sem isso cada checagem varreria a lista de alocacoes de novo."""

    def __init__(self, estado: GradeState, config: ConfigRegras):
        self.estado = estado
        self.config = config

        # Alocacoes cujo slot ou oferta nao existe sao descartadas aqui e
        # reportadas por `_referencias_quebradas`; o resto do validador assume
        # que os dicionarios respondem.
        self.validas = [
            a
            for a in estado.alocacoes
            if a.slot_id in estado.slots and a.oferta_id in estado.ofertas
        ]

        self.por_oferta: dict[int, list[AlocacaoInfo]] = defaultdict(list)
        self.por_bloco: dict[tuple[int, int], list[AlocacaoInfo]] = defaultdict(list)
        self.por_professor_slot: dict[tuple[int, int], list[AlocacaoInfo]] = defaultdict(list)
        self.por_fluxo_slot: dict[tuple[tuple[int, str], int], list[AlocacaoInfo]] = defaultdict(
            list
        )
        self.por_espaco_slot: dict[tuple[int, int], list[AlocacaoInfo]] = defaultdict(list)
        self.por_professor_dia: dict[tuple[int, int], list[AlocacaoInfo]] = defaultdict(list)

        for a in self.validas:
            slot = estado.slots[a.slot_id]
            oferta = estado.ofertas[a.oferta_id]
            self.por_oferta[a.oferta_id].append(a)
            self.por_bloco[(a.oferta_id, a.bloco_idx)].append(a)
            self.por_professor_slot[(a.professor_id, a.slot_id)].append(a)
            if a.espaco_id is not None:
                self.por_espaco_slot[(a.espaco_id, a.slot_id)].append(a)
            self.por_professor_dia[(a.professor_id, slot.dia)].append(a)
            for fluxo in estado.fluxos_da_oferta(oferta):
                self.por_fluxo_slot[(fluxo, a.slot_id)].append(a)

    def slot(self, a: AlocacaoInfo) -> SlotInfo:
        return self.estado.slots[a.slot_id]

    def rotulo(self, a: AlocacaoInfo) -> str:
        return self.estado.rotulo_oferta(self.estado.ofertas[a.oferta_id])


# ------------------------------------------------------------------- estrutura


def _referencias_quebradas(ctx: _Contexto) -> Iterator[Violacao]:
    for a in ctx.estado.alocacoes:
        faltando = []
        if a.slot_id not in ctx.estado.slots:
            faltando.append(f"horário {a.slot_id}")
        if a.oferta_id not in ctx.estado.ofertas:
            faltando.append(f"oferta {a.oferta_id}")
        if a.espaco_id is not None and a.espaco_id not in ctx.estado.espacos:
            faltando.append(f"espaço {a.espaco_id}")
        if faltando:
            yield Violacao(
                "REFERENCIA_QUEBRADA",
                BLOQUEANTE,
                f"Uma aula da grade aponta para {' e '.join(faltando)}, que não existe mais.",
                {"alocacao_id": a.id},
            )


def _quantidade_de_aulas(ctx: _Contexto) -> Iterator[Violacao]:
    for oferta in ctx.estado.ofertas.values():
        disciplina = ctx.estado.disciplina_da(oferta)
        alocadas = len(ctx.por_oferta.get(oferta.id, []))
        if alocadas == disciplina.aulas_semanais:
            continue
        rotulo = ctx.estado.rotulo_oferta(oferta)
        if alocadas == 0:
            mensagem = (
                f"{rotulo} não tem nenhuma aula na grade, mas precisa de "
                f"{disciplina.aulas_semanais} por semana."
            )
        elif alocadas < disciplina.aulas_semanais:
            mensagem = (
                f"{rotulo} está com {alocadas} de {disciplina.aulas_semanais} aulas semanais."
            )
        else:
            mensagem = (
                f"{rotulo} está com {alocadas} aulas na semana, mais que as "
                f"{disciplina.aulas_semanais} previstas."
            )
        yield Violacao(
            "QUANTIDADE_DE_AULAS",
            BLOQUEANTE,
            mensagem,
            {"oferta_id": oferta.id, "alocadas": alocadas, "previstas": disciplina.aulas_semanais},
        )


def _blocos_bem_formados(ctx: _Contexto) -> Iterator[Violacao]:
    """Um bloco geminado ocupa horarios seguidos, no mesmo dia, sem atravessar
    intervalo — e' a regra que o `bloco_id` do modelo de turno codifica."""
    for (oferta_id, bloco_idx), aulas in sorted(ctx.por_bloco.items()):
        slots = sorted((ctx.slot(a) for a in aulas), key=lambda s: (s.dia, s.ordem))
        rotulo = ctx.estado.rotulo_oferta(ctx.estado.ofertas[oferta_id])
        entidades = {"oferta_id": oferta_id, "bloco_idx": bloco_idx}

        if len({s.dia for s in slots}) > 1:
            dias = ", ".join(sorted({DIAS[s.dia] for s in slots}))
            yield Violacao(
                "BLOCO_PARTIDO",
                BLOQUEANTE,
                f"Um bloco de {rotulo} ficou espalhado entre {dias}. "
                "Aulas geminadas precisam ficar no mesmo dia.",
                entidades,
            )
            continue

        if len({s.bloco_id for s in slots}) > 1:
            yield Violacao(
                "BLOCO_ATRAVESSA_INTERVALO",
                BLOQUEANTE,
                f"Um bloco de {rotulo} atravessa o intervalo de "
                f"{DIAS[slots[0].dia]}: vai de {hhmm(slots[0].inicio_min)} a "
                f"{hhmm(slots[-1].fim_min)}, com o intervalo no meio.",
                entidades,
            )
            continue

        ordens = [s.ordem for s in slots]
        if ordens != list(range(ordens[0], ordens[0] + len(ordens))):
            yield Violacao(
                "BLOCO_NAO_CONTIGUO",
                BLOQUEANTE,
                f"Um bloco de {rotulo} tem um buraco no meio na "
                f"{DIAS[slots[0].dia]} (aulas {', '.join(map(str, ordens))}).",
                entidades,
            )

    # Os tamanhos dos blocos precisam bater com a decomposicao prevista.
    for oferta in ctx.estado.ofertas.values():
        aulas = ctx.por_oferta.get(oferta.id)
        if not aulas:
            continue
        disciplina = ctx.estado.disciplina_da(oferta)
        tamanhos = sorted(
            (len(v) for k, v in ctx.por_bloco.items() if k[0] == oferta.id), reverse=True
        )
        previstos = sorted(
            blocos_de(disciplina.aulas_semanais, disciplina.tamanho_bloco), reverse=True
        )
        if tamanhos != previstos and sum(tamanhos) == disciplina.aulas_semanais:
            yield Violacao(
                "BLOCOS_FORA_DO_PADRAO",
                ALERTA,
                f"{ctx.estado.rotulo_oferta(oferta)} ficou em blocos de "
                f"{'+'.join(map(str, tamanhos))} aulas; o previsto era "
                f"{'+'.join(map(str, previstos))}.",
                {"oferta_id": oferta.id, "tamanhos": tamanhos, "previstos": previstos},
            )


def _blocos_por_dia(ctx: _Contexto) -> Iterator[Violacao]:
    for oferta in ctx.estado.ofertas.values():
        disciplina = ctx.estado.disciplina_da(oferta)
        por_dia: dict[int, set[int]] = defaultdict(set)
        for a in ctx.por_oferta.get(oferta.id, []):
            por_dia[ctx.slot(a).dia].add(a.bloco_idx)
        for dia, blocos in sorted(por_dia.items()):
            if len(blocos) > disciplina.limite_blocos_por_dia:
                yield Violacao(
                    "BLOCOS_POR_DIA",
                    BLOQUEANTE,
                    f"{ctx.estado.rotulo_oferta(oferta)} tem {len(blocos)} blocos na "
                    f"{DIAS[dia]}, mas o limite da disciplina é "
                    f"{disciplina.max_blocos_por_dia} por dia.",
                    {"oferta_id": oferta.id, "dia": dia},
                )


def _concentracao(ctx: _Contexto) -> Iterator[Violacao]:
    """Disciplina marcada para concentrar: todas as aulas no mesmo dia e seguidas.

    Alerta, e nao bloqueante, por dois motivos. O solver concentra o que cabe
    e espalha o resto (D123): este aviso e' o que diz qual ficou de fora. E, na
    edicao manual, arrastar leva um par por vez — o primeiro par arrastado para
    outro dia sempre separa os dois, e bloquear impediria mudar de dia.
    """
    for oferta in ctx.estado.ofertas.values():
        disciplina = ctx.estado.disciplina_da(oferta)
        aulas = ctx.por_oferta.get(oferta.id, [])
        if not disciplina.concentrar_no_dia or len({a.bloco_idx for a in aulas}) < 2:
            continue

        rotulo = ctx.estado.rotulo_oferta(oferta)
        dias = sorted({ctx.slot(a).dia for a in aulas})
        if len(dias) > 1:
            nomes = [DIAS[d] for d in dias]
            yield Violacao(
                "AULAS_NAO_CONCENTRADAS",
                ALERTA,
                f"{rotulo} deveria ter as {len(aulas)} aulas no mesmo dia, mas está em "
                f"{', '.join(nomes[:-1])} e {nomes[-1]}.",
                {"oferta_id": oferta.id, "dias": dias},
            )
            continue

        turma = ctx.estado.turma_da(oferta)
        do_dia = sorted(
            s.ordem for s in ctx.estado.slots_do_modelo(turma.modelo_turno_id) if s.dia == dias[0]
        )
        posicoes = sorted(
            do_dia.index(o) for o in {ctx.slot(a).ordem for a in aulas} if o in do_dia
        )
        if posicoes and posicoes[-1] - posicoes[0] + 1 != len(posicoes):
            yield Violacao(
                "AULAS_NAO_CONCENTRADAS",
                ALERTA,
                f"As {len(aulas)} aulas de {rotulo} na {DIAS[dias[0]]} não estão seguidas: "
                "há outra aula ou um horário vago no meio.",
                {"oferta_id": oferta.id, "dias": dias},
            )


def _slot_do_modelo_certo(ctx: _Contexto) -> Iterator[Violacao]:
    for a in ctx.validas:
        oferta = ctx.estado.ofertas[a.oferta_id]
        turma = ctx.estado.turma_da(oferta)
        slot = ctx.slot(a)
        if slot.modelo_turno_id != turma.modelo_turno_id:
            yield Violacao(
                "HORARIO_DE_OUTRO_TURNO",
                BLOQUEANTE,
                f"{ctx.rotulo(a)} foi alocada em {slot.rotulo}, que pertence a outro "
                f"modelo de turno — a turma {turma.rotulo} não tem aula nesse horário.",
                {"alocacao_id": a.id, "slot_id": a.slot_id},
            )


def _sabado_desligado(ctx: _Contexto) -> Iterator[Violacao]:
    if ctx.config.usa_sabado:
        return
    for a in ctx.validas:
        slot = ctx.slot(a)
        if slot.dia >= 5:
            yield Violacao(
                "AULA_EM_DIA_NAO_PERMITIDO",
                BLOQUEANTE,
                f"{ctx.rotulo(a)} caiu em {DIAS[slot.dia]}, e esta unidade está "
                "configurada para não usar sábado.",
                {"alocacao_id": a.id, "dia": slot.dia},
            )


def _professor_bate_com_a_atribuicao(ctx: _Contexto) -> Iterator[Violacao]:
    for a in ctx.validas:
        oferta = ctx.estado.ofertas[a.oferta_id]
        if oferta.professor_id is None:
            yield Violacao(
                "AULA_SEM_ATRIBUICAO",
                BLOQUEANTE,
                f"{ctx.rotulo(a)} está na grade mas a oferta não tem professor atribuído.",
                {"alocacao_id": a.id, "oferta_id": oferta.id},
            )
        elif oferta.professor_id != a.professor_id:
            yield Violacao(
                "PROFESSOR_DIFERENTE_DA_ATRIBUICAO",
                BLOQUEANTE,
                f"{ctx.rotulo(a)} está com {ctx.estado.nome_professor(a.professor_id)} na "
                f"grade, mas a atribuição é de "
                f"{ctx.estado.nome_professor(oferta.professor_id)}.",
                {"alocacao_id": a.id, "oferta_id": oferta.id},
            )


# --------------------------------------------------------------------- choques


def _choque_professor(ctx: _Contexto) -> Iterator[Violacao]:
    for (professor_id, slot_id), aulas in sorted(ctx.por_professor_slot.items()):
        if len(aulas) > 1:
            yield Violacao(
                "CHOQUE_PROFESSOR",
                BLOQUEANTE,
                f"{ctx.estado.nome_professor(professor_id)} tem "
                f"{len(aulas)} aulas ao mesmo tempo em {ctx.estado.slots[slot_id].rotulo}: "
                f"{', '.join(sorted(ctx.rotulo(a) for a in aulas))}.",
                {
                    "professor_id": professor_id,
                    "slot_id": slot_id,
                    "alocacao_ids": [a.id for a in aulas],
                },
            )


def _choque_turma(ctx: _Contexto) -> Iterator[Violacao]:
    vistos: set[tuple[int, int, frozenset[int]]] = set()
    for (fluxo, slot_id), aulas in sorted(ctx.por_fluxo_slot.items(), key=lambda kv: kv[0][1]):
        if len(aulas) <= 1:
            continue
        turma_id, _sub = fluxo
        # Uma aula de turma inteira colidindo com outra aparece nos dois fluxos;
        # reportar uma vez so'.
        chave = (turma_id, slot_id, frozenset(a.id for a in aulas))
        if chave in vistos:
            continue
        vistos.add(chave)
        yield Violacao(
            "CHOQUE_TURMA",
            BLOQUEANTE,
            f"A turma {ctx.estado.turmas[turma_id].rotulo} tem "
            f"{len(aulas)} aulas ao mesmo tempo em {ctx.estado.slots[slot_id].rotulo}: "
            f"{', '.join(sorted(ctx.rotulo(a) for a in aulas))}.",
            {"turma_id": turma_id, "slot_id": slot_id, "alocacao_ids": [a.id for a in aulas]},
        )


def _choque_espaco(ctx: _Contexto) -> Iterator[Violacao]:
    for (espaco_id, slot_id), aulas in sorted(ctx.por_espaco_slot.items()):
        if len(aulas) > 1:
            espaco = ctx.estado.espacos.get(espaco_id)
            yield Violacao(
                "CHOQUE_ESPACO",
                BLOQUEANTE,
                f"{espaco.nome if espaco else f'Espaço {espaco_id}'} está com "
                f"{len(aulas)} aulas ao mesmo tempo em {ctx.estado.slots[slot_id].rotulo}: "
                f"{', '.join(sorted(ctx.rotulo(a) for a in aulas))}.",
                {
                    "espaco_id": espaco_id,
                    "slot_id": slot_id,
                    "alocacao_ids": [a.id for a in aulas],
                },
            )


def _espaco_adequado(ctx: _Contexto) -> Iterator[Violacao]:
    for a in ctx.validas:
        oferta = ctx.estado.ofertas[a.oferta_id]
        disciplina = ctx.estado.disciplina_da(oferta)
        turma = ctx.estado.turma_da(oferta)
        # Subturma leva metade dos alunos, arredondando para cima.
        alunos = turma.qtd_alunos if oferta.subturma is None else -(-turma.qtd_alunos // 2)

        if disciplina.remota:
            if a.espaco_id is not None:
                espaco = ctx.estado.espacos.get(a.espaco_id)
                yield Violacao(
                    "ESPACO_EM_AULA_REMOTA",
                    ALERTA,
                    f"{ctx.rotulo(a)} é remota e não precisa de sala, mas está ocupando "
                    f"{espaco.nome if espaco else a.espaco_id}.",
                    {"alocacao_id": a.id, "espaco_id": a.espaco_id},
                )
            continue

        if a.espaco_id is None:
            yield Violacao(
                "SEM_ESPACO",
                BLOQUEANTE,
                f"{ctx.rotulo(a)} é presencial e está sem sala em {ctx.slot(a).rotulo}.",
                {"alocacao_id": a.id},
            )
            continue

        espaco = ctx.estado.espacos.get(a.espaco_id)
        if espaco is None:
            continue  # ja' reportado por _referencias_quebradas

        if disciplina.precisa_laboratorio and espaco.tipo != TipoEspaco.LABORATORIO:
            yield Violacao(
                "ESPACO_INCOMPATIVEL",
                BLOQUEANTE,
                f"{ctx.rotulo(a)} precisa de laboratório, mas está em {espaco.nome}, "
                "que é sala comum.",
                {"alocacao_id": a.id, "espaco_id": espaco.id},
            )
        elif disciplina.precisa_laboratorio:
            exigido = (disciplina.tipo_laboratorio or "").strip().lower()
            tem = (espaco.tipo_laboratorio or "").strip().lower()
            if exigido and tem != exigido:
                yield Violacao(
                    "ESPACO_INCOMPATIVEL",
                    BLOQUEANTE,
                    f"{ctx.rotulo(a)} precisa de laboratório de {disciplina.tipo_laboratorio}, "
                    f"mas {espaco.nome} é de {espaco.tipo_laboratorio or 'tipo não informado'}.",
                    {"alocacao_id": a.id, "espaco_id": espaco.id},
                )

        if espaco.capacidade < alunos:
            yield Violacao(
                "CAPACIDADE_INSUFICIENTE",
                ALERTA,
                f"{ctx.rotulo(a)} tem {alunos} alunos e {espaco.nome} comporta "
                f"{espaco.capacidade}.",
                {"alocacao_id": a.id, "espaco_id": espaco.id, "alunos": alunos},
            )


def _disponibilidade(ctx: _Contexto) -> Iterator[Violacao]:
    for a in ctx.validas:
        if (
            ctx.estado.status_disponibilidade(a.professor_id, a.slot_id)
            == StatusDisponibilidade.INDISPONIVEL
        ):
            yield Violacao(
                "PROFESSOR_INDISPONIVEL",
                BLOQUEANTE,
                f"{ctx.estado.nome_professor(a.professor_id)} marcou "
                f"{ctx.slot(a).rotulo} como indisponível, mas tem {ctx.rotulo(a)} nesse horário.",
                {"alocacao_id": a.id, "professor_id": a.professor_id, "slot_id": a.slot_id},
            )


def _divisao_de_turma(ctx: _Contexto) -> Iterator[Violacao]:
    """PARALELA: A e B no mesmo horario. SEQUENCIAL com o mesmo professor:
    horarios diferentes (o choque de professor ja' cobre o resto)."""
    por_disciplina_turma: dict[tuple[int, int], list] = defaultdict(list)
    for oferta in ctx.estado.ofertas.values():
        if oferta.subturma:
            por_disciplina_turma[(oferta.disciplina_id, oferta.turma_id)].append(oferta)

    for (disciplina_id, _turma_id), ofertas in sorted(por_disciplina_turma.items()):
        disciplina = ctx.estado.disciplinas[disciplina_id]
        if len(ofertas) < 2 or disciplina.modo_divisao == ModoDivisao.INDIFERENTE:
            continue
        a, b = sorted(ofertas, key=lambda o: o.subturma or "")
        slots_a = {x.slot_id for x in ctx.por_oferta.get(a.id, [])}
        slots_b = {x.slot_id for x in ctx.por_oferta.get(b.id, [])}
        if not slots_a or not slots_b:
            continue

        if disciplina.modo_divisao == ModoDivisao.PARALELA and slots_a != slots_b:
            yield Violacao(
                "DIVISAO_PARALELA_SEPARADA",
                ALERTA,
                f"{disciplina.sigla} em {ctx.estado.turma_da(a).rotulo} está marcada como "
                "divisão paralela, mas as turmas A e B caíram em horários diferentes.",
                {"disciplina_id": disciplina_id, "ofertas": [a.id, b.id]},
            )
        if disciplina.modo_divisao == ModoDivisao.SEQUENCIAL and slots_a & slots_b:
            yield Violacao(
                "DIVISAO_SEQUENCIAL_SOBREPOSTA",
                BLOQUEANTE,
                f"{disciplina.sigla} em {ctx.estado.turma_da(a).rotulo} está marcada como "
                "divisão sequencial, mas as turmas A e B coincidem em "
                f"{len(slots_a & slots_b)} horário(s).",
                {"disciplina_id": disciplina_id, "ofertas": [a.id, b.id]},
            )


# ----------------------------------------------------------- carga e jornada


def _carga_semanal(ctx: _Contexto) -> Iterator[Violacao]:
    contagem: dict[int, int] = defaultdict(int)
    for a in ctx.validas:
        contagem[a.professor_id] += 1

    for professor_id, aulas in sorted(contagem.items()):
        vinculo = ctx.estado.vinculos.get(professor_id)
        limite = (
            vinculo.carga_max(ctx.config.carga_max_semanal)
            if vinculo
            else ctx.config.carga_max_semanal
        )
        if aulas > limite:
            yield Violacao(
                "CARGA_ACIMA_DO_LIMITE",
                BLOQUEANTE,
                f"{ctx.estado.nome_professor(professor_id)} está com {aulas} aulas semanais "
                f"nesta unidade e o limite do vínculo é {limite}.",
                {"professor_id": professor_id, "aulas": aulas, "limite": limite},
            )


def _linha_do_tempo(ctx: _Contexto) -> dict[int, dict[int, list[tuple[int, int, str, int]]]]:
    """Por professor e dia: `(inicio_min, fim_min, rotulo, unidade_id)` de todas as
    unidades do escopo, ordenado. Base da interjornada, do deslocamento e do
    choque entre unidades."""
    agenda: dict[int, dict[int, list[tuple[int, int, str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for a in ctx.validas:
        slot = ctx.slot(a)
        agenda[a.professor_id][slot.dia].append(
            (slot.inicio_min, slot.fim_min, ctx.rotulo(a), ctx.estado.unidade_id)
        )
    for o in ctx.estado.ocupacoes_externas:
        agenda[o.professor_id][o.dia].append((o.inicio_min, o.fim_min, o.rotulo, o.unidade_id))
    for dias in agenda.values():
        for lista in dias.values():
            lista.sort()
    return agenda


def _entre_unidades(ctx: _Contexto) -> Iterator[Violacao]:
    nomes = {ctx.estado.unidade_id: ctx.estado.unidade_nome}
    for o in ctx.estado.ocupacoes_externas:
        nomes[o.unidade_id] = o.unidade_nome

    deslocamento = ctx.config.deslocamento_entre_unidades_min

    for professor_id, dias in sorted(_linha_do_tempo(ctx).items()):
        for dia, eventos in sorted(dias.items()):
            for (ini_a, fim_a, rot_a, uni_a), (ini_b, _fim_b, rot_b, uni_b) in zip(
                eventos, eventos[1:], strict=False
            ):
                if uni_a == uni_b:
                    continue  # choque dentro da unidade ja' foi checado
                if ini_b < fim_a:
                    yield Violacao(
                        "CHOQUE_ENTRE_UNIDADES",
                        BLOQUEANTE,
                        f"{ctx.estado.nome_professor(professor_id)} tem {rot_a} em "
                        f"{nomes[uni_a]} e {rot_b} em {nomes[uni_b]} ao mesmo tempo na "
                        f"{DIAS[dia]}, às {hhmm(max(ini_a, ini_b))}.",
                        {"professor_id": professor_id, "dia": dia, "unidades": [uni_a, uni_b]},
                    )
                elif deslocamento and ini_b - fim_a < deslocamento:
                    yield Violacao(
                        "DESLOCAMENTO_INSUFICIENTE",
                        ALERTA,
                        f"{ctx.estado.nome_professor(professor_id)} sai de {nomes[uni_a]} às "
                        f"{hhmm(fim_a)} e entra em {nomes[uni_b]} às {hhmm(ini_b)} na "
                        f"{DIAS[dia]} — {ini_b - fim_a} min para um deslocamento que exige "
                        f"{deslocamento} min.",
                        {"professor_id": professor_id, "dia": dia, "minutos": ini_b - fim_a},
                    )


def _interjornada(ctx: _Contexto) -> Iterator[Violacao]:
    regra = ctx.config.interjornada
    if regra.modo == "off":
        return
    severidade = BLOQUEANTE if regra.modo == "rigida" else ALERTA
    minimo = regra.horas * 60

    for professor_id, dias in sorted(_linha_do_tempo(ctx).items()):
        for dia in sorted(dias):
            seguinte = dias.get(dia + 1)
            if not seguinte:
                continue
            fim = max(e[1] for e in dias[dia])
            inicio = min(e[0] for e in seguinte)
            descanso = (24 * 60 - fim) + inicio
            if descanso < minimo:
                horas = f"{descanso / 60:.1f}".replace(".", ",")
                yield Violacao(
                    "INTERJORNADA",
                    severidade,
                    f"{ctx.estado.nome_professor(professor_id)} termina {DIAS[dia]} às "
                    f"{hhmm(fim)} e começa {DIAS[dia + 1]} às {hhmm(inicio)}: "
                    f"{horas} h de descanso, abaixo das {regra.horas} h exigidas "
                    "pelo art. 66 da CLT.",
                    {
                        "professor_id": professor_id,
                        "dia": dia,
                        "descanso_min": descanso,
                        "minimo_min": minimo,
                    },
                )


def _limite_diario(ctx: _Contexto) -> Iterator[Violacao]:
    regra = ctx.config.limite_diario
    if not regra.ativo:
        return

    for (professor_id, dia), aulas in sorted(ctx.por_professor_dia.items()):
        ordens = sorted(ctx.slot(a).ordem for a in aulas)
        if len(ordens) > regra.max_intercaladas:
            yield Violacao(
                "LIMITE_DIARIO",
                BLOQUEANTE,
                f"{ctx.estado.nome_professor(professor_id)} tem {len(ordens)} aulas na "
                f"{DIAS[dia]}, acima do limite de {regra.max_intercaladas} por dia.",
                {"professor_id": professor_id, "dia": dia, "aulas": len(ordens)},
            )

        maior = atual = 1
        for anterior, seguinte in zip(ordens, ordens[1:], strict=False):
            atual = atual + 1 if seguinte == anterior + 1 else 1
            maior = max(maior, atual)
        if maior > regra.max_consecutivas:
            yield Violacao(
                "LIMITE_DIARIO",
                BLOQUEANTE,
                f"{ctx.estado.nome_professor(professor_id)} tem {maior} aulas seguidas na "
                f"{DIAS[dia]}, acima do limite de {regra.max_consecutivas} consecutivas.",
                {"professor_id": professor_id, "dia": dia, "consecutivas": maior},
            )


# ------------------------------------------------------------ qualidade (soft)


def _buracos(ocupadas: set[int], todas: list[int]) -> list[int]:
    """Ordens vazias que ainda tem aula depois no mesmo dia.

    Vazio no fim do dia nao e' janela: o professor vai embora mais cedo e a turma
    sai mais cedo — e' exatamente o que o objetivo do solver persegue.
    """
    if not ocupadas:
        return []
    ultima = max(ocupadas)
    return [o for o in todas if o < ultima and o not in ocupadas]


def _janelas_turma(ctx: _Contexto) -> Iterator[Violacao]:
    ocupacao: dict[tuple[int, int], set[int]] = defaultdict(set)
    for a in ctx.validas:
        oferta = ctx.estado.ofertas[a.oferta_id]
        ocupacao[(oferta.turma_id, ctx.slot(a).dia)].add(ctx.slot(a).ordem)

    for (turma_id, dia), ocupadas in sorted(ocupacao.items()):
        turma = ctx.estado.turmas[turma_id]
        todas = sorted(
            s.ordem
            for s in ctx.estado.slots.values()
            if s.modelo_turno_id == turma.modelo_turno_id and s.dia == dia
        )
        for ordem in _buracos(ocupadas, todas):
            yield Violacao(
                "JANELA_TURMA",
                ALERTA,
                f"A turma {turma.rotulo} tem uma janela na {DIAS[dia]}: a {ordem}ª aula está "
                "vaga e ainda há aula depois dela.",
                {"turma_id": turma_id, "dia": dia, "ordem": ordem},
            )


def _janelas_professor(ctx: _Contexto) -> Iterator[Violacao]:
    """Pelo eixo do tempo, e nao pela `ordem` do slot.

    Um professor pode dar aula de manha numa turma e a noite em outra no mesmo
    dia; as duas tem uma "1a aula", entao contar por `ordem` inventaria janelas
    que nao existem.
    """
    for (professor_id, dia), aulas in sorted(ctx.por_professor_dia.items()):
        modelos = {ctx.slot(a).modelo_turno_id for a in aulas}
        candidatos = sorted(
            {
                (s.inicio_min, s.fim_min)
                for s in ctx.estado.slots.values()
                if s.modelo_turno_id in modelos and s.dia == dia
            }
        )
        ocupados = {(ctx.slot(a).inicio_min, ctx.slot(a).fim_min) for a in aulas}
        ultimo_fim = max(f for _i, f in ocupados)
        buracos = [c for c in candidatos if c[1] <= ultimo_fim and c not in ocupados]
        if buracos:
            faixas = ", ".join(f"{hhmm(i)}–{hhmm(f)}" for i, f in buracos[:3])
            yield Violacao(
                "JANELA_PROFESSOR",
                ALERTA,
                f"{ctx.estado.nome_professor(professor_id)} tem "
                f"{len(buracos)} horário(s) vago(s) no meio da {DIAS[dia]} ({faixas}).",
                {
                    "professor_id": professor_id,
                    "dia": dia,
                    "faixas": [list(b) for b in buracos],
                },
            )


def _preferencias_nao_atendidas(ctx: _Contexto) -> Iterator[Violacao]:
    alocados: dict[int, set[int]] = defaultdict(set)
    for a in ctx.validas:
        alocados[a.professor_id].add(a.slot_id)

    preferidos: dict[int, set[int]] = defaultdict(set)
    for (professor_id, slot_id), status in ctx.estado.disponibilidade.items():
        if status == StatusDisponibilidade.PREFERENCIAL:
            preferidos[professor_id].add(slot_id)

    for professor_id, slots in sorted(preferidos.items()):
        if not alocados.get(professor_id):
            continue
        perdidos = sorted(slots - alocados[professor_id])
        if perdidos:
            exemplos = ", ".join(
                ctx.estado.slots[s].rotulo for s in perdidos[:3] if s in ctx.estado.slots
            )
            yield Violacao(
                "PREFERENCIA_NAO_ATENDIDA",
                INFO,
                f"{ctx.estado.nome_professor(professor_id)} marcou "
                f"{len(perdidos)} horário(s) como preferenciais e não recebeu aula neles"
                f"{f' ({exemplos})' if exemplos else ''}.",
                {"professor_id": professor_id, "slot_ids": perdidos},
            )


# ------------------------------------------------------------------ orquestracao

CHECAGENS = (
    _referencias_quebradas,
    _quantidade_de_aulas,
    _blocos_bem_formados,
    _blocos_por_dia,
    _concentracao,
    _slot_do_modelo_certo,
    _sabado_desligado,
    _professor_bate_com_a_atribuicao,
    _choque_professor,
    _choque_turma,
    _choque_espaco,
    _espaco_adequado,
    _disponibilidade,
    _divisao_de_turma,
    _carga_semanal,
    _entre_unidades,
    _interjornada,
    _limite_diario,
    _janelas_turma,
    _janelas_professor,
    _preferencias_nao_atendidas,
)

ORDEM_SEVERIDADE = {BLOQUEANTE: 0, ALERTA: 1, INFO: 2}


def validar(estado: GradeState, config: ConfigRegras) -> list[Violacao]:
    """Todas as violacoes da grade, das mais graves para as menos graves."""
    ctx = _Contexto(estado, config)
    violacoes = [v for checagem in CHECAGENS for v in checagem(ctx)]
    return sorted(violacoes, key=lambda v: (ORDEM_SEVERIDADE[v.severidade], v.tipo, v.mensagem))
