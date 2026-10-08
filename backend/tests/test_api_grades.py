"""Etapa 5: geracao de grade, progresso, avisos e publicacao pela API."""

from sqlalchemy import select

from app.models import Alocacao, Aviso, Grade, Severidade, StatusGrade, Unidade


def _unidade(db, nome: str) -> Unidade:
    return db.scalar(select(Unidade).where(Unidade.nome == nome))


def _gerar(cliente, unidade_id: int, **params) -> dict:
    # Sem fixar `workers`: provar otimalidade com um unico worker custa o limite
    # de tempo inteiro em cada teste.
    corpo = {"tempo_limite_s": 15, **params}
    resposta = cliente.post(f"/unidades/{unidade_id}/grades/gerar", json=corpo)
    assert resposta.status_code == 202, resposta.text
    return resposta.json()


def _preparar(cliente, db, nome="Fatec Taquaritinga") -> Unidade:
    unidade = _unidade(db, nome)
    cliente.post(f"/unidades/{unidade.id}/atribuicao/sugerir")
    return unidade


# --------------------------------------------------------------- pre-requisito


def test_gerar_sem_atribuicao_recusa_com_as_pendencias(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    resposta = cliente.post(f"/unidades/{fatec.id}/grades/gerar", json={"tempo_limite_s": 5})
    assert resposta.status_code == 409
    detalhe = resposta.json()["detail"]
    assert "ainda não pode gerar" in detalhe["mensagem"]
    assert len(detalhe["pendencias"]) == 18
    assert detalhe["pendencias"][0]["tipo"] == "OFERTA_SEM_PROFESSOR"


def test_nenhuma_grade_e_criada_quando_a_pre_validacao_recusa(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    cliente.post(f"/unidades/{fatec.id}/grades/gerar", json={"tempo_limite_s": 5})
    assert db.scalars(select(Grade)).all() == []


# -------------------------------------------------------------------- geracao


def test_gerar_produz_grade_completa_e_sem_bloqueantes(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    corpo = _gerar(cliente, fatec.id)

    progresso = cliente.get(f"/grades/{corpo['grade_id']}/progresso").json()
    assert progresso["status"] == "concluido", progresso.get("mensagem")
    assert progresso["terminado"] is True
    assert progresso["solucoes"] >= 1
    assert progresso["job_id"] == corpo["job_id"]

    alocacoes = db.scalars(select(Alocacao).where(Alocacao.grade_id == corpo["grade_id"])).all()
    assert len(alocacoes) == 72  # 18 ofertas x 4 aulas

    validacao = cliente.get(f"/grades/{corpo['grade_id']}/validacao").json()
    assert [v for v in validacao if v["severidade"] == "BLOQUEANTE"] == []


def test_grade_guarda_as_metricas_do_objetivo(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    corpo = _gerar(cliente, fatec.id)

    grade = db.get(Grade, corpo["grade_id"])
    assert grade.score["janela_turma"] == 3, "o sábado tem blocos de 3: 1 janela por turma"
    assert set(grade.score) >= {"objetivo", "limite_inferior", "tempo_s", "janela_professor"}


def test_etec_tambem_gera_grade_valida(cliente, escopo_seed, db):
    etec = _preparar(cliente, db, "Etec Taquaritinga")
    corpo = _gerar(cliente, etec.id)

    assert cliente.get(f"/grades/{corpo['grade_id']}/progresso").json()["status"] == "concluido"
    validacao = cliente.get(f"/grades/{corpo['grade_id']}/validacao").json()
    assert [v for v in validacao if v["severidade"] == "BLOQUEANTE"] == []


def test_divisao_paralela_do_seed_cai_no_mesmo_horario(cliente, escopo_seed, db):
    from app.models import Curso, Disciplina, Oferta, Turma

    etec = _preparar(cliente, db, "Etec Taquaritinga")
    corpo = _gerar(cliente, etec.id)

    ofertas = db.scalars(
        select(Oferta)
        .join(Disciplina, Oferta.disciplina_id == Disciplina.id)
        .join(Turma, Oferta.turma_id == Turma.id)
        .join(Curso, Turma.curso_id == Curso.id)
        .where(Curso.unidade_id == etec.id, Disciplina.sigla == "PW")
    ).all()
    assert len(ofertas) == 2

    slots = [
        {
            a.slot_id
            for a in db.scalars(
                select(Alocacao).where(
                    Alocacao.grade_id == corpo["grade_id"], Alocacao.oferta_id == o.id
                )
            )
        }
        for o in ofertas
    ]
    assert slots[0] == slots[1]


def test_grade_aparece_na_listagem_da_unidade(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    corpo = _gerar(cliente, fatec.id)

    lista = cliente.get(f"/grades?unidade_id={fatec.id}").json()
    assert [g["id"] for g in lista] == [corpo["grade_id"]]
    assert lista[0]["nome"] == "Grade 1"


def test_segunda_grade_ganha_nome_sequencial(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    _gerar(cliente, fatec.id)
    segunda = _gerar(cliente, fatec.id)
    assert db.get(Grade, segunda["grade_id"]).nome == "Grade 2"


# ---------------------------------------------------------------- regeneracao


def test_regenerar_a_partir_de_outra_mantem_as_fixadas(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    primeira = _gerar(cliente, fatec.id)["grade_id"]

    alocacoes = db.scalars(select(Alocacao).where(Alocacao.grade_id == primeira)).all()
    alvo = [a for a in alocacoes if a.oferta_id == alocacoes[0].oferta_id]
    for a in alvo:
        a.fixada = True
    db.commit()
    travados = {(a.oferta_id, a.slot_id) for a in alvo}

    segunda = _gerar(cliente, fatec.id, partir_de=primeira)["grade_id"]
    db.expire_all()
    novas = {
        (a.oferta_id, a.slot_id)
        for a in db.scalars(select(Alocacao).where(Alocacao.grade_id == segunda))
    }
    assert travados <= novas


def test_regenerar_a_partir_de_grade_de_outra_unidade_e_recusado(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    etec = _preparar(cliente, db, "Etec Taquaritinga")
    da_fatec = _gerar(cliente, fatec.id)["grade_id"]

    resposta = cliente.post(
        f"/unidades/{etec.id}/grades/gerar",
        json={"tempo_limite_s": 5, "partir_de": da_fatec},
    )
    assert resposta.status_code == 409
    assert "outra unidade" in resposta.json()["detail"]


# --------------------------------------------------------------------- avisos


def test_avisos_sao_gravados_com_a_grade(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    corpo = _gerar(cliente, fatec.id)

    avisos = cliente.get(f"/grades/{corpo['grade_id']}/avisos").json()
    assert avisos
    assert all(a["ciente"] is False for a in avisos)
    assert {a["severidade"] for a in avisos} <= {"INFO", "ALERTA", "BLOQUEANTE"}


def test_grade_com_alerta_fica_aguardando_ciencia(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    corpo = _gerar(cliente, fatec.id)

    grade = db.get(Grade, corpo["grade_id"])
    tem_alerta = db.scalar(
        select(Aviso.id).where(Aviso.grade_id == grade.id, Aviso.severidade == Severidade.ALERTA)
    )
    esperado = StatusGrade.AGUARDANDO_CIENCIA if tem_alerta else StatusGrade.RASCUNHO
    assert grade.status == esperado


def test_dar_ciencia_em_um_aviso(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    corpo = _gerar(cliente, fatec.id)
    aviso = cliente.get(f"/grades/{corpo['grade_id']}/avisos").json()[0]

    resposta = cliente.post(f"/avisos/{aviso['id']}/ciente?autor=Coordenação")
    assert resposta.status_code == 200
    assert resposta.json()["ciente"] is True
    assert resposta.json()["ciente_por"] == "Coordenação"
    assert resposta.json()["ciente_em"]


def test_ciente_de_todos_pega_so_os_alertas(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    corpo = _gerar(cliente, fatec.id)

    marcados = cliente.post(f"/grades/{corpo['grade_id']}/avisos/ciente-todos").json()
    assert all(a["severidade"] == "ALERTA" for a in marcados)

    depois = cliente.get(f"/grades/{corpo['grade_id']}/avisos").json()
    assert all(a["ciente"] for a in depois if a["severidade"] == "ALERTA")


def test_ciencia_sobrevive_a_regeneracao(cliente, escopo_seed, db):
    """Regerar nao deve fazer o usuario reconhecer o mesmo aviso de novo."""
    fatec = _preparar(cliente, db)
    grade_id = _gerar(cliente, fatec.id)["grade_id"]
    cliente.post(f"/grades/{grade_id}/avisos/ciente-todos?autor=Coordenação")
    antes = {a["mensagem"] for a in cliente.get(f"/grades/{grade_id}/avisos").json() if a["ciente"]}
    assert antes

    # gera de novo na mesma grade, pelo job
    from app.scheduling import jobs
    from app.scheduling.solver import Parametros

    jobs.executar_sincrono(grade_id, fatec.id, Parametros(tempo_limite_s=15))

    db.expire_all()
    depois = {
        a["mensagem"] for a in cliente.get(f"/grades/{grade_id}/avisos").json() if a["ciente"]
    }
    assert antes & depois, "os avisos que continuam valendo perderam a ciência"


# ----------------------------------------------------------------- publicacao


def test_publicar_recusa_enquanto_ha_alerta_sem_ciencia(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    grade_id = _gerar(cliente, fatec.id)["grade_id"]

    resposta = cliente.post(f"/grades/{grade_id}/publicar")
    if resposta.status_code == 409:
        assert "Estou ciente" in " ".join(resposta.json()["detail"]["motivos"])
    else:
        # sem nenhum alerta a grade pode ir direto
        assert resposta.json()["status"] == "PUBLICADA"


def test_publicar_depois_da_ciencia(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    grade_id = _gerar(cliente, fatec.id)["grade_id"]
    cliente.post(f"/grades/{grade_id}/avisos/ciente-todos?autor=Coordenação")

    resposta = cliente.post(f"/grades/{grade_id}/publicar")
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "PUBLICADA"


def test_publicar_recusa_com_aviso_bloqueante(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    grade_id = _gerar(cliente, fatec.id)["grade_id"]
    cliente.post(f"/grades/{grade_id}/avisos/ciente-todos")

    db.add(
        Aviso(
            grade_id=grade_id,
            tipo="TESTE",
            severidade=Severidade.BLOQUEANTE,
            mensagem="algo impede",
        )
    )
    db.commit()

    resposta = cliente.post(f"/grades/{grade_id}/publicar")
    assert resposta.status_code == 409
    assert "bloqueante" in " ".join(resposta.json()["detail"]["motivos"])


def test_grade_publicada_vira_ocupacao_na_outra_unidade(cliente, escopo_seed, db):
    """Paulo Serrano leciona nas duas: publicar na Etec trava o horário na Fatec."""
    etec = _preparar(cliente, db, "Etec Taquaritinga")
    grade_etec = _gerar(cliente, etec.id)["grade_id"]
    cliente.post(f"/grades/{grade_etec}/avisos/ciente-todos")
    assert cliente.post(f"/grades/{grade_etec}/publicar").status_code == 200

    from app.scheduling.loader import carregar_estado

    fatec = _unidade(db, "Fatec Taquaritinga")
    estado, _ = carregar_estado(db, fatec.id)
    assert estado.ocupacoes_externas
    assert {o.unidade_nome for o in estado.ocupacoes_externas} == {"Etec Taquaritinga"}


def test_as_duas_unidades_publicadas_nao_geram_choque(cliente, escopo_seed, db):
    """O cenário do professor compartilhado, ponta a ponta."""
    etec = _preparar(cliente, db, "Etec Taquaritinga")
    grade_etec = _gerar(cliente, etec.id)["grade_id"]
    cliente.post(f"/grades/{grade_etec}/avisos/ciente-todos")
    cliente.post(f"/grades/{grade_etec}/publicar")

    fatec = _preparar(cliente, db)
    grade_fatec = _gerar(cliente, fatec.id)["grade_id"]

    validacao = cliente.get(f"/grades/{grade_fatec}/validacao").json()
    assert not [v for v in validacao if v["tipo"] == "CHOQUE_ENTRE_UNIDADES"]
    assert not [v for v in validacao if v["severidade"] == "BLOQUEANTE"]


# ------------------------------------------------------------------- limpeza


def test_apagar_grade_leva_alocacoes_e_avisos_junto(cliente, escopo_seed, db):
    fatec = _preparar(cliente, db)
    grade_id = _gerar(cliente, fatec.id)["grade_id"]

    assert cliente.delete(f"/grades/{grade_id}").status_code == 204
    db.expire_all()
    assert db.scalars(select(Alocacao).where(Alocacao.grade_id == grade_id)).all() == []
    assert db.scalars(select(Aviso).where(Aviso.grade_id == grade_id)).all() == []


def test_progresso_de_grade_sem_execucao_recente(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    grade = Grade(unidade_id=fatec.id, nome="Manual")
    db.add(grade)
    db.commit()
    assert cliente.get(f"/grades/{grade.id}/progresso").status_code == 404


# ------------------------------------------------------------ resolver avisos


def test_resolver_avisos_entrega_a_grade_e_nomeia_o_aviso_que_nao_tem_jeito(
    cliente, escopo_seed, db
):
    """Na Fatec do seed uma janela de turma e' inevitavel. O botao nao pode
    responder so' "nao da": ele entrega a grade sem todos os outros avisos e
    diz qual ficou e por que."""
    fatec = _preparar(cliente, db)
    base = _gerar(cliente, fatec.id)
    corpo = _gerar(cliente, fatec.id, partir_de=base["grade_id"], resolver_avisos=True)

    progresso = cliente.get(f"/grades/{corpo['grade_id']}/progresso").json()
    assert progresso["status"] == "concluido", progresso.get("mensagem")
    culpados = progresso["diagnostico"]["culpados"]
    assert culpados, progresso
    assert culpados[0]["nome"] in progresso["mensagem"]

    avisos = cliente.get(f"/grades/{corpo['grade_id']}/avisos").json()
    assert avisos, "a Fatec do seed tem ao menos uma janela inevitavel"
    nomes_culpados = {c["nome"] for c in culpados}
    for aviso in avisos:
        assert aviso["tipo"] in ("JANELA_TURMA", "JANELA_PROFESSOR", "INTERJORNADA")
        assert any(nome in aviso["mensagem"] for nome in nomes_culpados), aviso["mensagem"]
