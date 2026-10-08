"""Pre-validacao (secao 5.1 da especificacao).

Roda **antes** do solver e captura as inviabilidades que da' para ver por
contagem, sem resolver nada. O objetivo e' trocar um `INFEASIBLE` sem explicacao
por uma frase que nomeia a entidade responsavel e sugere o que fazer.

Devolve `Violacao` — o mesmo tipo do validador — para que a UI e a tabela `Aviso`
tratem os dois do mesmo jeito.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from app.models import ModoDivisao, Severidade, StatusDisponibilidade, TipoEspaco
from app.scheduling.candidatos import slots_iniciais
from app.scheduling.domain import DIAS, GradeState, Violacao
from app.schemas import ConfigRegras
from app.services import blocos_de

BLOQUEANTE = Severidade.BLOQUEANTE
ALERTA = Severidade.ALERTA


def _dias_uteis(estado: GradeState, config: ConfigRegras, modelo_turno_id: int) -> list:
    return [s for s in estado.slots_do_modelo(modelo_turno_id) if config.usa_sabado or s.dia < 5]


# ------------------------------------------------------------------ atribuicao


def _ofertas_sem_professor(estado: GradeState, _config: ConfigRegras) -> Iterator[Violacao]:
    sem = [o for o in estado.ofertas.values() if o.professor_id is None]
    for oferta in sorted(sem, key=lambda o: o.id):
        yield Violacao(
            "OFERTA_SEM_PROFESSOR",
            BLOQUEANTE,
            f"{estado.rotulo_oferta(oferta)} não tem professor atribuído. "
            "Atribua manualmente ou use “Sugerir atribuição”.",
            {"oferta_id": oferta.id},
        )


def _professor_sem_vinculo(estado: GradeState, _config: ConfigRegras) -> Iterator[Violacao]:
    for professor_id in sorted(
        {
            o.professor_id
            for o in estado.ofertas.values()
            if o.professor_id is not None and o.professor_id not in estado.vinculos
        }
    ):
        yield Violacao(
            "PROFESSOR_SEM_VINCULO",
            BLOQUEANTE,
            f"{estado.nome_professor(professor_id)} tem aulas atribuídas mas não tem vínculo "
            f"com {estado.unidade_nome}. Sem vínculo não há pontuação nem carga máxima.",
            {"professor_id": professor_id},
        )


def _carga_atribuida(estado: GradeState, config: ConfigRegras) -> Iterator[Violacao]:
    carga: dict[int, int] = defaultdict(int)
    for oferta in estado.ofertas.values():
        if oferta.professor_id is not None:
            carga[oferta.professor_id] += estado.disciplina_da(oferta).aulas_semanais

    for professor_id, aulas in sorted(carga.items()):
        vinculo = estado.vinculos.get(professor_id)
        limite = (
            vinculo.carga_max(config.carga_max_semanal) if vinculo else config.carga_max_semanal
        )
        if aulas > limite:
            yield Violacao(
                "CARGA_ATRIBUIDA_ACIMA_DO_LIMITE",
                BLOQUEANTE,
                f"{estado.nome_professor(professor_id)} está com {aulas} aulas semanais "
                f"atribuídas e o limite do vínculo é {limite}. Remova "
                f"{aulas - limite} aula(s) ou aumente a carga máxima.",
                {"professor_id": professor_id, "atribuidas": aulas, "limite": limite},
            )


def _professor_sem_horario_suficiente(
    estado: GradeState, config: ConfigRegras
) -> Iterator[Violacao]:
    """Aulas atribuidas x horarios em que o docente pode realmente dar aula."""
    carga: dict[int, int] = defaultdict(int)
    modelos: dict[int, set[int]] = defaultdict(set)
    for oferta in estado.ofertas.values():
        if oferta.professor_id is None:
            continue
        carga[oferta.professor_id] += estado.disciplina_da(oferta).aulas_semanais
        modelos[oferta.professor_id].add(estado.turma_da(oferta).modelo_turno_id)

    for professor_id, aulas in sorted(carga.items()):
        livres = {
            (s.dia, s.inicio_min)
            for modelo in modelos[professor_id]
            for s in _dias_uteis(estado, config, modelo)
            if estado.status_disponibilidade(professor_id, s.id)
            != StatusDisponibilidade.INDISPONIVEL
        }
        if aulas > len(livres):
            yield Violacao(
                "PROFESSOR_SEM_HORARIO_SUFICIENTE",
                BLOQUEANTE,
                f"{estado.nome_professor(professor_id)} tem {aulas} aulas atribuídas mas só "
                f"{len(livres)} horário(s) disponível(is) nos turnos das turmas dele. "
                "Libere disponibilidade ou redistribua as aulas.",
                {"professor_id": professor_id, "aulas": aulas, "horarios": len(livres)},
            )


# ----------------------------------------------------------------- capacidade


def _horarios_que_a_turma_consome(estado: GradeState) -> dict[int, int]:
    """Quantos horarios da turma cada disciplina ocupa.

    Numa divisao PARALELA as subturmas A e B assistem ao mesmo tempo, entao a
    disciplina consome `aulas_semanais` horarios da turma, e nao o dobro.
    INDIFERENTE conta como paralela: a pre-validacao so' pode acusar o que e'
    inviavel em qualquer arranjo, e o solver ainda pode escolher o paralelo.
    """
    demanda: dict[int, int] = defaultdict(int)
    ja_contadas: set[tuple[int, int]] = set()
    for oferta in estado.ofertas.values():
        disciplina = estado.disciplina_da(oferta)
        simultaneas = disciplina.divisao_turma and disciplina.modo_divisao in (
            ModoDivisao.PARALELA,
            ModoDivisao.INDIFERENTE,
        )
        if simultaneas:
            chave = (oferta.turma_id, disciplina.id)
            if chave in ja_contadas:
                continue
            ja_contadas.add(chave)
        demanda[oferta.turma_id] += disciplina.aulas_semanais
    return demanda


def _aulas_por_tamanho_de_bloco(estado: GradeState) -> dict[int, dict[int, int]]:
    """`turma -> tamanho do bloco -> aulas`, com a mesma regra de subturma de
    `_horarios_que_a_turma_consome`."""
    demanda: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    ja_contadas: set[tuple[int, int]] = set()
    for oferta in estado.ofertas.values():
        disciplina = estado.disciplina_da(oferta)
        simultaneas = disciplina.divisao_turma and disciplina.modo_divisao in (
            ModoDivisao.PARALELA,
            ModoDivisao.INDIFERENTE,
        )
        if simultaneas:
            chave = (oferta.turma_id, disciplina.id)
            if chave in ja_contadas:
                continue
            ja_contadas.add(chave)
        demanda[oferta.turma_id][max(1, disciplina.tamanho_bloco)] += disciplina.aulas_semanais
    return demanda


def _capacidade_em_blocos(slots, tamanho: int) -> int:
    """Quantas aulas em blocos de `tamanho` cabem: uma geminada nunca atravessa
    intervalo, entao cada trecho contiguo (mesmo dia e `bloco_id`) comporta
    `len // tamanho` blocos e o resto e' horario solto."""
    trechos: dict[tuple[int, int], int] = defaultdict(int)
    for s in slots:
        trechos[(s.dia, s.bloco_id)] += 1
    return sum((n // tamanho) * tamanho for n in trechos.values())


def _turma_nao_cabe_no_turno(estado: GradeState, config: ConfigRegras) -> Iterator[Violacao]:
    demanda = _horarios_que_a_turma_consome(estado)
    por_bloco = _aulas_por_tamanho_de_bloco(estado)

    for turma_id, aulas in sorted(demanda.items()):
        turma = estado.turmas[turma_id]
        uteis = _dias_uteis(estado, config, turma.modelo_turno_id)
        disponiveis = len(uteis)
        if disponiveis == 0:
            yield Violacao(
                "TURNO_SEM_HORARIOS",
                BLOQUEANTE,
                f"O modelo de turno da turma {turma.rotulo} não tem nenhum horário "
                f"{'' if config.usa_sabado else 'em dia útil '}cadastrado.",
                {"turma_id": turma_id},
            )
        elif aulas > disponiveis:
            sugestao = (
                " Ative o uso de sábado nas regras da unidade ou marque alguma disciplina "
                "como remota em outro turno."
                if not config.usa_sabado
                else " Reduza a carga do período ou acrescente horários ao turno."
            )
            yield Violacao(
                "TURMA_NAO_CABE_NO_TURNO",
                BLOQUEANTE,
                f"A turma {turma.rotulo} tem {aulas} aulas semanais e o turno dela só "
                f"comporta {disponiveis}.{sugestao}",
                {"turma_id": turma_id, "aulas": aulas, "horarios": disponiveis},
            )
        else:
            # Cabe em horarios; cabe em blocos? Checagem por tamanho de bloco,
            # cada um sozinho: so' acusa o que e' impossivel em qualquer arranjo.
            for tamanho, aulas_bloco in sorted(por_bloco[turma_id].items()):
                if tamanho < 2:
                    continue
                geminadas = _capacidade_em_blocos(uteis, tamanho)
                if aulas_bloco > geminadas:
                    yield Violacao(
                        "TURMA_NAO_CABE_NO_TURNO",
                        BLOQUEANTE,
                        f"A turma {turma.rotulo} tem {aulas_bloco} aulas em blocos de "
                        f"{tamanho} e o turno dela só comporta {geminadas} assim: um bloco "
                        "nunca atravessa intervalo, e sobra horário solto em cada trecho. "
                        "Mude o tamanho do bloco das disciplinas ou os intervalos do turno.",
                        {
                            "turma_id": turma_id,
                            "aulas": aulas_bloco,
                            "tamanho_bloco": tamanho,
                            "geminadas": geminadas,
                        },
                    )


def _laboratorio_inexistente(estado: GradeState, _config: ConfigRegras) -> Iterator[Violacao]:
    labs_por_tipo: dict[str, int] = defaultdict(int)
    for espaco in estado.espacos.values():
        if espaco.tipo == TipoEspaco.LABORATORIO:
            labs_por_tipo[(espaco.tipo_laboratorio or "").strip().lower()] += 1

    exigidos: dict[str, list[str]] = defaultdict(list)
    for disciplina in estado.disciplinas.values():
        if disciplina.precisa_laboratorio:
            exigidos[(disciplina.tipo_laboratorio or "").strip().lower()].append(disciplina.sigla)

    for tipo, siglas in sorted(exigidos.items()):
        if labs_por_tipo.get(tipo, 0) == 0:
            nome = tipo or "sem tipo definido"
            yield Violacao(
                "LABORATORIO_INEXISTENTE",
                BLOQUEANTE,
                f"{', '.join(sorted(siglas))} exige(m) laboratório de {nome} e "
                f"{estado.unidade_nome} não tem nenhum desse tipo.",
                {"tipo_laboratorio": tipo, "disciplinas": sorted(siglas)},
            )


def _demanda_de_espaco(estado: GradeState, config: ConfigRegras) -> Iterator[Violacao]:
    """Aulas presenciais x (espacos compativeis × horarios).

    Checagem agregada: se a demanda ja' passa da oferta total, nenhuma
    distribuicao resolve.
    """
    horarios_por_modelo = {
        modelo: len(_dias_uteis(estado, config, modelo))
        for modelo in {t.modelo_turno_id for t in estado.turmas.values()}
    }
    if not horarios_por_modelo:
        return
    horarios = max(horarios_por_modelo.values())

    demanda_lab: dict[str, int] = defaultdict(int)
    demanda_sala = 0
    for oferta in estado.ofertas.values():
        disciplina = estado.disciplina_da(oferta)
        if disciplina.remota:
            continue
        if disciplina.precisa_laboratorio:
            demanda_lab[(disciplina.tipo_laboratorio or "").strip().lower()] += (
                disciplina.aulas_semanais
            )
        else:
            demanda_sala += disciplina.aulas_semanais

    for tipo, aulas in sorted(demanda_lab.items()):
        labs = [
            e
            for e in estado.espacos.values()
            if e.tipo == TipoEspaco.LABORATORIO
            and (e.tipo_laboratorio or "").strip().lower() == tipo
        ]
        if not labs:
            continue  # ja' reportado por _laboratorio_inexistente
        capacidade = len(labs) * horarios
        if aulas > capacidade:
            yield Violacao(
                "LABORATORIO_INSUFICIENTE",
                BLOQUEANTE,
                f"As disciplinas de laboratório de {tipo or 'tipo não definido'} somam "
                f"{aulas} aulas por semana, e {len(labs)} laboratório(s) × {horarios} "
                f"horários comportam {capacidade}. Falta(m) "
                f"{-(-(aulas - capacidade) // horarios)} laboratório(s).",
                {"tipo_laboratorio": tipo, "aulas": aulas, "capacidade": capacidade},
            )

    # Sala comum aceita tambem o que sobra de laboratorio, entao a conta usa
    # todos os espacos presenciais.
    total_espacos = len(estado.espacos)
    if total_espacos and demanda_sala > total_espacos * horarios:
        yield Violacao(
            "ESPACO_INSUFICIENTE",
            BLOQUEANTE,
            f"As aulas presenciais que precisam de sala somam {demanda_sala} por semana e "
            f"{total_espacos} espaço(s) × {horarios} horários comportam "
            f"{total_espacos * horarios}.",
            {"aulas": demanda_sala, "capacidade": total_espacos * horarios},
        )
    if total_espacos == 0 and demanda_sala:
        yield Violacao(
            "SEM_ESPACOS_CADASTRADOS",
            BLOQUEANTE,
            f"{estado.unidade_nome} não tem nenhuma sala ou laboratório cadastrado, e há "
            f"{demanda_sala} aulas presenciais por semana.",
            {"aulas": demanda_sala},
        )


def _capacidade_das_salas(estado: GradeState, _config: ConfigRegras) -> Iterator[Violacao]:
    for oferta in sorted(estado.ofertas.values(), key=lambda o: o.id):
        disciplina = estado.disciplina_da(oferta)
        if disciplina.remota:
            continue
        turma = estado.turma_da(oferta)
        alunos = turma.qtd_alunos if oferta.subturma is None else -(-turma.qtd_alunos // 2)
        if not any(e.atende(disciplina, alunos) for e in estado.espacos.values()):
            yield Violacao(
                "SEM_ESPACO_COMPATIVEL",
                BLOQUEANTE,
                f"Não há espaço que atenda {estado.rotulo_oferta(oferta)}: são {alunos} alunos"
                + (
                    f" e é preciso laboratório de {disciplina.tipo_laboratorio}."
                    if disciplina.precisa_laboratorio
                    else "."
                ),
                {"oferta_id": oferta.id, "alunos": alunos},
            )


# ------------------------------------------------------------------- horarios


def _oferta_sem_horario_possivel(estado: GradeState, config: ConfigRegras) -> Iterator[Violacao]:
    """A checagem mais util: usa o mesmo filtro que o solver usaria."""
    for oferta in sorted(estado.ofertas.values(), key=lambda o: o.id):
        if oferta.professor_id is None:
            continue  # ja' reportado
        disciplina = estado.disciplina_da(oferta)
        for tamanho in sorted(
            set(blocos_de(disciplina.aulas_semanais, disciplina.tamanho_bloco)), reverse=True
        ):
            recusas: dict[int, object] = {}
            possiveis = slots_iniciais(estado, config, oferta, tamanho, recusas=recusas)
            if possiveis:
                continue
            motivos = sorted({r.detalhe for r in recusas.values()})  # type: ignore[attr-defined]
            yield Violacao(
                "SEM_HORARIO_POSSIVEL",
                BLOQUEANTE,
                f"Não há onde encaixar um bloco de {tamanho} aula(s) de "
                f"{estado.rotulo_oferta(oferta)} com "
                f"{estado.nome_professor(oferta.professor_id)}: " + "; ".join(motivos) + ".",
                {"oferta_id": oferta.id, "tamanho_bloco": tamanho},
            )
            break

        # Aviso quando ha' saida, mas apertada demais para sobrar escolha.
        blocos = blocos_de(disciplina.aulas_semanais, disciplina.tamanho_bloco)
        if len(blocos) > 1:
            maiores = slots_iniciais(estado, config, oferta, blocos[0])
            dias = {s.dia for s in maiores}
            if maiores and len(dias) < len(blocos) and disciplina.limite_blocos_por_dia == 1:
                yield Violacao(
                    "POUCOS_DIAS_PARA_A_DISCIPLINA",
                    BLOQUEANTE,
                    f"{estado.rotulo_oferta(oferta)} precisa de {len(blocos)} blocos em dias "
                    f"diferentes, mas {estado.nome_professor(oferta.professor_id)} só tem "
                    f"horário em {len(dias)} dia(s): "
                    f"{', '.join(DIAS[d] for d in sorted(dias))}.",
                    {"oferta_id": oferta.id, "dias": sorted(dias)},
                )


def _turma_sem_ofertas(estado: GradeState, _config: ConfigRegras) -> Iterator[Violacao]:
    com_oferta = {o.turma_id for o in estado.ofertas.values()}
    for turma_id in sorted(set(estado.turmas) - com_oferta):
        yield Violacao(
            "TURMA_SEM_OFERTAS",
            ALERTA,
            f"A turma {estado.turmas[turma_id].rotulo} não tem nenhuma disciplina no período "
            "dela e vai ficar fora da grade.",
            {"turma_id": turma_id},
        )


def _cabe_seguido(slots_do_dia: list, tamanhos: list[int]) -> bool:
    """Os blocos cabem em horarios seguidos deste dia, cada um dentro de um
    trecho sem intervalo? `blocos_de` devolve blocos iguais e, no maximo, um
    menor no fim: basta testar esse menor em cada posicao da fila."""
    slots = sorted(slots_do_dia, key=lambda s: s.ordem)
    ordens = {tuple(tamanhos[:i] + tamanhos[-1:] + tamanhos[i:-1]) for i in range(len(tamanhos))}
    for inicio in range(len(slots)):
        for ordem in ordens:
            pos = inicio
            for tamanho in ordem:
                trecho = slots[pos : pos + tamanho]
                if len(trecho) < tamanho or len({s.bloco_id for s in trecho}) != 1:
                    break
                pos += tamanho
            else:
                return True
    return False


def _concentracao_nao_cabe(estado: GradeState, config: ConfigRegras) -> Iterator[Violacao]:
    """O que a concentracao pedida nao vai conseguir. Alerta, nao impedimento:
    o solver concentra o que cabe e espalha o resto (D123) — mas quem marcou
    seis disciplinas precisa saber, antes de gerar, que uma fica de fora."""
    por_turma: dict[int, list] = defaultdict(list)
    vistas: set[tuple[int, int]] = set()
    for oferta in sorted(estado.ofertas.values(), key=lambda o: o.id):
        disciplina = estado.disciplina_da(oferta)
        chave = (oferta.turma_id, disciplina.id)
        tamanhos = blocos_de(disciplina.aulas_semanais, disciplina.tamanho_bloco)
        if not disciplina.concentrar_no_dia or chave in vistas or len(tamanhos) < 2:
            continue
        vistas.add(chave)
        por_turma[oferta.turma_id].append((oferta, disciplina, tamanhos))

    for turma_id, marcadas in sorted(por_turma.items()):
        turma = estado.turmas[turma_id]
        por_dia: dict[int, list] = defaultdict(list)
        for slot in _dias_uteis(estado, config, turma.modelo_turno_id):
            por_dia[slot.dia].append(slot)
        if not por_dia:
            continue

        cabem = []
        for oferta, disciplina, tamanhos in marcadas:
            if any(_cabe_seguido(slots, tamanhos) for slots in por_dia.values()):
                cabem.append(disciplina)
                continue
            maior_dia = max(len(slots) for slots in por_dia.values())
            yield Violacao(
                "CONCENTRACAO_NAO_CABE",
                ALERTA,
                f"{estado.rotulo_oferta(oferta)} está marcada para ter as "
                f"{disciplina.aulas_semanais} aulas seguidas no mesmo dia, mas nenhum dia do "
                f"turno comporta: o dia tem {maior_dia} horários e um bloco de "
                f"{disciplina.tamanho_bloco} não atravessa intervalo. Ela vai ficar espalhada "
                "pela semana.",
                {"oferta_id": oferta.id, "aulas": disciplina.aulas_semanais},
            )

        # Teto de quantas concentradas a semana comporta: em cada dia, quantas
        # das menores cabem. E' um teto (ignora intervalo e professor), entao
        # "pelo menos N ficam de fora" e' sempre verdade.
        aulas = sorted(d.aulas_semanais for d in cabem)
        teto = 0
        for slots in por_dia.values():
            livres = len(slots)
            for a in aulas:
                if a > livres:
                    break
                livres -= a
                teto += 1
        if len(cabem) > teto:
            de_fora = len(cabem) - teto
            turno = f" ({turma.turno})" if turma.turno else ""
            yield Violacao(
                "CONCENTRACOES_DEMAIS",
                ALERTA,
                f"A turma {turma.rotulo}{turno} tem {len(cabem)} disciplinas marcadas para "
                f"concentrar, mas o turno só comporta {teto} na semana. O sistema concentra "
                f"as que couberem e pelo menos {de_fora} "
                f"{'fica espalhada' if de_fora == 1 else 'ficam espalhadas'}; a grade avisa "
                "qual.",
                {"turma_id": turma_id, "marcadas": len(cabem), "cabem": teto},
            )


CHECAGENS = (
    _ofertas_sem_professor,
    _professor_sem_vinculo,
    _carga_atribuida,
    _professor_sem_horario_suficiente,
    _turma_nao_cabe_no_turno,
    _concentracao_nao_cabe,
    _turma_sem_ofertas,
    _laboratorio_inexistente,
    _demanda_de_espaco,
    _capacidade_das_salas,
    _oferta_sem_horario_possivel,
)

ORDEM_SEVERIDADE = {Severidade.BLOQUEANTE: 0, Severidade.ALERTA: 1, Severidade.INFO: 2}


def prevalidar(estado: GradeState, config: ConfigRegras) -> list[Violacao]:
    """Tudo que impede a grade de existir, antes de acordar o solver."""
    violacoes = [v for checagem in CHECAGENS for v in checagem(estado, config)]
    return sorted(violacoes, key=lambda v: (ORDEM_SEVERIDADE[v.severidade], v.tipo, v.mensagem))
