"""Etapa 5: o solver CP-SAT (app/scheduling/solver.py)."""

from dataclasses import replace

import pytest

from app.models import ModoDivisao, Severidade, TipoEspaco
from app.scheduling.diagnose import diagnosticar
from app.scheduling.domain import AlocacaoInfo
from app.scheduling.solver import Parametros, decompor_em_blocos, resolver
from app.scheduling.validator import validar
from tests.fabrica import Cenario, slot_id


def _resolver(c: Cenario, **kw):
    return resolver(c.estado, c.config, Parametros(tempo_limite_s=kw.pop("tempo", 15), **kw))


def _aplicar(c: Cenario, solucao) -> None:
    """Coloca a solucao no estado para o validador poder examinar."""
    c.estado.alocacoes = [
        AlocacaoInfo(
            id=i,
            oferta_id=a.oferta_id,
            professor_id=a.professor_id,
            slot_id=a.slot_id,
            espaco_id=a.espaco_id,
            bloco_idx=a.bloco_idx,
        )
        for i, a in enumerate(solucao.alocacoes, start=1)
    ]


def _slots_de(solucao, oferta_id: int) -> set[int]:
    return {a.slot_id for a in solucao.alocacoes if a.oferta_id == oferta_id}


# ------------------------------------------------------------------- basico


def test_decomposicao_em_blocos_segue_a_matriz():
    c = Cenario()
    prof = c.professor("Ana")
    turma = c.turma()
    c.oferta(turma, c.disciplina("ALP", aulas=4, tamanho_bloco=2), prof)
    c.oferta(turma, c.disciplina("ING", aulas=5, tamanho_bloco=2), prof)

    tamanhos = sorted(b.tamanho for b in decompor_em_blocos(c.estado))
    assert tamanhos == [1, 2, 2, 2, 2]


def test_oferta_sem_professor_nao_gera_bloco():
    c = Cenario()
    c.oferta(c.turma(), c.disciplina("ALP"))
    assert decompor_em_blocos(c.estado) == []


def test_grade_simples_fica_otima_e_sem_violacao():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    c.oferta(turma, c.disciplina("ALP", aulas=4), prof)

    solucao = _resolver(c)
    assert solucao.status == "OPTIMAL"
    assert len(solucao.alocacoes) == 4

    _aplicar(c, solucao)
    assert [v for v in validar(c.estado, c.config) if v.severidade == Severidade.BLOQUEANTE] == []


def test_resultado_e_reproduzivel_com_um_worker():
    """Com varios workers o CP-SAT e' uma corrida entre threads e dois otimos de
    mesmo custo podem sair em execucoes diferentes. Reprodutibilidade exata
    exige `workers=1`."""

    def montar() -> Cenario:
        c = Cenario()
        c.espaco("Sala 1")
        c.espaco("Sala 2")
        turma = c.turma()
        for i in range(4):
            prof = c.professor(f"P{i}")
            c.oferta(turma, c.disciplina(f"D{i}", aulas=4), prof)
        return c

    a, b = _resolver(montar(), workers=1), _resolver(montar(), workers=1)
    assert sorted((x.oferta_id, x.slot_id) for x in a.alocacoes) == sorted(
        (x.oferta_id, x.slot_id) for x in b.alocacoes
    )


def test_custo_otimo_e_o_mesmo_mesmo_com_varios_workers():
    """O que nao muda entre execucoes e' o **custo** do otimo."""

    def montar() -> Cenario:
        c = Cenario()
        c.espaco("Sala 1")
        c.espaco("Sala 2")
        turma = c.turma()
        for i in range(4):
            c.oferta(turma, c.disciplina(f"D{i}", aulas=4), c.professor(f"P{i}"))
        return c

    a, b = _resolver(montar()), _resolver(montar())
    assert a.status == b.status == "OPTIMAL"
    assert a.objetivo == b.objetivo


# ------------------------------------------------------------ restricoes rigidas


def test_bloco_nunca_atravessa_o_intervalo():
    """No turno noturno so' (1,2) e (3,4) sao geminaveis."""
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=2), prof)

    solucao = _resolver(c)
    ordens = sorted(c.estado.slots[s].ordem for s in _slots_de(solucao, oferta))
    assert ordens in ([1, 2], [3, 4])


def test_professor_nunca_fica_em_duas_turmas_ao_mesmo_tempo():
    c = Cenario()
    c.espaco("Sala 1")
    c.espaco("Sala 2")
    prof = c.professor("Ana")
    t1, t2 = c.turma("1o sem"), c.turma("2o sem")
    c.oferta(t1, c.disciplina("A", aulas=4), prof)
    c.oferta(t2, c.disciplina("B", aulas=4), prof)

    solucao = _resolver(c)
    _aplicar(c, solucao)
    assert "CHOQUE_PROFESSOR" not in {v.tipo for v in validar(c.estado, c.config)}


def test_laboratorio_e_respeitado():
    c = Cenario()
    c.espaco("Sala 1")
    lab = c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=4, laboratorio="info"), prof)

    solucao = _resolver(c)
    assert {a.espaco_id for a in solucao.alocacoes if a.oferta_id == oferta} == {lab}


def test_disciplina_remota_nao_ocupa_espaco():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("MCT", aulas=4, remota=True), prof)

    solucao = _resolver(c)
    assert {a.espaco_id for a in solucao.alocacoes if a.oferta_id == oferta} == {None}


def test_horario_indisponivel_nunca_e_usado():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    for dia in (0, 1, 2):
        c.indisponivel(prof, dia=dia)
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=4), prof)

    solucao = _resolver(c)
    dias = {c.estado.slots[s].dia for s in _slots_de(solucao, oferta)}
    assert dias <= {3, 4}


def test_max_blocos_por_dia_espalha_a_disciplina():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=4, max_blocos_por_dia=1), prof)

    solucao = _resolver(c)
    dias = [c.estado.slots[s].dia for s in _slots_de(solucao, oferta)]
    assert len(set(dias)) == 2, "4 aulas em blocos de 2, um por dia = dois dias"


def test_aula_em_outra_unidade_bloqueia_o_horario():
    c = Cenario(dias=1)
    c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("MAT", aulas=2), prof)
    c.aula_em_outra_unidade(prof, dia=0, inicio_min=19 * 60, fim_min=20 * 60 + 40)

    solucao = _resolver(c)
    assert solucao.status == "OPTIMAL"
    ordens = sorted(c.estado.slots[s].ordem for s in _slots_de(solucao, oferta))
    assert ordens == [3, 4], "as duas primeiras aulas estao ocupadas na outra unidade"


def test_sabado_so_e_usado_quando_a_unidade_permite():
    c = Cenario(dias=6, usa_sabado=False)
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=2), prof)

    solucao = _resolver(c)
    assert all(c.estado.slots[s].dia < 5 for s in _slots_de(solucao, oferta))


# ------------------------------------------------------------ divisao de turma


def test_divisao_paralela_cai_no_mesmo_horario():
    c = Cenario()
    lab1 = c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    lab2 = c.espaco("Lab 2", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    pa, pb = c.professor("Ana"), c.professor("Bruno")
    turma = c.turma(alunos=36)
    pw = c.disciplina("PW", aulas=4, laboratorio="info", divisao=ModoDivisao.PARALELA)
    a = c.oferta(turma, pw, pa, subturma="A")
    b = c.oferta(turma, pw, pb, subturma="B")

    solucao = _resolver(c)
    assert solucao.status == "OPTIMAL"
    assert _slots_de(solucao, a) == _slots_de(solucao, b)

    # no mesmo horario, cada subturma em um laboratorio diferente
    por_slot: dict[int, set[int | None]] = {}
    for x in solucao.alocacoes:
        por_slot.setdefault(x.slot_id, set()).add(x.espaco_id)
    assert all(espacos == {lab1, lab2} for espacos in por_slot.values())


def test_divisao_sequencial_cai_em_horarios_diferentes():
    c = Cenario()
    c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    prof = c.professor("Ana")
    turma = c.turma(alunos=36)
    ai = c.disciplina("AI", aulas=2, laboratorio="info", divisao=ModoDivisao.SEQUENCIAL)
    a = c.oferta(turma, ai, prof, subturma="A")
    b = c.oferta(turma, ai, prof, subturma="B")

    solucao = _resolver(c)
    assert solucao.status == "OPTIMAL"
    assert not (_slots_de(solucao, a) & _slots_de(solucao, b))


def test_turma_inteira_nao_coincide_com_subturma():
    c = Cenario()
    c.espaco("Sala 1")
    lab = c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    lab2 = c.espaco("Lab 2", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    pa, pb, pc = c.professor("A"), c.professor("B"), c.professor("C")
    turma = c.turma(alunos=36)
    pw = c.disciplina("PW", aulas=2, laboratorio="info", divisao=ModoDivisao.PARALELA)
    inteira = c.disciplina("BD", aulas=2)
    sub_a = c.oferta(turma, pw, pa, subturma="A")
    c.oferta(turma, pw, pb, subturma="B")
    bd = c.oferta(turma, inteira, pc)
    assert lab and lab2

    solucao = _resolver(c)
    assert not (_slots_de(solucao, sub_a) & _slots_de(solucao, bd))


# ------------------------------------------------------------------ objetivo


def test_quando_da_para_nao_ter_janela_o_solver_nao_deixa_nenhuma():
    """4 disciplinas de 4 aulas em 5 noites de 4 aulas: cabe sem buraco."""
    c = Cenario()
    for i in range(4):
        c.espaco(f"Sala {i}")
    turma = c.turma()
    for i in range(4):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4), c.professor(f"P{i}"))

    solucao = _resolver(c)
    assert solucao.status == "OPTIMAL"
    assert solucao.metricas["janela_turma"] == 0


def test_horario_vago_vai_para_o_fim_do_dia():
    """Uma turma com 6 aulas em dois dias de 4: o vazio fica no fim, nao no meio."""
    c = Cenario(dias=2)
    c.espaco("Sala 1")
    c.espaco("Sala 2")
    turma = c.turma()
    c.oferta(turma, c.disciplina("A", aulas=4), c.professor("Pa"))
    c.oferta(turma, c.disciplina("B", aulas=2), c.professor("Pb"))

    solucao = _resolver(c)
    assert solucao.metricas["janela_turma"] == 0

    ocupadas: dict[int, set[int]] = {}
    for a in solucao.alocacoes:
        slot = c.estado.slots[a.slot_id]
        ocupadas.setdefault(slot.dia, set()).add(slot.ordem)
    for dia, ordens in ocupadas.items():
        assert ordens == set(range(1, len(ordens) + 1)), f"dia {dia} com buraco: {ordens}"


def test_janela_inevitavel_fica_no_ultimo_horario_possivel():
    """5 aulas em blocos de 2 num dia de 4 horarios + outro dia: sobra 1 vago,
    e ele precisa ficar no fim de um dos dias."""
    c = Cenario(dias=2)
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    c.oferta(turma, c.disciplina("A", aulas=5, tamanho_bloco=2, max_blocos_por_dia=2), prof)

    solucao = _resolver(c)
    assert solucao.status in ("OPTIMAL", "FEASIBLE")
    assert solucao.metricas["janela_turma"] == 0

    _aplicar(c, solucao)
    assert "JANELA_TURMA" not in {v.tipo for v in validar(c.estado, c.config)}


def test_horario_preferencial_do_melhor_classificado_e_atendido():
    """Ana (90) e Bruno (50) querem a segunda; so' um cabe. O peso da pontuacao
    faz o solver preferir atender Ana."""
    c = Cenario(dias=2)
    c.espaco("Sala 1")
    ana = c.professor("Ana", pontuacao=90)
    bruno = c.professor("Bruno", pontuacao=50)
    t1, t2 = c.turma("1o sem"), c.turma("2o sem")
    oferta_ana = c.oferta(t1, c.disciplina("A", aulas=2), ana)
    c.oferta(t2, c.disciplina("B", aulas=2), bruno)
    c.preferencial(ana, dia=0, ordens=[1, 2])
    c.preferencial(bruno, dia=0, ordens=[1, 2])

    solucao = _resolver(c)
    slots_ana = _slots_de(solucao, oferta_ana)
    assert slots_ana == {slot_id(0, 1), slot_id(0, 2)}


def test_modo_lexicografico_tambem_zera_as_janelas():
    c = Cenario()
    c.config.modo_objetivo = "lexicografico"
    for i in range(3):
        c.espaco(f"Sala {i}")
    turma = c.turma()
    for i in range(3):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4), c.professor(f"P{i}"))

    solucao = _resolver(c, tempo=20)
    assert solucao.viavel
    _aplicar(c, solucao)
    assert "JANELA_TURMA" not in {v.tipo for v in validar(c.estado, c.config)}


def test_estabilidade_mantem_a_grade_anterior_quando_ela_ja_e_otima():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=4), prof)

    primeira = _resolver(c)
    anterior = [
        AlocacaoInfo(
            id=i,
            oferta_id=a.oferta_id,
            professor_id=a.professor_id,
            slot_id=a.slot_id,
            espaco_id=a.espaco_id,
            bloco_idx=a.bloco_idx,
        )
        for i, a in enumerate(primeira.alocacoes, start=1)
    ]
    segunda = resolver(
        c.estado,
        c.config,
        Parametros(tempo_limite_s=15, grade_anterior=anterior),
    )
    assert _slots_de(segunda, oferta) == _slots_de(primeira, oferta)
    assert segunda.metricas["estabilidade"] == 0


# --------------------------------------------------------------------- fixadas


def test_aula_fixada_nao_sai_do_lugar():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=4, max_blocos_por_dia=1), prof)

    # trava o primeiro bloco na quinta-feira
    for ordem in (3, 4):
        c.estado.alocacoes.append(
            AlocacaoInfo(
                id=100 + ordem,
                oferta_id=oferta,
                professor_id=prof,
                slot_id=slot_id(3, ordem),
                espaco_id=sala,
                bloco_idx=0,
                fixada=True,
            )
        )

    solucao = _resolver(c)
    do_bloco_zero = {a.slot_id for a in solucao.alocacoes if a.bloco_idx == 0}
    assert do_bloco_zero == {slot_id(3, 3), slot_id(3, 4)}


def test_desligar_manter_fixadas_libera_a_aula():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=2), prof)
    c.estado.alocacoes.append(
        AlocacaoInfo(
            id=1,
            oferta_id=oferta,
            professor_id=prof,
            slot_id=slot_id(4, 3),
            espaco_id=sala,
            bloco_idx=0,
            fixada=True,
        )
    )

    presa = _resolver(c)
    assert _slots_de(presa, oferta) == {slot_id(4, 3), slot_id(4, 4)}

    livre = resolver(c.estado, c.config, Parametros(tempo_limite_s=15, manter_fixadas=False))
    assert _slots_de(livre, oferta) != {slot_id(4, 3), slot_id(4, 4)}


# ----------------------------------------------------- limites configuraveis


def test_interjornada_rigida_e_respeitada_pelo_solver():
    c = Cenario(dias=2)
    c.config.interjornada.modo = "rigida"
    c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("MAT", aulas=2), prof)
    # aula das 07h00 na terca em outra unidade: a noite de segunda fica proibida
    c.aula_em_outra_unidade(prof, dia=1, inicio_min=7 * 60, fim_min=7 * 60 + 50)

    solucao = _resolver(c)
    _aplicar(c, solucao)
    assert "INTERJORNADA" not in {v.tipo for v in validar(c.estado, c.config)}
    assert all(c.estado.slots[s].dia != 0 for s in _slots_de(solucao, oferta))


def test_limite_diario_de_consecutivas_quando_ligado():
    c = Cenario(dias=2)
    c.config.limite_diario.ativo = True
    c.config.limite_diario.max_consecutivas = 2
    c.config.limite_diario.max_intercaladas = 8
    c.espaco("Sala 1")
    c.espaco("Sala 2")
    prof = c.professor("Ana")
    t1, t2 = c.turma("1o sem"), c.turma("2o sem")
    c.oferta(t1, c.disciplina("A", aulas=2), prof)
    c.oferta(t2, c.disciplina("B", aulas=2), prof)

    solucao = _resolver(c)
    _aplicar(c, solucao)
    assert "LIMITE_DIARIO" not in {v.tipo for v in validar(c.estado, c.config)}


# ------------------------------------------------------------- inviabilidade


def test_solver_devolve_inviavel_quando_nao_ha_saida():
    c = Cenario(dias=1)
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    # 3 disciplinas de 4 aulas num unico dia de 4 horarios
    for i in range(3):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4), prof)

    assert not _resolver(c).viavel


def test_diagnostico_nomeia_o_culpado():
    from app.scheduling.diagnose import diagnosticar

    c = Cenario(dias=1)
    c.espaco("Sala 1")
    prof = c.professor("Ana Ribeiro", carga_max_semanal=40)
    turma = c.turma()
    for i in range(3):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4), prof)

    diag = diagnosticar(c.estado, c.config, Parametros(tempo_limite_s=10))
    assert diag.mensagem
    nomes = {c_["nome"] for c_ in diag.culpados}
    assert nomes & {"Ana Ribeiro", "DSM 1o sem"}, diag.mensagem
    assert diag.acoes


def test_diagnostico_de_oferta_sem_horario_algum():
    from app.scheduling.diagnose import diagnosticar

    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    for dia in range(5):
        c.indisponivel(prof, dia=dia)
    c.oferta(turma, c.disciplina("ALP", aulas=2), prof)

    diag = diagnosticar(c.estado, c.config, Parametros(tempo_limite_s=10))
    assert "Não há nenhum horário possível" in diag.mensagem
    assert "ALP (DSM 1o sem)" in diag.mensagem


# ------------------------------------------- contrato entre solver e validador


@pytest.mark.parametrize("semente", [1, 7, 13, 42, 99])
def test_validador_nao_acha_violacao_rigida_no_que_o_solver_produz(semente):
    """Teste de propriedade da secao 8 da spec: cenários variados, e o validador
    precisa aprovar tudo que o solver devolver."""
    import random

    rnd = random.Random(semente)
    c = Cenario(dias=5, usa_sabado=False)
    for i in range(rnd.randint(2, 4)):
        c.espaco(f"Sala {i}")
    c.espaco("Lab", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=40)

    professores = [c.professor(f"P{i}", pontuacao=rnd.randint(40, 90)) for i in range(4)]
    for t in range(rnd.randint(1, 3)):
        turma = c.turma(f"{t}o sem")
        for d in range(rnd.randint(2, 4)):
            disciplina = c.disciplina(
                f"D{t}{d}",
                aulas=rnd.choice([2, 4]),
                laboratorio="info" if rnd.random() < 0.3 else None,
                remota=rnd.random() < 0.2,
            )
            c.oferta(turma, disciplina, rnd.choice(professores))

    # alguma indisponibilidade e alguma preferencia
    for prof in professores:
        if rnd.random() < 0.5:
            c.indisponivel(prof, dia=rnd.randrange(5))
        if rnd.random() < 0.5:
            c.preferencial(prof, dia=rnd.randrange(5), ordens=[1, 2])

    solucao = _resolver(c, tempo=20)
    if not solucao.viavel:
        pytest.skip("cenário sorteado é inviável; o teste é sobre soluções válidas")

    _aplicar(c, solucao)
    bloqueantes = [v for v in validar(c.estado, c.config) if v.severidade == Severidade.BLOQUEANTE]
    assert bloqueantes == [], [v.mensagem for v in bloqueantes]


# ------------------------------------------------------------------ desempenho


@pytest.mark.slow
def test_unidade_grande_resolve_dentro_do_limite():
    """Secao 10 da spec: 10 turmas, 40 professores e 200 blocos em ate' 60 s.

    Cada turma tem 20 aulas em 20 horarios — a grade fica cheia, que e' o pior
    caso para as restricoes de espaco e de professor.
    """
    import time

    c = Cenario(dias=5, usa_sabado=False)
    for i in range(14):
        c.espaco(f"Sala {i}")
    for i in range(4):
        c.espaco(f"Lab {i}", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info")

    professores = [c.professor(f"P{i}", pontuacao=40 + i, carga_max_semanal=34) for i in range(40)]
    n = 0
    for t in range(10):
        turma = c.turma(f"{t}o sem")
        for d in range(10):
            disciplina = c.disciplina(
                f"D{t}_{d}",
                aulas=2,
                tamanho_bloco=1,
                max_blocos_por_dia=2,
                laboratorio="info" if d == 0 else None,
            )
            c.oferta(turma, disciplina, professores[n % len(professores)])
            n += 1

    blocos = decompor_em_blocos(c.estado)
    assert len(blocos) == 200, f"o cenário precisa ter 200 blocos, tem {len(blocos)}"

    inicio = time.monotonic()
    solucao = resolver(c.estado, c.config, Parametros(tempo_limite_s=60))
    decorrido = time.monotonic() - inicio

    assert solucao.viavel, solucao.status
    assert decorrido <= 70, f"levou {decorrido:.1f}s"
    assert len(solucao.alocacoes) == 200

    _aplicar(c, solucao)
    assert [v for v in validar(c.estado, c.config) if v.severidade == Severidade.BLOQUEANTE] == []


def test_parametros_do_solver_sao_expostos():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    c.oferta(c.turma(), c.disciplina("ALP", aulas=2), prof)

    solucao = resolver(c.estado, c.config, Parametros(tempo_limite_s=5, semente=7, workers=1))
    assert solucao.viavel
    assert solucao.tempo_s >= 0
    assert set(solucao.metricas) >= {"janela_turma", "janela_professor", "preferencia"}


def test_oferta_com_professor_trocado_em_memoria_e_respeitada():
    """O solver le o professor da oferta, nao da atribuicao no banco."""
    c = Cenario()
    c.espaco("Sala 1")
    ana = c.professor("Ana")
    bruno = c.professor("Bruno")
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP", aulas=2), ana)
    c.estado.ofertas[oferta] = replace(c.estado.ofertas[oferta], professor_id=bruno)

    solucao = _resolver(c)
    assert {a.professor_id for a in solucao.alocacoes} == {bruno}


# ------------------------------------------------------------ resolver avisos


def test_resolver_avisos_zera_a_janela_que_o_peso_preferia_manter():
    """Ana (90) prefere as duas ultimas aulas da unica noite: o peso da
    preferencia (40 x 100 x 2) vence o das janelas (2 x 1000) e a turma fica
    com a 1a e a 2a aula vagas. Com `resolver_avisos` a janela vira regra."""

    def montar() -> tuple[Cenario, int]:
        c = Cenario(dias=1)
        c.espaco("Sala 1")
        c.espaco("Sala 2")
        ana = c.professor("Ana", pontuacao=90)
        bruno = c.professor("Bruno", pontuacao=50)
        t1, t2 = c.turma("1o sem"), c.turma("2o sem")
        oferta = c.oferta(t1, c.disciplina("A", aulas=2), ana)
        c.oferta(t2, c.disciplina("B", aulas=2), bruno)
        c.preferencial(ana, dia=0, ordens=[3, 4])
        return c, oferta

    c, oferta = montar()
    livre = _resolver(c)
    assert livre.metricas["janela_turma"] > 0, "o cenario precisa ter janela por preferencia"

    c, oferta = montar()
    sem_avisos = _resolver(c, resolver_avisos=True)
    assert sem_avisos.viavel
    assert sem_avisos.metricas["janela_turma"] == 0
    assert sem_avisos.metricas["janela_professor"] == 0
    assert _slots_de(sem_avisos, oferta) == {slot_id(0, 1), slot_id(0, 2)}


def test_resolver_avisos_e_inviavel_quando_a_janela_e_forcada_e_nomeia_a_turma():
    """Ana so pode nas duas ultimas aulas: a 1a e a 2a ficam vagas em qualquer
    grade. Exigir zero janela nao fecha, e o diagnostico diz de quem e' a janela."""
    c = Cenario(dias=1)
    c.espaco("Sala 1")
    ana = c.professor("Ana")
    turma = c.turma("1o sem")
    c.oferta(turma, c.disciplina("A", aulas=2), ana)
    c.indisponivel(ana, dia=0, ordens=[1, 2])

    assert _resolver(c).viavel
    solucao = _resolver(c, resolver_avisos=True)
    assert not solucao.viavel

    diag = diagnosticar(c.estado, c.config, Parametros(tempo_limite_s=15, resolver_avisos=True))
    assert any(x["tipo"] == "janela_turma" and x["nome"] == "DSM 1o sem" for x in diag.culpados)
    assert "zero janela na turma DSM 1o sem" in diag.mensagem


def test_resolver_avisos_torna_a_interjornada_rigida():
    """Interjornada em modo `aviso` nao entra no solver. Com `resolver_avisos`
    ela passa a valer: aula ate 22h30 na segunda e aula as 07h00 na terca em
    outra unidade nao cabem juntas, entao Ana vai para a terca a noite."""
    c = Cenario(dias=2)
    assert c.config.interjornada.modo == "aviso"
    c.espaco("Sala 1")
    ana = c.professor("Ana")
    turma = c.turma("1o sem")
    oferta = c.oferta(turma, c.disciplina("A", aulas=2), ana)
    c.aula_em_outra_unidade(ana, dia=1, inicio_min=7 * 60, fim_min=7 * 60 + 50)
    c.preferencial(ana, dia=0, ordens=[1, 2])  # puxa para a segunda, onde o descanso nao fecha

    solucao = _resolver(c, resolver_avisos=True)
    assert solucao.viavel
    assert {c.estado.slots[s].dia for s in _slots_de(solucao, oferta)} == {1}

    _aplicar(c, solucao)
    assert "INTERJORNADA" not in {v.tipo for v in validar(c.estado, c.config)}


# -------------------------------------------------------- concentrar no dia

MANHA_2_2_2 = [
    (1, 7 * 60 + 30, 8 * 60 + 20, 1),
    (2, 8 * 60 + 20, 9 * 60 + 10, 1),
    (3, 9 * 60 + 20, 10 * 60 + 10, 2),
    (4, 10 * 60 + 10, 11 * 60, 2),
    (5, 11 * 60 + 10, 12 * 60, 3),
    (6, 12 * 60, 12 * 60 + 50, 3),
]


def test_concentrar_poe_as_quatro_aulas_no_mesmo_dia_e_seguidas():
    """O "4 + 2" da Fatec: a disciplina concentrada ocupa quatro aulas seguidas
    de um dia (dois pares, um de cada lado do intervalo) e a outra fica com as
    duas que sobram. Ana prefere a 1a/2a e a 5a/6a — sem a regra, o solver
    faria o sanduiche A A B B A A para atender a preferencia."""
    c = Cenario(dias=1, horarios=MANHA_2_2_2)
    c.espaco("Sala 1")
    ana = c.professor("Ana", pontuacao=90)
    bia = c.professor("Bia", pontuacao=50)
    turma = c.turma()
    quatro = c.oferta(turma, c.disciplina("A", aulas=4, concentrar=True), ana)
    dois = c.oferta(turma, c.disciplina("B", aulas=2), bia)
    c.preferencial(ana, dia=0, ordens=[1, 2, 5, 6])

    solucao = _resolver(c)
    assert solucao.viavel, solucao.status
    ordens = {c.estado.slots[s].ordem for s in _slots_de(solucao, quatro)}
    assert ordens in ({1, 2, 3, 4}, {3, 4, 5, 6}), ordens
    assert len(_slots_de(solucao, dois)) == 2

    _aplicar(c, solucao)
    assert "AULAS_NAO_CONCENTRADAS" not in {v.tipo for v in validar(c.estado, c.config)}


def test_concentrar_escolhe_um_dia_so_mesmo_com_varios_disponiveis():
    """Sem concentrar, 4 aulas com 1 bloco por dia vao para dois dias. Com
    concentrar, o limite de blocos por dia deixa de valer para a disciplina."""
    c = Cenario(dias=3)
    c.espaco("Sala 1")
    turma = c.turma()
    espalhada = c.oferta(turma, c.disciplina("E", aulas=4), c.professor("Edu"))
    junta = c.oferta(turma, c.disciplina("J", aulas=4, concentrar=True), c.professor("Jo"))

    solucao = _resolver(c)
    assert solucao.viavel, solucao.status
    dias = lambda oferta: {c.estado.slots[s].dia for s in _slots_de(solucao, oferta)}  # noqa: E731
    assert len(dias(espalhada)) == 2
    assert len(dias(junta)) == 1


def test_seis_concentradas_em_cinco_dias_viram_cinco_mais_uma():
    """Cada dia da manha (6 aulas) comporta uma disciplina concentrada (4). Seis
    marcadas em cinco dias nao cabem: em vez de "sem solucao", o solver
    concentra as cinco que cabem e espalha a que sobrou, com 1 bloco por dia."""
    c = Cenario(dias=5, horarios=MANHA_2_2_2)
    c.espaco("Sala 1")
    turma = c.turma()
    ofertas = [
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4, concentrar=True), c.professor(f"P{i}"))
        for i in range(6)
    ]

    solucao = _resolver(c, tempo=30)
    assert solucao.viavel, solucao.status
    assert solucao.metricas["nao_concentradas"] == 1

    dias = [sorted({c.estado.slots[s].dia for s in _slots_de(solucao, o)}) for o in ofertas]
    assert sorted(len(d) for d in dias) == [1, 1, 1, 1, 1, 2]

    _aplicar(c, solucao)
    avisos = [v for v in validar(c.estado, c.config) if v.tipo == "AULAS_NAO_CONCENTRADAS"]
    assert len(avisos) == 1 and avisos[0].severidade == Severidade.ALERTA


def test_quatro_concentradas_e_duas_espalhadas_fecham_sem_nenhuma_de_fora():
    """O "4 + 2" pedido: quatro disciplinas marcadas, duas nao."""
    c = Cenario(dias=5, horarios=MANHA_2_2_2)
    c.espaco("Sala 1")
    turma = c.turma()
    for i in range(6):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4, concentrar=i < 4), c.professor(f"P{i}"))

    solucao = _resolver(c, tempo=30)
    assert solucao.viavel, solucao.status
    assert solucao.metricas["nao_concentradas"] == 0
