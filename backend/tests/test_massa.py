"""A massa de dados precisa fechar grade — senão não serve para nada."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import Oferta, Professor, Severidade, Turma, Unidade
from app.scheduling.loader import carregar_estado
from app.scheduling.prevalidate import prevalidar
from scripts.massa import CURSOS_ETEC, CURSOS_FATEC, capacidade_em_aulas, povoar


def test_capacidade_conta_aulas_geminadas_e_nao_horarios():
    """O ETIM tem 30 horários por semana, mas dois blocos de três aulas por dia.

    Uma geminada nunca atravessa intervalo, então cada bloco de três comporta
    um par e sobra um horário solto: 20 aulas, não 30. Contar 30 gerava turmas
    que o solver declarava INFEASIBLE.
    """
    assert capacidade_em_aulas("etec_etim") == 20
    assert capacidade_em_aulas("fatec_manha") == 20
    assert capacidade_em_aulas("fatec_noturno") == 20
    assert capacidade_em_aulas("fatec_noturno_sabado") == 24


def test_toda_matriz_do_catalogo_cabe_no_turno_que_escolheu():
    """Conferência estática: nenhum curso do catálogo pede mais do que cabe."""
    from scripts.massa import _horarios_que_consome, _matriz_que_cabe

    for modelo in (*CURSOS_FATEC, *CURSOS_ETEC):
        total = sum(_horarios_que_consome(c) for c in _matriz_que_cabe(modelo))
        limite = capacidade_em_aulas(modelo.preset)
        assert total <= limite - 2, f"{modelo.sigla}: {total} aulas em {limite} disponíveis"


@pytest.fixture
def povoado(engine):
    """Uma cidade — duas unidades completas. Leva menos de um segundo."""
    from sqlalchemy.orm import sessionmaker

    Sessao = sessionmaker(bind=engine, autoflush=False)
    with Sessao() as db:
        contagem = povoar(db, cidades=1)
    return contagem, Sessao


def test_uma_cidade_gera_duas_unidades_completas(povoado):
    contagem, Sessao = povoado

    assert contagem.unidades == 2
    assert contagem.turmas > 20
    assert contagem.professores > 40
    with Sessao() as db:
        assert db.scalar(select(func.count()).select_from(Turma)) == contagem.turmas
        assert db.scalar(select(func.count()).select_from(Oferta)) == contagem.ofertas
        assert db.scalar(select(func.count()).select_from(Professor)) == contagem.professores


def test_nenhuma_unidade_nasce_impedida_de_gerar_grade(povoado):
    """É a promessa do script: massa que não fecha grade não serve para nada.

    Roda a mesma pré-validação da tela da unidade — a que o usuário veria ao
    clicar em "Gerar grade".
    """
    contagem, Sessao = povoado
    assert contagem.avisos == []

    with Sessao() as db:
        for unidade in db.scalars(select(Unidade)):
            estado, config = carregar_estado(db, unidade.id)
            impedimentos = [
                v.mensagem
                for v in prevalidar(estado, config)
                if v.severidade == Severidade.BLOQUEANTE
            ]
            assert impedimentos == [], f"{unidade.nome}: {impedimentos[:3]}"


def test_toda_oferta_sai_com_professor_atribuido(povoado):
    _, Sessao = povoado
    with Sessao() as db:
        for unidade in db.scalars(select(Unidade)):
            estado, _ = carregar_estado(db, unidade.id)
            sem = [
                estado.rotulo_oferta(o) for o in estado.ofertas.values() if o.professor_id is None
            ]
            assert sem == [], f"{unidade.nome}: {sem[:3]}"


def test_a_cidade_tem_docente_nas_duas_unidades(povoado):
    """O caso que gera choque entre unidades e interjornada."""
    _, Sessao = povoado
    with Sessao() as db:
        compartilhados = [
            p.nome
            for p in db.scalars(select(Professor))
            if len({v.unidade_id for v in p.vinculos}) > 1
        ]
        assert compartilhados, "ninguém leciona nas duas unidades da cidade"


@pytest.mark.slow
def test_a_massa_realmente_fecha_grade(povoado):
    """A pré-validação diz que *pode* fechar; isto confirma que fecha."""
    from app.scheduling.solver import Parametros, resolver

    _, Sessao = povoado
    with Sessao() as db:
        for unidade in db.scalars(select(Unidade)):
            estado, config = carregar_estado(db, unidade.id)
            solucao = resolver(estado, config, Parametros(tempo_limite_s=60))
            assert solucao.viavel, f"{unidade.nome}: {solucao.status}"


# ------------------------------------------------------------------ conflitos


def test_conflitos_plantados_aparecem_na_pre_validacao(engine):
    """`--conflitos` e' o oposto da promessa acima: dados sabotados de proposito,
    para ver como o sistema reage. Cada conflito plantado precisa aparecer na
    tela da unidade — senao foi plantado em vao. Duas cidades: a par recebe as
    sabotagens brandas, a impar as duras."""
    from sqlalchemy.orm import sessionmaker

    from scripts.massa import sabotar

    Sessao = sessionmaker(bind=engine, autoflush=False)
    with Sessao() as db:
        povoar(db, cidades=2)
        relatorio = sabotar(db, cidades=2)
        db.commit()
    assert len(relatorio) >= 4, relatorio
    assert any("choque" in linha.lower() for linha in relatorio), relatorio

    with Sessao() as db:
        tipos: set[str] = set()
        for unidade in db.scalars(select(Unidade)):
            estado, config = carregar_estado(db, unidade.id)
            tipos |= {v.tipo for v in prevalidar(estado, config)}
    assert {
        "PROFESSOR_SEM_HORARIO_SUFICIENTE",
        "LABORATORIO_INEXISTENTE",
        "OFERTA_SEM_PROFESSOR",
        "CARGA_ATRIBUIDA_ACIMA_DO_LIMITE",
    } <= tipos, tipos
