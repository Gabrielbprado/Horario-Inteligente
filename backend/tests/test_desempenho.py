"""Etapa 10: desempenho dos caminhos que o usuario espera sentado.

O solver ja tem o seu teste de 200 blocos em `test_solver.py`. Aqui estao os
caminhos **interativos**, que rodam a cada arrasto, a cada mensagem do chat e a
cada abertura de tela — e que, ao contrario do solver, nao tem barra de
progresso para justificar a espera.

Os limites sao folgados de proposito (mais de dez vezes o medido em maquina de
desenvolvimento): servem para pegar regressao de ordem de grandeza, nao para
cravar milissegundos numa maquina de CI compartilhada.
"""

from __future__ import annotations

import time

import pytest

from app.models import Severidade, TipoEspaco
from app.scheduling.apply import Bloco, destinos_possiveis, simular_movimento
from app.scheduling.domain import AlocacaoInfo
from app.scheduling.solver import Parametros, decompor_em_blocos, resolver
from app.scheduling.validator import validar
from tests.fabrica import Cenario

pytestmark = pytest.mark.slow


def _unidade_grande() -> Cenario:
    """10 turmas, 40 professores, 200 blocos — o porte da secao 10 da spec."""
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
    return c


@pytest.fixture(scope="module")
def grade_cheia() -> Cenario:
    """Uma grade de verdade, resolvida uma vez e reaproveitada pelos testes."""
    c = _unidade_grande()
    assert len(decompor_em_blocos(c.estado)) == 200

    solucao = resolver(c.estado, c.config, Parametros(tempo_limite_s=60))
    assert solucao.viavel, solucao.status

    c.estado.alocacoes = [
        AlocacaoInfo(
            id=i + 1,
            oferta_id=a.oferta_id,
            professor_id=a.professor_id,
            slot_id=a.slot_id,
            espaco_id=a.espaco_id,
            bloco_idx=a.bloco_idx,
        )
        for i, a in enumerate(solucao.alocacoes)
    ]
    return c


def _medir(funcao, repeticoes: int = 5) -> float:
    """Milissegundos por chamada."""
    funcao()  # a primeira paga import e cache
    inicio = time.perf_counter()
    for _ in range(repeticoes):
        funcao()
    return (time.perf_counter() - inicio) / repeticoes * 1000


def test_validar_a_grade_inteira_e_instantaneo(grade_cheia):
    """`validar` roda em toda alteracao: arrasto, ferramenta do chat, publicar.

    Sao 20 checagens sobre 200 aulas. Medido em ~3 ms; o limite aqui e' 50 ms.
    """
    ms = _medir(lambda: validar(grade_cheia.estado, grade_cheia.config))
    assert ms < 50, f"validar levou {ms:.1f} ms numa grade de 200 aulas"


def test_a_grade_grande_sai_do_solver_sem_violacao_rigida(grade_cheia):
    bloqueantes = [
        v
        for v in validar(grade_cheia.estado, grade_cheia.config)
        if v.severidade == Severidade.BLOQUEANTE
    ]
    assert bloqueantes == []


def test_um_arrasto_avalia_a_semana_inteira_em_um_pedido(grade_cheia):
    """O contrato da tela (DECISOES D64): uma consulta por arrasto, nao uma por
    celula sobrevoada. Esta consulta valida a grade uma vez por destino, entao
    e' a mais cara do uso interativo. Medida em ~100 ms."""
    bloco = Bloco(grade_cheia.estado.alocacoes[0].oferta_id, 0)
    ms = _medir(
        lambda: destinos_possiveis(grade_cheia.estado, grade_cheia.config, bloco),
        repeticoes=3,
    )
    assert ms < 1500, f"destinos levou {ms:.0f} ms"

    destinos = destinos_possiveis(grade_cheia.estado, grade_cheia.config, bloco)
    assert len(destinos) > 1, "a semana toda deveria ter sido avaliada"


def test_simular_um_movimento_e_barato(grade_cheia):
    """O chat chama `validar_movimento` antes de propor; nao pode pesar."""
    alocacao = grade_cheia.estado.alocacoes[0]
    bloco = Bloco(alocacao.oferta_id, 0)
    # `destinos_possiveis` devolve {slot_id: Resultado}.
    alvo = next(iter(destinos_possiveis(grade_cheia.estado, grade_cheia.config, bloco)))

    ms = _medir(
        lambda: simular_movimento(grade_cheia.estado, grade_cheia.config, bloco, alvo, None)
    )
    assert ms < 50, f"simular_movimento levou {ms:.1f} ms"
