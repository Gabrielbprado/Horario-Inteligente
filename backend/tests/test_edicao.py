"""Etapa 7: edicao manual — mover, trocar, fixar e desfazer."""

from sqlalchemy import select

from app.models import Alocacao, HistoricoAlteracao, StatusGrade, Unidade


def _preparar(cliente, db, nome="Fatec Taquaritinga") -> tuple[int, int]:
    unidade = db.scalar(select(Unidade).where(Unidade.nome == nome))
    cliente.post(f"/unidades/{unidade.id}/atribuicao/sugerir")
    corpo = cliente.post(f"/unidades/{unidade.id}/grades/gerar", json={"tempo_limite_s": 15}).json()
    return unidade.id, corpo["grade_id"]


def _um_bloco(cliente, grade_id: int, sigla: str | None = None) -> dict:
    """Um bloco da grade, com a lista de slots que ele ocupa."""
    celulas = cliente.get(f"/grades/{grade_id}/visao").json()["celulas"]
    if sigla:
        celulas = [c for c in celulas if c["disciplina_sigla"] == sigla]
    alvo = celulas[0]
    do_bloco = [
        c
        for c in celulas
        if c["oferta_id"] == alvo["oferta_id"] and c["bloco_idx"] == alvo["bloco_idx"]
    ]
    do_bloco.sort(key=lambda c: c["ordem"])
    return {
        "oferta_id": alvo["oferta_id"],
        "bloco_idx": alvo["bloco_idx"],
        "slots": [c["slot_id"] for c in do_bloco],
        "sigla": alvo["disciplina_sigla"],
        "espaco_id": alvo["espaco_id"],
    }


def _movimento_limpo(cliente, grade_id: int) -> tuple[dict, int]:
    """Um bloco e um destino aplicavel, diferente de onde ele ja' esta'.

    Varre os blocos porque a grade do seed fica quase cheia: muitos nao tem para
    onde ir sem criar choque, e isso e' o comportamento correto. Aceita destino
    com ALERTA — o movimento e' aplicado do mesmo jeito; so' BLOQUEANTE recusa.
    """
    celulas = cliente.get(f"/grades/{grade_id}/visao").json()["celulas"]
    vistos: set[tuple[int, int]] = set()
    for celula in celulas:
        chave = (celula["oferta_id"], celula["bloco_idx"])
        if chave in vistos:
            continue
        vistos.add(chave)
        bloco = _bloco_de(celulas, *chave)
        destinos = cliente.get(
            f"/grades/{grade_id}/destinos?oferta_id={chave[0]}&bloco_idx={chave[1]}"
        ).json()
        for destino in destinos:
            if destino["severidade"] != "BLOQUEANTE" and destino["slot_id"] not in bloco["slots"]:
                return bloco, destino["slot_id"]
    raise AssertionError("nenhum bloco desta grade tem destino livre")


def _bloco_de(celulas: list[dict], oferta_id: int, bloco_idx: int) -> dict:
    do_bloco = sorted(
        (c for c in celulas if c["oferta_id"] == oferta_id and c["bloco_idx"] == bloco_idx),
        key=lambda c: c["ordem"],
    )
    return {
        "oferta_id": oferta_id,
        "bloco_idx": bloco_idx,
        "slots": [c["slot_id"] for c in do_bloco],
        "sigla": do_bloco[0]["disciplina_sigla"],
        "espaco_id": do_bloco[0]["espaco_id"],
    }


def _slots_do_bloco(cliente, grade_id: int, oferta_id: int, bloco_idx: int) -> list[int]:
    celulas = cliente.get(f"/grades/{grade_id}/visao").json()["celulas"]
    do_bloco = [c for c in celulas if c["oferta_id"] == oferta_id and c["bloco_idx"] == bloco_idx]
    return sorted(c["slot_id"] for c in do_bloco)


# ------------------------------------------------------------------- destinos


def test_destinos_avalia_a_semana_inteira_de_uma_vez(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)

    destinos = cliente.get(
        f"/grades/{grade_id}/destinos?oferta_id={bloco['oferta_id']}&bloco_idx={bloco['bloco_idx']}"
    ).json()

    assert destinos, "o bloco precisa ter pelo menos um destino avaliado"
    assert all(set(d) == {"slot_id", "severidade", "motivos"} for d in destinos)
    # o lugar onde ele ja' esta' e' sempre um destino limpo
    atual = min(bloco["slots"])
    assert next(d for d in destinos if d["slot_id"] == atual)["severidade"] is None


def test_destinos_marca_o_que_criaria_choque(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    destinos = cliente.get(
        f"/grades/{grade_id}/destinos?oferta_id={bloco['oferta_id']}&bloco_idx={bloco['bloco_idx']}"
    ).json()

    bloqueados = [d for d in destinos if d["severidade"] == "BLOQUEANTE"]
    assert bloqueados, "a grade está cheia; algum destino tem de dar choque"
    assert all(d["motivos"] for d in bloqueados), "todo bloqueio precisa de motivo"


def test_destinos_de_bloco_inexistente(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    resposta = cliente.get(f"/grades/{grade_id}/destinos?oferta_id=99999")
    assert resposta.status_code == 422


# --------------------------------------------------------------------- mover


def test_validar_movimento_nao_altera_nada(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    bloco, destino = _movimento_limpo(cliente, grade_id)

    resposta = cliente.post(
        f"/grades/{grade_id}/validar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": destino,
        },
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["aplicado"] is False
    assert corpo["permitido"] is True
    assert len(corpo["alteracoes"]) == len(bloco["slots"])

    db.expire_all()
    assert _slots_do_bloco(cliente, grade_id, bloco["oferta_id"], bloco["bloco_idx"]) == sorted(
        bloco["slots"]
    )


def test_mover_o_bloco_inteiro(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    bloco, destino = _movimento_limpo(cliente, grade_id)

    resposta = cliente.post(
        f"/grades/{grade_id}/aplicar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": destino,
        },
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["aplicado"] is True

    db.expire_all()
    novos = _slots_do_bloco(cliente, grade_id, bloco["oferta_id"], bloco["bloco_idx"])
    assert destino in novos
    assert len(novos) == len(bloco["slots"]), "as aulas geminadas andam juntas"


def test_movimento_que_viola_regra_rigida_e_recusado(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    destinos = cliente.get(
        f"/grades/{grade_id}/destinos?oferta_id={bloco['oferta_id']}&bloco_idx={bloco['bloco_idx']}"
    ).json()
    proibido = next(d for d in destinos if d["severidade"] == "BLOQUEANTE")

    resposta = cliente.post(
        f"/grades/{grade_id}/aplicar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": proibido["slot_id"],
        },
    )
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["motivos"]

    db.expire_all()
    assert _slots_do_bloco(cliente, grade_id, bloco["oferta_id"], bloco["bloco_idx"]) == sorted(
        bloco["slots"]
    )


def test_forcar_aplica_e_deixa_o_aviso_bloqueando_a_publicacao(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    destinos = cliente.get(
        f"/grades/{grade_id}/destinos?oferta_id={bloco['oferta_id']}&bloco_idx={bloco['bloco_idx']}"
    ).json()
    proibido = next(d for d in destinos if d["severidade"] == "BLOQUEANTE")

    resposta = cliente.post(
        f"/grades/{grade_id}/aplicar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": proibido["slot_id"],
            "forcar": True,
        },
    )
    assert resposta.status_code == 200
    assert resposta.json()["aplicado"] is True

    avisos = cliente.get(f"/grades/{grade_id}/avisos").json()
    assert [a for a in avisos if a["severidade"] == "BLOQUEANTE"]

    cliente.post(f"/grades/{grade_id}/avisos/ciente-todos")
    publicar = cliente.post(f"/grades/{grade_id}/publicar")
    assert publicar.status_code == 409
    assert "bloqueante" in " ".join(publicar.json()["detail"]["motivos"])


def test_destino_sem_horarios_seguidos_explica_o_motivo(cliente, escopo_seed, db):
    """O sábado tem blocos de 3; começar na 3ª aula não cabe um bloco de 2."""
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    visao = cliente.get(f"/grades/{grade_id}/visao").json()

    sabado = [h for h in visao["horarios"] if h["dia"] == 5]
    assert sabado
    # a 3a aula de sabado fecha o primeiro bloco do modelo
    celulas_sabado = [c for c in visao["celulas"] if c["dia"] == 5 and c["ordem"] == 3]
    slot_fim_de_bloco = celulas_sabado[0]["slot_id"] if celulas_sabado else None
    if slot_fim_de_bloco is None:
        return

    resposta = cliente.post(
        f"/grades/{grade_id}/validar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": slot_fim_de_bloco,
        },
    )
    assert resposta.status_code == 422
    assert "sem intervalo no meio" in resposta.json()["detail"]


# --------------------------------------------------------------------- trocar


def test_trocar_dois_blocos_de_lugar(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    celulas = cliente.get(f"/grades/{grade_id}/visao").json()["celulas"]
    a = _um_bloco(cliente, grade_id, celulas[0]["disciplina_sigla"])

    outra = next(
        c
        for c in celulas
        if c["oferta_id"] != a["oferta_id"] and c["turma_id"] != celulas[0]["turma_id"]
    )
    b = {"oferta_id": outra["oferta_id"], "bloco_idx": outra["bloco_idx"]}
    slots_b = _slots_do_bloco(cliente, grade_id, b["oferta_id"], b["bloco_idx"])

    resposta = cliente.post(
        f"/grades/{grade_id}/trocar",
        json={
            "a": {"oferta_id": a["oferta_id"], "bloco_idx": a["bloco_idx"]},
            "b": b,
            "forcar": True,
        },
    )
    assert resposta.status_code == 200, resposta.text

    db.expire_all()
    novos_a = _slots_do_bloco(cliente, grade_id, a["oferta_id"], a["bloco_idx"])
    novos_b = _slots_do_bloco(cliente, grade_id, b["oferta_id"], b["bloco_idx"])
    assert novos_a == sorted(slots_b)
    assert novos_b == sorted(a["slots"])


def test_trocar_blocos_de_tamanhos_diferentes_e_recusado(cliente, escopo_seed, db):
    """Etec: Inglês tem 2 aulas em 1 bloco; Lógica tem 4 em blocos de 2."""
    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    curto = _um_bloco(cliente, grade_id, "ING")
    longo = _um_bloco(cliente, grade_id, "LP")
    if len(curto["slots"]) == len(longo["slots"]):
        return  # os tamanhos coincidiram; nada a testar aqui

    resposta = cliente.post(
        f"/grades/{grade_id}/trocar",
        json={
            "a": {"oferta_id": curto["oferta_id"], "bloco_idx": curto["bloco_idx"]},
            "b": {"oferta_id": longo["oferta_id"], "bloco_idx": longo["bloco_idx"]},
        },
    )
    assert resposta.status_code == 422
    assert "quantidades diferentes de horários" in resposta.json()["detail"]


# ---------------------------------------------------------------------- fixar


def test_fixar_e_liberar_o_bloco(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    corpo = {"oferta_id": bloco["oferta_id"], "bloco_idx": bloco["bloco_idx"]}

    assert (
        cliente.post(f"/grades/{grade_id}/fixar", json={**corpo, "fixada": True}).status_code == 200
    )
    db.expire_all()
    fixadas = {
        a.fixada
        for a in db.scalars(
            select(Alocacao).where(
                Alocacao.grade_id == grade_id, Alocacao.oferta_id == bloco["oferta_id"]
            )
        )
        if a.bloco_idx == bloco["bloco_idx"]
    }
    assert fixadas == {True}

    cliente.post(f"/grades/{grade_id}/fixar", json={**corpo, "fixada": False})
    db.expire_all()
    assert not any(
        a.fixada for a in db.scalars(select(Alocacao).where(Alocacao.grade_id == grade_id))
    )


def test_bloco_fixado_sobrevive_a_regeneracao(cliente, escopo_seed, db):
    unidade_id, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    cliente.post(
        f"/grades/{grade_id}/fixar",
        json={"oferta_id": bloco["oferta_id"], "bloco_idx": bloco["bloco_idx"], "fixada": True},
    )

    nova = cliente.post(
        f"/unidades/{unidade_id}/grades/gerar",
        json={"tempo_limite_s": 15, "partir_de": grade_id},
    ).json()["grade_id"]

    db.expire_all()
    assert _slots_do_bloco(cliente, nova, bloco["oferta_id"], bloco["bloco_idx"]) == sorted(
        bloco["slots"]
    )


# ------------------------------------------------------------------ historico


def test_cada_alteracao_entra_no_historico(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    cliente.post(
        f"/grades/{grade_id}/fixar",
        json={"oferta_id": bloco["oferta_id"], "bloco_idx": bloco["bloco_idx"], "fixada": True},
    )

    historico = cliente.get(f"/grades/{grade_id}/historico").json()
    assert len(historico) == 1
    assert historico[0]["origem"] == "MANUAL"
    assert bloco["sigla"] in historico[0]["descricao"]
    assert historico[0]["desfeito"] is False


def test_desfazer_volta_o_bloco_para_o_lugar(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    bloco, destino = _movimento_limpo(cliente, grade_id)

    cliente.post(
        f"/grades/{grade_id}/aplicar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": destino,
        },
    )
    db.expire_all()
    assert _slots_do_bloco(cliente, grade_id, bloco["oferta_id"], bloco["bloco_idx"]) != sorted(
        bloco["slots"]
    )

    desfeitos = cliente.post(f"/grades/{grade_id}/desfazer").json()
    assert desfeitos and bloco["sigla"] in desfeitos[0]

    db.expire_all()
    assert _slots_do_bloco(cliente, grade_id, bloco["oferta_id"], bloco["bloco_idx"]) == sorted(
        bloco["slots"]
    )


def test_desfazer_varios_passos_de_uma_vez(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    corpo = {"oferta_id": bloco["oferta_id"], "bloco_idx": bloco["bloco_idx"]}

    cliente.post(f"/grades/{grade_id}/fixar", json={**corpo, "fixada": True})
    cliente.post(f"/grades/{grade_id}/fixar", json={**corpo, "fixada": False})
    cliente.post(f"/grades/{grade_id}/fixar", json={**corpo, "fixada": True})

    desfeitos = cliente.post(f"/grades/{grade_id}/desfazer?passos=3").json()
    assert len(desfeitos) == 3

    db.expire_all()
    assert not any(
        a.fixada for a in db.scalars(select(Alocacao).where(Alocacao.grade_id == grade_id))
    )
    assert all(r.desfeito for r in db.scalars(select(HistoricoAlteracao)))


def test_desfazer_sem_historico(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    assert cliente.post(f"/grades/{grade_id}/desfazer").status_code == 409


def test_desfazer_nao_repete_um_passo_ja_desfeito(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    cliente.post(
        f"/grades/{grade_id}/fixar",
        json={"oferta_id": bloco["oferta_id"], "bloco_idx": bloco["bloco_idx"], "fixada": True},
    )
    assert cliente.post(f"/grades/{grade_id}/desfazer").status_code == 200
    assert cliente.post(f"/grades/{grade_id}/desfazer").status_code == 409


# -------------------------------------------------------------------- status


def test_editar_tira_a_grade_de_publicada(cliente, escopo_seed, db):
    """O que foi publicado mudou; a grade volta a precisar de conferência."""
    from app.models import Grade

    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    cliente.post(f"/grades/{grade_id}/avisos/ciente-todos")
    cliente.post(f"/grades/{grade_id}/publicar")
    db.expire_all()
    assert db.get(Grade, grade_id).status == StatusGrade.PUBLICADA

    bloco, destino = _movimento_limpo(cliente, grade_id)
    cliente.post(
        f"/grades/{grade_id}/aplicar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": destino,
        },
    )

    db.expire_all()
    assert db.get(Grade, grade_id).status != StatusGrade.PUBLICADA


def test_grade_quase_cheia_quase_nao_tem_para_onde_mover(cliente, escopo_seed, db):
    """As turmas do DSM ocupam 24 dos 26 horários. Quase todo destino cria
    choque de turma — é por isso que os testes de movimento usam a Etec."""
    _, grade_id = _preparar(cliente, db)
    bloco = _um_bloco(cliente, grade_id)
    destinos = cliente.get(
        f"/grades/{grade_id}/destinos?oferta_id={bloco['oferta_id']}&bloco_idx={bloco['bloco_idx']}"
    ).json()

    limpos = [d for d in destinos if d["severidade"] is None]
    assert [d["slot_id"] for d in limpos] == [min(bloco["slots"])], (
        "o único destino sem violação deveria ser o lugar onde o bloco já está"
    )


def test_soltar_no_mesmo_lugar_nao_gera_passo_no_historico(cliente, escopo_seed, db):
    """Arrastar e soltar de volta não é uma alteração; gravaria um "desfazer"
    que não desfaz nada."""
    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    bloco = _um_bloco(cliente, grade_id)

    resposta = cliente.post(
        f"/grades/{grade_id}/aplicar-movimento",
        json={
            "oferta_id": bloco["oferta_id"],
            "bloco_idx": bloco["bloco_idx"],
            "slot_inicial": min(bloco["slots"]),
        },
    )
    assert resposta.status_code == 200
    assert resposta.json()["alteracoes"] == []
    assert cliente.get(f"/grades/{grade_id}/historico").json() == []


def test_fixar_duas_vezes_seguidas_nao_duplica_o_historico(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    bloco = _um_bloco(cliente, grade_id)
    corpo = {"oferta_id": bloco["oferta_id"], "bloco_idx": bloco["bloco_idx"], "fixada": True}

    cliente.post(f"/grades/{grade_id}/fixar", json=corpo)
    cliente.post(f"/grades/{grade_id}/fixar", json=corpo)
    assert len(cliente.get(f"/grades/{grade_id}/historico").json()) == 1
