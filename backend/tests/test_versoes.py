"""Etapa 9: duplicar uma grade e comparar duas versoes."""

from sqlalchemy import select

from app.models import Grade, StatusGrade, Unidade
from app.scheduling.diff import comparar, resumo
from tests.fabrica import Cenario

# ------------------------------------------------------------------ o diff


def _cenario_com(posicoes: dict[int, tuple[int, int]], espacos=None, professor=None) -> Cenario:
    """`posicoes` e' `{oferta: (dia, ordem)}` — um bloco de uma aula cada."""
    c = Cenario()
    sala = c.espaco("Sala 1")
    outra = c.espaco("Sala 2")
    ana = c.professor("Ana")
    bruno = c.professor("Bruno")
    turma = c.turma()
    for chave, (dia, ordem) in posicoes.items():
        disciplina = c.disciplina(f"D{chave}", aulas=1, tamanho_bloco=1)
        docente = (professor or {}).get(chave, ana) if professor else ana
        if docente == "bruno":
            docente = bruno
        oferta = c.oferta(turma, disciplina, docente)
        escolhido = (espacos or {}).get(chave, sala)
        escolhido = outra if escolhido == "outra" else escolhido
        c.aloca(oferta, dia, ordem, espaco=escolhido)
    return c


def test_grades_identicas_nao_tem_nenhuma_mudanca():
    a = _cenario_com({1: (0, 1), 2: (1, 1)})
    b = _cenario_com({1: (0, 1), 2: (1, 1)})

    assert resumo(comparar(a.estado, b.estado)) == {
        "igual": 2,
        "horario": 0,
        "espaco": 0,
        "professor": 0,
        "removida": 0,
        "adicionada": 0,
    }


def test_aula_que_mudou_de_dia_aparece_como_mudanca_de_horario():
    a = _cenario_com({1: (0, 1)})
    b = _cenario_com({1: (3, 1)})

    (diferenca,) = comparar(a.estado, b.estado)
    assert diferenca.tipo == "horario"
    assert "segunda" in diferenca.antes
    assert "quinta" in diferenca.depois


def test_mesma_hora_em_outra_sala_e_mudanca_de_sala():
    a = _cenario_com({1: (0, 1)})
    b = _cenario_com({1: (0, 1)}, espacos={1: "outra"})

    (diferenca,) = comparar(a.estado, b.estado)
    assert diferenca.tipo == "espaco"
    assert "Sala 1" in diferenca.antes
    assert "Sala 2" in diferenca.depois


def test_outro_professor_no_mesmo_horario_e_sala():
    a = _cenario_com({1: (0, 1)})
    b = _cenario_com({1: (0, 1)}, professor={1: "bruno"})

    (diferenca,) = comparar(a.estado, b.estado)
    assert diferenca.tipo == "professor"


def test_aula_que_so_existe_num_dos_lados():
    a = _cenario_com({1: (0, 1), 2: (1, 1)})
    b = _cenario_com({1: (0, 1)})
    # O cenario numera as ofertas na ordem de criacao, entao a oferta 2 de `a`
    # simplesmente nao existe em `b`.
    tipos = {d.tipo for d in comparar(a.estado, b.estado)}
    assert "removida" in tipos
    assert "adicionada" in {d.tipo for d in comparar(b.estado, a.estado)}


def test_o_bloco_inteiro_conta_como_uma_mudanca_so():
    """Mover duas aulas geminadas e' uma mudanca, nao duas."""
    a = Cenario()
    b = Cenario()
    for cenario, dia in ((a, 0), (b, 2)):
        sala = cenario.espaco("Sala 1")
        prof = cenario.professor("Ana")
        turma = cenario.turma()
        disciplina = cenario.disciplina("ALP", aulas=2, tamanho_bloco=2)
        oferta = cenario.oferta(turma, disciplina, prof)
        cenario.aloca_bloco(oferta, dia, 1, 2, espaco=sala)

    diferencas = comparar(a.estado, b.estado)
    assert len(diferencas) == 1
    assert diferencas[0].tipo == "horario"


def test_as_mudancas_vem_antes_das_iguais():
    a = _cenario_com({1: (0, 1), 2: (1, 1)})
    b = _cenario_com({1: (0, 1), 2: (4, 1)})

    assert [d.tipo for d in comparar(a.estado, b.estado)] == ["horario", "igual"]


# ------------------------------------------------------------------- a API


def _preparar(cliente, db, nome="Etec Taquaritinga") -> int:
    unidade = db.scalar(select(Unidade).where(Unidade.nome == nome))
    cliente.post(f"/unidades/{unidade.id}/atribuicao/sugerir")
    return cliente.post(f"/unidades/{unidade.id}/grades/gerar", json={"tempo_limite_s": 15}).json()[
        "grade_id"
    ]


def test_duplicar_copia_as_aulas_e_nomeia_a_copia(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    copia = cliente.post(f"/grades/{original}/duplicar", json={}).json()

    assert copia["id"] != original
    assert copia["nome"].endswith("(cópia)")

    antes = cliente.get(f"/grades/{original}/visao").json()["celulas"]
    depois = cliente.get(f"/grades/{copia['id']}/visao").json()["celulas"]
    assert len(antes) == len(depois)


def test_duplicar_nao_nasce_publicada(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    cliente.post(f"/grades/{original}/avisos/ciente-todos")
    cliente.post(f"/grades/{original}/publicar")

    copia = cliente.post(f"/grades/{original}/duplicar", json={}).json()
    assert copia["status"] != StatusGrade.PUBLICADA.value


def test_a_copia_recalcula_os_avisos_sem_herdar_a_ciencia(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    cliente.post(f"/grades/{original}/avisos/ciente-todos")

    copia = cliente.post(f"/grades/{original}/duplicar", json={}).json()["id"]
    avisos = cliente.get(f"/grades/{copia}/avisos").json()
    assert avisos
    assert all(not a["ciente"] for a in avisos)


def test_nome_da_copia_nao_se_repete(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    primeira = cliente.post(f"/grades/{original}/duplicar", json={}).json()["nome"]
    segunda = cliente.post(f"/grades/{original}/duplicar", json={}).json()["nome"]
    assert primeira != segunda


def test_duplicar_aceita_nome_escolhido(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    copia = cliente.post(f"/grades/{original}/duplicar", json={"nome": "Plano B"}).json()
    assert copia["nome"] == "Plano B"


def test_comparar_a_copia_com_a_original_nao_acha_mudanca(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    copia = cliente.post(f"/grades/{original}/duplicar", json={}).json()["id"]

    corpo = cliente.get(f"/grades/{original}/comparar?com={copia}").json()
    assert corpo["resumo"]["horario"] == 0
    assert corpo["resumo"]["igual"] > 0
    assert all(d["antes"] == d["depois"] for d in corpo["diferencas"])


def test_comparar_mostra_a_aula_movida_a_mao(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    copia = cliente.post(f"/grades/{original}/duplicar", json={}).json()["id"]

    celula = cliente.get(f"/grades/{copia}/visao").json()["celulas"][0]
    destinos = cliente.get(
        f"/grades/{copia}/destinos?oferta_id={celula['oferta_id']}&bloco_idx={celula['bloco_idx']}"
    ).json()
    destino = next(d for d in destinos if d["slot_id"] != celula["slot_id"])
    r = cliente.post(
        f"/grades/{copia}/aplicar-movimento",
        json={
            "oferta_id": celula["oferta_id"],
            "bloco_idx": celula["bloco_idx"],
            "slot_inicial": destino["slot_id"],
            "forcar": True,
        },
    )
    assert r.status_code == 200, r.text

    corpo = cliente.get(f"/grades/{original}/comparar?com={copia}").json()
    mudancas = [d for d in corpo["diferencas"] if d["tipo"] != "igual"]
    assert mudancas
    assert mudancas[0]["rotulo_tipo"]
    assert mudancas[0]["antes"] != mudancas[0]["depois"]


def test_comparar_traz_as_metricas_lado_a_lado(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    copia = cliente.post(f"/grades/{original}/duplicar", json={}).json()["id"]

    metricas = cliente.get(f"/grades/{original}/comparar?com={copia}").json()["metricas"]
    assert any(m["nome"] == "Janelas de turma" for m in metricas)
    assert all(m["primeira"] is not None for m in metricas)


def test_comparar_grades_de_unidades_diferentes_e_recusado(cliente, escopo_seed, db):
    etec = _preparar(cliente, db, "Etec Taquaritinga")
    fatec = _preparar(cliente, db, "Fatec Taquaritinga")

    r = cliente.get(f"/grades/{etec}/comparar?com={fatec}")
    assert r.status_code == 409
    assert "unidades diferentes" in r.json()["detail"]


def test_comparar_uma_grade_com_ela_mesma_e_recusado(cliente, escopo_seed, db):
    grade = _preparar(cliente, db)
    r = cliente.get(f"/grades/{grade}/comparar?com={grade}")
    assert r.status_code == 409


def test_apagar_a_original_nao_leva_a_copia_junto(cliente, escopo_seed, db):
    original = _preparar(cliente, db)
    copia = cliente.post(f"/grades/{original}/duplicar", json={}).json()["id"]

    assert cliente.delete(f"/grades/{original}").status_code == 204
    assert db.scalar(select(Grade).where(Grade.id == copia)) is not None
