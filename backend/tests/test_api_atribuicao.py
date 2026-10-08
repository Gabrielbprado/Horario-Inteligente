"""Etapa 4: atribuicao sobre o seed real e pelos endpoints."""

from sqlalchemy import select

from app.models import Atribuicao, Curso, Disciplina, Oferta, Turma, Unidade


def _unidade(db, nome: str) -> Unidade:
    return db.scalar(select(Unidade).where(Unidade.nome == nome))


def _oferta(db, unidade: Unidade, sigla: str, subturma: str | None = None) -> Oferta:
    return db.scalar(
        select(Oferta)
        .join(Disciplina, Oferta.disciplina_id == Disciplina.id)
        .join(Turma, Oferta.turma_id == Turma.id)
        .join(Curso, Turma.curso_id == Curso.id)
        .where(
            Curso.unidade_id == unidade.id,
            Disciplina.sigla == sigla,
            Oferta.subturma.is_(None) if subturma is None else Oferta.subturma == subturma,
        )
    )


def _nome_do_professor(db, oferta_id: int) -> str | None:
    atribuicao = db.scalar(select(Atribuicao).where(Atribuicao.oferta_id == oferta_id))
    return atribuicao.professor.nome if atribuicao else None


# ------------------------------------------------------------------ endpoint


def test_classificacao_da_fatec_segue_contrato_e_pontuacao(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    lista = cliente.get(f"/unidades/{fatec.id}/atribuicao/classificacao").json()

    assert [c["professor_nome"] for c in lista[:3]] == [
        "Ana Ribeiro",
        "Bruno Carvalho",
        "Carla Menezes",
    ]
    # os contratos por prazo determinado ficam no fim, mesmo com pontuação maior
    assert [c["tipo_contrato"] for c in lista[-3:]] == ["DETERMINADO"] * 3
    assert lista[0]["posicao"] == 1
    assert lista[0]["carga_max"] == 29


def test_sugerir_atribui_tudo_e_devolve_os_avisos(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    corpo = cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir").json()

    assert corpo["atribuidas"] == 18
    assert corpo["preservadas"] == 0
    assert corpo["sem_professor"] == []

    tipos = {a["tipo"] for a in corpo["avisos"]}
    assert tipos == {"PRIORIDADE_NA_ATRIBUICAO"}
    assert all(a["severidade"] == "ALERTA" for a in corpo["avisos"])


def test_disputa_por_pontuacao_no_seed(cliente, escopo_seed, db):
    """Gisele e Henrique empatam em 61,0; a assiduidade decide."""
    fatec = _unidade(db, "Fatec Taquaritinga")
    corpo = cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir").json()

    aviso = next(a for a in corpo["avisos"] if "DW1" in a["mensagem"])
    assert "Gisele Tavares" in aviso["mensagem"]
    assert "Henrique Lopes" in aviso["mensagem"]
    assert "empate em 61 pontos" in aviso["mensagem"]
    assert "assiduidade e pontualidade (20 × 12)" in aviso["mensagem"]

    assert _nome_do_professor(db, _oferta(db, fatec, "DW1").id) == "Gisele Tavares"


def test_contrato_indeterminado_vence_na_fatec(cliente, escopo_seed, db):
    """Paulo (64,0, indeterminado) leva MAT de Elaine (54,0, determinado)."""
    fatec = _unidade(db, "Fatec Taquaritinga")
    corpo = cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir").json()

    aviso = next(a for a in corpo["avisos"] if "MAT" in a["mensagem"])
    assert "contrato por prazo indeterminado" in aviso["mensagem"]
    assert _nome_do_professor(db, _oferta(db, fatec, "MAT").id) == "Paulo Serrano"


def test_manutencao_na_etec_supera_a_classificacao(cliente, escopo_seed, db):
    """Kelly (70,0) mantém Programação Web mesmo com João (78,5) habilitado."""
    etec = _unidade(db, "Etec Taquaritinga")
    corpo = cliente.post(f"/unidades/{etec.id}/atribuicao/sugerir").json()

    assert _nome_do_professor(db, _oferta(db, etec, "PW", "A").id) == "Kelly Souza"
    aviso = next(a for a in corpo["avisos"] if "PW" in a["mensagem"])
    assert "manutenção das aulas que já lecionava" in aviso["mensagem"]
    assert "Deliberação CEETEPS 23/2015" in aviso["mensagem"]


def test_divisao_paralela_fica_com_dois_professores(cliente, escopo_seed, db):
    etec = _unidade(db, "Etec Taquaritinga")
    cliente.post(f"/unidades/{etec.id}/atribuicao/sugerir")

    a = _nome_do_professor(db, _oferta(db, etec, "PW", "A").id)
    b = _nome_do_professor(db, _oferta(db, etec, "PW", "B").id)
    assert a and b and a != b


def test_divisao_sequencial_fica_com_o_mesmo_professor(cliente, escopo_seed, db):
    etec = _unidade(db, "Etec Taquaritinga")
    cliente.post(f"/unidades/{etec.id}/atribuicao/sugerir")

    a = _nome_do_professor(db, _oferta(db, etec, "AI", "A").id)
    b = _nome_do_professor(db, _oferta(db, etec, "AI", "B").id)
    assert a == b


def test_sugerir_preserva_a_atribuicao_manual(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    alp = _oferta(db, fatec, "ALP")
    fabio = next(v.professor for v in fatec.vinculos if v.professor.nome == "Fabio Rocha")
    cliente.post("/atribuicoes", json={"oferta_id": alp.id, "professor_id": fabio.id})

    corpo = cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir").json()
    assert corpo["preservadas"] == 1
    assert corpo["atribuidas"] == 17
    assert _nome_do_professor(db, alp.id) == "Fabio Rocha"


def test_substituir_refaz_tudo_do_zero(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    alp = _oferta(db, fatec, "ALP")
    fabio = next(v.professor for v in fatec.vinculos if v.professor.nome == "Fabio Rocha")
    cliente.post("/atribuicoes", json={"oferta_id": alp.id, "professor_id": fabio.id})

    corpo = cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir?substituir=true").json()
    assert corpo["preservadas"] == 0
    assert corpo["atribuidas"] == 18
    assert _nome_do_professor(db, alp.id) == "Ana Ribeiro"


def test_sugerir_duas_vezes_nao_duplica(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir")
    segundo = cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir").json()

    assert segundo["atribuidas"] == 0
    assert segundo["preservadas"] == 18


def test_limpar_remove_toda_a_atribuicao(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir")
    assert cliente.delete(f"/unidades/{fatec.id}/atribuicao").status_code == 204

    db.expire_all()
    assert _nome_do_professor(db, _oferta(db, fatec, "ALP").id) is None


def test_atribuir_derruba_as_pendencias_da_pre_validacao(cliente, escopo_seed, db):
    """O motivo de a pré-validação reclamar era justamente a falta de professor."""
    fatec = _unidade(db, "Fatec Taquaritinga")
    antes = cliente.get(f"/unidades/{fatec.id}/pre-validacao").json()
    assert {v["tipo"] for v in antes} == {"OFERTA_SEM_PROFESSOR"}

    cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir")

    depois = cliente.get(f"/unidades/{fatec.id}/pre-validacao").json()
    assert depois == [], f"restaram pendências: {[v['tipo'] for v in depois]}"


def test_etec_tambem_fica_pronta_depois_de_atribuir(cliente, escopo_seed, db):
    etec = _unidade(db, "Etec Taquaritinga")
    cliente.post(f"/unidades/{etec.id}/atribuicao/sugerir")
    assert cliente.get(f"/unidades/{etec.id}/pre-validacao").json() == []


def test_classificacao_mostra_a_carga_ja_atribuida(cliente, escopo_seed, db):
    fatec = _unidade(db, "Fatec Taquaritinga")
    cliente.post(f"/unidades/{fatec.id}/atribuicao/sugerir")
    lista = cliente.get(f"/unidades/{fatec.id}/atribuicao/classificacao").json()

    total = sum(c["aulas_atribuidas"] for c in lista)
    assert total == 72  # 18 disciplinas do DSM x 4 aulas semanais
    assert all(c["aulas_atribuidas"] <= c["carga_max"] for c in lista)


def test_unidade_inexistente_devolve_404(cliente, escopo_seed):
    assert cliente.post("/unidades/9999/atribuicao/sugerir").status_code == 404
