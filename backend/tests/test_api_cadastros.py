"""Etapa 2: CRUDs de cadastro."""

from sqlalchemy import select

from app.models import Curso, Disciplina, Disponibilidade, Oferta, Turma, Unidade


def _criar_escopo(cliente) -> int:
    return cliente.post("/escopos", json={"nome": "CPS"}).json()["id"]


# ------------------------------------------------------------------------- CRUD


def test_ciclo_completo_de_escopo(cliente):
    criado = cliente.post("/escopos", json={"nome": "Centro Paula Souza"})
    assert criado.status_code == 201
    id_ = criado.json()["id"]

    assert cliente.get(f"/escopos/{id_}").json()["nome"] == "Centro Paula Souza"
    assert [e["id"] for e in cliente.get("/escopos").json()] == [id_]

    alterado = cliente.patch(f"/escopos/{id_}", json={"nome": "CPS"})
    assert alterado.json()["nome"] == "CPS"

    assert cliente.delete(f"/escopos/{id_}").status_code == 204
    assert cliente.get(f"/escopos/{id_}").status_code == 404


def test_nome_duplicado_devolve_409_com_mensagem_em_portugues(cliente):
    cliente.post("/escopos", json={"nome": "CPS"})
    repetido = cliente.post("/escopos", json={"nome": "CPS"})
    assert repetido.status_code == 409
    assert "Ja existe" in repetido.json()["detail"]


def test_404_nomeia_a_entidade(cliente):
    assert cliente.get("/professores/999").json()["detail"] == "Professor 999 nao encontrado(a)."


def test_validacao_rejeita_nome_vazio(cliente):
    assert cliente.post("/escopos", json={"nome": ""}).status_code == 422


def test_filtro_desconhecido_explica_os_validos(cliente):
    resposta = cliente.get("/unidades?nome=x")
    assert resposta.status_code == 422
    assert "escopo_id" in resposta.json()["detail"]


def test_filtro_por_fk(cliente):
    a, b = _criar_escopo(cliente), _criar_escopo_com_nome(cliente, "Outro")
    cliente.post("/unidades", json={"escopo_id": a, "nome": "Fatec A", "tipo": "FATEC"})
    cliente.post("/unidades", json={"escopo_id": b, "nome": "Fatec B", "tipo": "FATEC"})

    assert [u["nome"] for u in cliente.get(f"/unidades?escopo_id={a}").json()] == ["Fatec A"]


def _criar_escopo_com_nome(cliente, nome: str) -> int:
    return cliente.post("/escopos", json={"nome": nome}).json()["id"]


# -------------------------------------------------------------- unidade + presets


def test_unidade_nova_ja_nasce_com_preset_do_tipo(cliente, db):
    escopo_id = _criar_escopo(cliente)
    unidade = cliente.post(
        "/unidades", json={"escopo_id": escopo_id, "nome": "Etec X", "tipo": "ETEC"}
    ).json()

    assert unidade["config_regras"]["carga_max_semanal"] == 34
    assert unidade["config_regras"]["atribuicao"]["regra"] == "ETEC"

    modelos = cliente.get(f"/modelos-turno?unidade_id={unidade['id']}").json()
    assert {mt["preset_origem"] for mt in modelos} == {
        "etec_tecnico_noturno",
        "etec_tecnico_noturno_1850",
        "etec_etim",
    }
    noturno = next(mt for mt in modelos if mt["preset_origem"] == "etec_tecnico_noturno")
    assert len(noturno["slots"]) == 20
    assert db.get(Unidade, unidade["id"]).carga_max_semanal_padrao == 34


def test_reaplicar_preset_pode_preservar_as_regras_editadas(cliente):
    escopo_id = _criar_escopo(cliente)
    id_ = cliente.post(
        "/unidades", json={"escopo_id": escopo_id, "nome": "Fatec Y", "tipo": "FATEC"}
    ).json()["id"]

    cliente.patch(f"/unidades/{id_}", json={"config_regras": {"carga_max_semanal": 12}})
    preservado = cliente.post(f"/unidades/{id_}/presets/fatec?substituir_regras=false").json()
    assert preservado["config_regras"]["carga_max_semanal"] == 12

    substituido = cliente.post(f"/unidades/{id_}/presets/fatec").json()
    assert substituido["config_regras"]["carga_max_semanal"] == 29


def test_config_regras_e_validada_antes_de_gravar(cliente):
    escopo_id = _criar_escopo(cliente)
    id_ = cliente.post(
        "/unidades", json={"escopo_id": escopo_id, "nome": "Fatec Z", "tipo": "FATEC"}
    ).json()["id"]

    atual = cliente.get(f"/unidades/{id_}/config-regras").json()
    atual["interjornada"]["modo"] = "talvez"
    assert cliente.put(f"/unidades/{id_}/config-regras", json=atual).status_code == 422

    atual["interjornada"]["modo"] = "rigida"
    gravado = cliente.put(f"/unidades/{id_}/config-regras", json=atual)
    assert gravado.status_code == 200
    assert cliente.get(f"/unidades/{id_}/config-regras").json()["interjornada"]["modo"] == "rigida"


def test_config_regras_preenche_o_que_falta_com_o_padrao(cliente):
    """O solver nunca deve ler uma chave ausente."""
    escopo_id = _criar_escopo(cliente)
    id_ = cliente.post(
        "/unidades", json={"escopo_id": escopo_id, "nome": "Fatec W", "tipo": "FATEC"}
    ).json()["id"]
    cliente.patch(f"/unidades/{id_}", json={"config_regras": {"carga_max_semanal": 20}})

    regras = cliente.get(f"/unidades/{id_}/config-regras").json()
    assert regras["carga_max_semanal"] == 20
    assert regras["pesos"]["janela_turma"] == 1000
    assert regras["limite_diario"]["ativo"] is False


def test_presets_de_turno_listados_por_tipo(cliente):
    fatec = cliente.get("/presets/turno?tipo=FATEC").json()
    assert {p["chave"] for p in fatec} == {
        "fatec_noturno",
        "fatec_noturno_sabado",
        "fatec_manha",
    }
    noturno = next(p for p in fatec if p["chave"] == "fatec_noturno")
    assert noturno["aulas_por_dia"] == {"0": 4, "1": 4, "2": 4, "3": 4, "4": 4}
    assert len(cliente.get("/presets/turno").json()) == 6


# ------------------------------------------------------------------ modelo de turno


def _unidade(cliente) -> int:
    escopo_id = _criar_escopo(cliente)
    return cliente.post(
        "/unidades", json={"escopo_id": escopo_id, "nome": "Fatec T", "tipo": "FATEC"}
    ).json()["id"]


def _slot(ordem, inicio, fim, bloco, dia=0):
    return {
        "dia_semana": dia,
        "ordem": ordem,
        "inicio": inicio,
        "fim": fim,
        "bloco_id": bloco,
    }


def test_modelo_de_turno_criado_a_partir_de_preset(cliente):
    unidade_id = _unidade(cliente)
    criado = cliente.post(
        "/modelos-turno",
        json={"unidade_id": unidade_id, "nome": "Noite", "preset_origem": "fatec_noturno"},
    )
    assert criado.status_code == 201
    corpo = criado.json()
    assert corpo["nome"] == "Noite"
    assert corpo["dias_semana"] == [0, 1, 2, 3, 4]
    assert len(corpo["slots"]) == 20


def test_modelo_de_turno_recusa_bloco_que_atravessa_intervalo(cliente):
    unidade_id = _unidade(cliente)
    resposta = cliente.post(
        "/modelos-turno",
        json={
            "unidade_id": unidade_id,
            "nome": "Errado",
            "slots": [
                _slot(1, "19:00", "19:50", 1),
                # ha um intervalo de 10 min, mas os dois estao no mesmo bloco
                _slot(2, "20:00", "20:50", 1),
            ],
        },
    )
    assert resposta.status_code == 422
    assert "nao atravessa intervalo" in resposta.json()["detail"]


def test_modelo_de_turno_recusa_aulas_sobrepostas_e_ordens_com_furo(cliente):
    unidade_id = _unidade(cliente)
    sobreposto = cliente.post(
        "/modelos-turno",
        json={
            "unidade_id": unidade_id,
            "nome": "Sobreposto",
            "slots": [_slot(1, "19:00", "20:00", 1), _slot(2, "19:30", "20:20", 2)],
        },
    )
    assert sobreposto.status_code == 422
    assert "comeca" in sobreposto.json()["detail"]

    com_furo = cliente.post(
        "/modelos-turno",
        json={
            "unidade_id": unidade_id,
            "nome": "Furo",
            "slots": [_slot(1, "19:00", "19:50", 1), _slot(3, "19:50", "20:40", 1)],
        },
    )
    assert com_furo.status_code == 422
    assert "sem furos" in com_furo.json()["detail"]


def test_slot_com_fim_antes_do_inicio_e_rejeitado(cliente):
    unidade_id = _unidade(cliente)
    resposta = cliente.post(
        "/modelos-turno",
        json={
            "unidade_id": unidade_id,
            "nome": "Invertido",
            "slots": [_slot(1, "20:00", "19:00", 1)],
        },
    )
    assert resposta.status_code == 422


def test_substituir_modelo_troca_a_semana_inteira(cliente):
    unidade_id = _unidade(cliente)
    id_ = cliente.post(
        "/modelos-turno",
        json={"unidade_id": unidade_id, "nome": "Noite", "preset_origem": "fatec_noturno"},
    ).json()["id"]

    novo = cliente.put(
        f"/modelos-turno/{id_}",
        json={
            "unidade_id": unidade_id,
            "nome": "Noite curta",
            "slots": [_slot(1, "19:00", "19:50", 1), _slot(2, "19:50", "20:40", 1)],
        },
    )
    assert novo.status_code == 200
    assert novo.json()["nome"] == "Noite curta"
    assert len(novo.json()["slots"]) == 2
    assert novo.json()["dias_semana"] == [0]


def test_modelo_em_uso_por_turma_nao_pode_ser_apagado(cliente, escopo_seed, db):
    turma = db.scalars(select(Turma)).first()
    resposta = cliente.delete(f"/modelos-turno/{turma.modelo_turno_id}")
    assert resposta.status_code == 409
    assert "em uso por turmas" in resposta.json()["detail"]


# ------------------------------------------------------------- turma <-> ofertas


def test_criar_turma_gera_as_ofertas_do_periodo(cliente, escopo_seed, db):
    dsm = db.scalar(select(Curso).where(Curso.sigla == "DSM"))
    modelo_id = dsm.turmas[0].modelo_turno_id

    criada = cliente.post(
        "/turmas",
        json={
            "curso_id": dsm.id,
            "periodo": "1o sem",
            "turno": "Noturno",
            "modelo_turno_id": modelo_id,
            "qtd_alunos": 30,
        },
    )
    assert criada.status_code == 201
    ofertas = cliente.get(f"/ofertas?turma_id={criada.json()['id']}").json()
    assert len(ofertas) == 6
    assert {o["disciplina_sigla"] for o in ofertas} == {
        "ALP",
        "DD",
        "ESW1",
        "MBD",
        "SOR",
        "MCT",
    }


def test_ligar_divisao_de_turma_cria_a_subturma_b(cliente, escopo_seed, db):
    lp = db.scalar(select(Disciplina).where(Disciplina.sigla == "LP"))
    assert len(lp.ofertas) == 1

    cliente.patch(f"/disciplinas/{lp.id}", json={"divisao_turma": True, "modo_divisao": "PARALELA"})
    db.expire_all()
    ofertas = db.scalars(select(Oferta).where(Oferta.disciplina_id == lp.id)).all()
    assert sorted(o.subturma for o in ofertas) == ["A", "B"]


def test_apagar_disciplina_remove_as_ofertas(cliente, escopo_seed, db):
    lp = db.scalar(select(Disciplina).where(Disciplina.sigla == "LP"))
    assert cliente.delete(f"/disciplinas/{lp.id}").status_code == 204
    assert db.scalars(select(Oferta).where(Oferta.disciplina_id == lp.id)).all() == []


def test_ofertas_trazem_professor_atribuido_sem_consulta_extra(cliente, escopo_seed, db):
    oferta = db.scalars(select(Oferta)).first()
    professor_id = db.scalar(
        select(Disciplina).where(Disciplina.id == oferta.disciplina_id).join(Disciplina.ofertas)
    )
    cliente.post("/atribuicoes", json={"professor_id": 1, "oferta_id": oferta.id})

    detalhe = next(o for o in cliente.get("/ofertas").json() if o["id"] == oferta.id)
    assert detalhe["professor_id"] == 1
    assert detalhe["professor_nome"]
    assert detalhe["disciplina_nome"]
    assert professor_id is not None  # a oferta pertence mesmo a essa disciplina


def test_uma_oferta_tem_no_maximo_um_professor(cliente, escopo_seed, db):
    oferta = db.scalars(select(Oferta)).first()
    assert (
        cliente.post("/atribuicoes", json={"professor_id": 1, "oferta_id": oferta.id}).status_code
        == 201
    )
    repetida = cliente.post("/atribuicoes", json={"professor_id": 2, "oferta_id": oferta.id})
    assert repetida.status_code == 409


# ------------------------------------------------------------------ disponibilidade


def test_lote_marca_a_noite_inteira_de_uma_vez(cliente, escopo_seed, db):
    turma = db.scalars(select(Turma)).first()
    slots = [s.id for s in turma.modelo_turno.slots if s.dia_semana == 2]
    unidade_id = turma.curso.unidade_id

    resposta = cliente.put(
        "/disponibilidades/lote",
        json={
            "professor_id": 1,
            "unidade_id": unidade_id,
            "slot_ids": slots,
            "status": "INDISPONIVEL",
        },
    )
    assert resposta.status_code == 200
    assert len(resposta.json()) == len(slots)

    gravadas = cliente.get("/disponibilidades?professor_id=1").json()
    indisponiveis = [d for d in gravadas if d["status"] == "INDISPONIVEL"]
    assert {d["slot_id"] for d in indisponiveis} == set(slots)


def test_lote_com_disponivel_apaga_o_registro(cliente, escopo_seed, db):
    turma = db.scalars(select(Turma)).first()
    slots = [s.id for s in turma.modelo_turno.slots if s.dia_semana == 2][:2]
    unidade_id = turma.curso.unidade_id
    corpo = {"professor_id": 1, "unidade_id": unidade_id, "slot_ids": slots}

    cliente.put("/disponibilidades/lote", json={**corpo, "status": "PREFERENCIAL"})
    assert db.scalars(select(Disponibilidade).where(Disponibilidade.slot_id.in_(slots))).all() != []

    cliente.put("/disponibilidades/lote", json={**corpo, "status": "DISPONIVEL"})
    db.expire_all()
    assert db.scalars(select(Disponibilidade).where(Disponibilidade.slot_id.in_(slots))).all() == []


def test_lote_reaplicado_atualiza_em_vez_de_duplicar(cliente, escopo_seed, db):
    turma = db.scalars(select(Turma)).first()
    slots = [s.id for s in turma.modelo_turno.slots if s.dia_semana == 3]
    corpo = {"professor_id": 1, "unidade_id": turma.curso.unidade_id, "slot_ids": slots}

    cliente.put("/disponibilidades/lote", json={**corpo, "status": "INDISPONIVEL"})
    cliente.put("/disponibilidades/lote", json={**corpo, "status": "PREFERENCIAL"})

    db.expire_all()
    registros = db.scalars(select(Disponibilidade).where(Disponibilidade.slot_id.in_(slots))).all()
    assert len(registros) == len(slots)
    assert {r.status.value for r in registros} == {"PREFERENCIAL"}


def test_lote_para_professor_inexistente_devolve_404(cliente, escopo_seed, db):
    turma = db.scalars(select(Turma)).first()
    resposta = cliente.put(
        "/disponibilidades/lote",
        json={
            "professor_id": 9999,
            "unidade_id": turma.curso.unidade_id,
            "slot_ids": [turma.modelo_turno.slots[0].id],
            "status": "INDISPONIVEL",
        },
    )
    assert resposta.status_code == 404


# ------------------------------------------------------------------------ protecao


def test_unidade_com_grade_nao_pode_ser_apagada(cliente, escopo_seed, db):
    from app.models import Grade

    unidade = db.scalars(select(Unidade)).first()
    db.add(Grade(unidade_id=unidade.id, nome="Rascunho"))
    db.commit()

    resposta = cliente.delete(f"/unidades/{unidade.id}")
    assert resposta.status_code == 409
    assert "Apague as grades" in resposta.json()["detail"]


# ------------------------------------------------------- blocos no nivel do curso


def test_blocos_do_curso_valem_para_todas_as_disciplinas(cliente, escopo_seed, db):
    """O tamanho do bloco e os blocos por dia moram na disciplina, que e' o que
    o solver le. Mas a escola decide isso por curso: um PUT no curso grava em
    todas as disciplinas dele, e a disciplina continua editavel como excecao."""
    dsm = db.scalar(select(Curso).where(Curso.sigla == "DSM"))
    antes = cliente.get(f"/disciplinas?curso_id={dsm.id}").json()
    assert {d["max_blocos_por_dia"] for d in antes} == {1}

    resposta = cliente.put(f"/cursos/{dsm.id}/blocos", json={"max_blocos_por_dia": 2})
    assert resposta.status_code == 200, resposta.text
    depois = resposta.json()
    assert len(depois) == len(antes)
    assert {d["max_blocos_por_dia"] for d in depois} == {2}
    assert {d["tamanho_bloco"] for d in depois} == {2}, "nao mexe no que nao foi pedido"

    resposta = cliente.put(f"/cursos/{dsm.id}/blocos", json={"tamanho_bloco": 4})
    assert {d["tamanho_bloco"] for d in resposta.json()} == {4}
    assert {d["max_blocos_por_dia"] for d in resposta.json()} == {2}


def test_blocos_do_curso_recusa_corpo_vazio_e_curso_inexistente(cliente, escopo_seed, db):
    dsm = db.scalar(select(Curso).where(Curso.sigla == "DSM"))
    assert cliente.put(f"/cursos/{dsm.id}/blocos", json={}).status_code == 422
    assert cliente.put("/cursos/9999/blocos", json={"tamanho_bloco": 2}).status_code == 404


def test_concentrar_no_dia_vale_para_o_curso_e_para_a_disciplina(cliente, escopo_seed, db):
    dsm = db.scalar(select(Curso).where(Curso.sigla == "DSM"))
    antes = cliente.get(f"/disciplinas?curso_id={dsm.id}").json()
    assert {d["concentrar_no_dia"] for d in antes} == {False}

    depois = cliente.put(f"/cursos/{dsm.id}/blocos", json={"concentrar_no_dia": True}).json()
    assert {d["concentrar_no_dia"] for d in depois} == {True}
    assert {d["tamanho_bloco"] for d in depois} == {2}

    uma = depois[0]["id"]
    excecao = cliente.patch(f"/disciplinas/{uma}", json={"concentrar_no_dia": False})
    assert excecao.status_code == 200 and excecao.json()["concentrar_no_dia"] is False
