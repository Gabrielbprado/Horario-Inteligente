"""Etapa 3: o loader e o validador rodando sobre o seed real."""

from sqlalchemy import select

from app.models import (
    Alocacao,
    Curso,
    Disciplina,
    Grade,
    Oferta,
    Professor,
    StatusGrade,
    Turma,
    Unidade,
)
from app.scheduling.loader import carregar_estado
from app.scheduling.prevalidate import prevalidar
from app.scheduling.validator import validar


def _unidade(db, nome: str) -> Unidade:
    return db.scalar(select(Unidade).where(Unidade.nome == nome))


def test_loader_traduz_a_unidade_inteira(escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    estado, config = carregar_estado(db, fatec.id)

    assert estado.unidade_nome == "Fatec Taquaritinga"
    assert config.carga_max_semanal == 29
    assert config.usa_sabado is True
    assert len(estado.turmas) == 3
    assert len(estado.ofertas) == 18
    assert len(estado.espacos) == 5
    # 3 modelos de turno: noturno 20 + noturno com sabado 26 + manha 30
    assert len(estado.slots) == 76
    assert estado.alocacoes == []


def test_loader_resolve_rotulos_legiveis(escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    estado, _ = carregar_estado(db, fatec.id)
    rotulos = {estado.rotulo_oferta(o) for o in estado.ofertas.values()}
    assert "ALP (DSM 1o sem)" in rotulos


def test_loader_marca_subturmas_da_divisao(escopo_seed, db):
    etec = _unidade(db, "Etec Taquaritinga")
    estado, _ = carregar_estado(db, etec.id)
    pw = next(d for d in estado.disciplinas.values() if d.sigla == "PW")
    ofertas = [o for o in estado.ofertas.values() if o.disciplina_id == pw.id]
    assert sorted(o.subturma for o in ofertas) == ["A", "B"]
    assert "PW (TDS Modulo I, turma A)" in {estado.rotulo_oferta(o) for o in ofertas}


def test_seed_sem_atribuicao_acusa_todas_as_ofertas(escopo_seed, db):
    """O seed nao atribui professores; a pre-validacao precisa dizer isso."""
    fatec = _unidade(db, "Fatec Taquaritinga")
    estado, config = carregar_estado(db, fatec.id)
    pendencias = prevalidar(estado, config)

    sem_professor = [v for v in pendencias if v.tipo == "OFERTA_SEM_PROFESSOR"]
    assert len(sem_professor) == 18
    # nenhuma pendencia de capacidade: o seed foi dimensionado para caber
    assert {v.tipo for v in pendencias} == {"OFERTA_SEM_PROFESSOR"}


def test_etec_do_seed_tambem_so_falta_atribuir(escopo_seed, db):
    etec = _unidade(db, "Etec Taquaritinga")
    estado, config = carregar_estado(db, etec.id)
    assert {v.tipo for v in prevalidar(estado, config)} == {"OFERTA_SEM_PROFESSOR"}


def test_grade_vazia_do_seed_acusa_falta_de_aulas(escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    grade = Grade(unidade_id=fatec.id, nome="Rascunho")
    db.add(grade)
    db.commit()

    estado, config = carregar_estado(db, fatec.id, grade_id=grade.id)
    violacoes = validar(estado, config)
    assert {v.tipo for v in violacoes} == {"QUANTIDADE_DE_AULAS"}
    assert len(violacoes) == 18


def test_ocupacao_externa_so_vem_de_grade_publicada(escopo_seed, db):
    """Rascunho de outra unidade nao pode travar horario aqui."""
    fatec = _unidade(db, "Fatec Taquaritinga")
    etec = _unidade(db, "Etec Taquaritinga")
    paulo = db.scalar(select(Professor).where(Professor.identificador == "paulo.serrano"))

    oferta = db.scalar(
        select(Oferta)
        .join(Disciplina, Oferta.disciplina_id == Disciplina.id)
        .join(Turma, Oferta.turma_id == Turma.id)
        .join(Curso, Turma.curso_id == Curso.id)
        .where(Curso.unidade_id == etec.id, Disciplina.sigla == "LPG")
    )
    slot = db.scalar(select(Turma).where(Turma.id == oferta.turma_id)).modelo_turno.slots[0]

    grade_etec = Grade(unidade_id=etec.id, nome="Rascunho da Etec")
    db.add(grade_etec)
    db.flush()
    db.add(
        Alocacao(
            grade_id=grade_etec.id,
            oferta_id=oferta.id,
            professor_id=paulo.id,
            slot_id=slot.id,
            bloco_idx=0,
        )
    )
    db.commit()

    estado, _ = carregar_estado(db, fatec.id)
    assert estado.ocupacoes_externas == []

    grade_etec.status = StatusGrade.PUBLICADA
    db.commit()

    estado, _ = carregar_estado(db, fatec.id)
    assert len(estado.ocupacoes_externas) == 1
    ocupacao = estado.ocupacoes_externas[0]
    assert ocupacao.professor_id == paulo.id
    assert ocupacao.unidade_nome == "Etec Taquaritinga"
    assert ocupacao.inicio_min == 7 * 60  # ETIM comeca as 07:00


def test_endpoint_de_pre_validacao(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    resposta = cliente.get(f"/unidades/{fatec.id}/pre-validacao")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 18
    assert corpo[0]["severidade"] == "BLOQUEANTE"
    assert corpo[0]["tipo"] == "OFERTA_SEM_PROFESSOR"
    assert "oferta_id" in corpo[0]["entidades"]


def test_endpoint_de_validacao_de_grade(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    grade = Grade(unidade_id=fatec.id, nome="Rascunho")
    db.add(grade)
    db.commit()

    resposta = cliente.get(f"/grades/{grade.id}/validacao")
    assert resposta.status_code == 200
    assert {v["tipo"] for v in resposta.json()} == {"QUANTIDADE_DE_AULAS"}


def test_endpoint_de_validacao_404_para_grade_inexistente(cliente, escopo_seed):
    assert cliente.get("/grades/9999/validacao").status_code == 404


def test_divisao_paralela_nao_conta_em_dobro_nos_horarios_da_turma(escopo_seed, db):
    """PW A e B assistem ao mesmo tempo: o Modulo I gasta 18 dos 20 horarios,
    nao 22. Contar em dobro acusaria uma inviabilidade que nao existe."""
    from app.scheduling.prevalidate import _horarios_que_a_turma_consome

    etec = _unidade(db, "Etec Taquaritinga")
    estado, _ = carregar_estado(db, etec.id)
    modulo_i = next(t for t in estado.turmas.values() if t.periodo == "Modulo I")

    assert _horarios_que_a_turma_consome(estado)[modulo_i.id] == 18
    # soma ingenua, contando cada oferta: 22
    ingenua = sum(
        estado.disciplina_da(o).aulas_semanais
        for o in estado.ofertas.values()
        if o.turma_id == modulo_i.id
    )
    assert ingenua == 22
