"""Etapa 6: visao da grade por turma, professor e espaco."""

from sqlalchemy import select

from app.models import Unidade


def _preparar(cliente, db, nome="Fatec Taquaritinga") -> tuple[int, int]:
    unidade = db.scalar(select(Unidade).where(Unidade.nome == nome))
    cliente.post(f"/unidades/{unidade.id}/atribuicao/sugerir")
    corpo = cliente.post(f"/unidades/{unidade.id}/grades/gerar", json={"tempo_limite_s": 15}).json()
    return unidade.id, corpo["grade_id"]


def test_visao_por_turma_traz_uma_coluna_por_turma(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    visao = cliente.get(f"/grades/{grade_id}/visao?tipo=turma").json()

    assert visao["tipo"] == "turma"
    assert [c["titulo"] for c in visao["colunas"]] == [
        "DSM 1o sem",
        "DSM 2o sem",
        "DSM 3o sem",
    ]
    assert len(visao["celulas"]) == 72


def test_cada_celula_traz_tudo_que_a_tela_precisa(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    celula = cliente.get(f"/grades/{grade_id}/visao").json()["celulas"][0]

    assert set(celula) >= {
        "disciplina_sigla",
        "disciplina_nome",
        "turma_rotulo",
        "professor_nome",
        "espaco_nome",
        "dia",
        "inicio",
        "fim",
        "bloco_idx",
        "remota",
        "precisa_laboratorio",
        "fixada",
    }
    assert celula["professor_nome"]
    assert ":" in celula["inicio"]


def test_aula_remota_aparece_sem_espaco(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    celulas = cliente.get(f"/grades/{grade_id}/visao").json()["celulas"]

    remotas = [c for c in celulas if c["remota"]]
    assert remotas, "o seed tem uma disciplina remota por semestre"
    assert all(c["espaco_nome"] is None for c in remotas)
    assert all(c["espaco_nome"] for c in celulas if not c["remota"])


def test_horarios_cobrem_a_semana_do_turno_usado(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    visao = cliente.get(f"/grades/{grade_id}/visao?tipo=turma").json()

    # as turmas do DSM usam o modelo noturno + sabado: 4 aulas x 5 dias + 6
    assert len(visao["horarios"]) == 26
    assert {h["dia"] for h in visao["horarios"]} == {0, 1, 2, 3, 4, 5}
    assert visao["horarios"][0]["inicio"] == "19:00:00"


def test_visao_por_professor_so_lista_quem_tem_aula(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    visao = cliente.get(f"/grades/{grade_id}/visao?tipo=professor").json()

    nomes = [c["titulo"] for c in visao["colunas"]]
    assert nomes == sorted(nomes)
    assert "Ana Ribeiro" in nomes
    assert len(nomes) == len({c["professor_id"] for c in visao["celulas"]})
    assert visao["colunas"][0]["subtitulo"], "a pontuação aparece como subtítulo"


def test_visao_por_espaco_lista_salas_e_laboratorios(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    visao = cliente.get(f"/grades/{grade_id}/visao?tipo=espaco").json()

    assert len(visao["colunas"]) == 5
    assert {c["tipo"] for c in visao["colunas"]} == {"SALA", "LABORATORIO"}


def test_visao_ignora_turno_que_nenhuma_turma_usa(cliente, escopo_seed, db):
    """A Fatec tem o modelo de manha cadastrado e sem turma. Incluí-lo enchia a
    visao por professor de linhas vazias marcadas como janela."""
    _, grade_id = _preparar(cliente, db)
    por_professor = cliente.get(f"/grades/{grade_id}/visao?tipo=professor").json()

    inicios = {h["inicio"] for h in por_professor["horarios"]}
    assert "07:30:00" not in inicios, "o turno da manhã não tem turma nenhuma"
    assert len(por_professor["horarios"]) == 26


def test_todas_as_visoes_compartilham_o_mesmo_eixo_de_horarios(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    eixos = {
        tipo: cliente.get(f"/grades/{grade_id}/visao?tipo={tipo}").json()["horarios"]
        for tipo in ("turma", "professor", "espaco")
    }
    assert eixos["turma"] == eixos["professor"] == eixos["espaco"]


def test_divisao_paralela_aparece_com_subturma(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db, "Etec Taquaritinga")
    celulas = cliente.get(f"/grades/{grade_id}/visao").json()["celulas"]

    pw = [c for c in celulas if c["disciplina_sigla"] == "PW"]
    assert {c["subturma"] for c in pw} == {"A", "B"}
    # mesmo horario, professores e espacos diferentes
    por_slot: dict[int, set] = {}
    for c in pw:
        por_slot.setdefault(c["slot_id"], set()).add((c["professor_id"], c["espaco_id"]))
    assert all(len(v) == 2 for v in por_slot.values())


def test_visao_de_grade_inexistente(cliente, escopo_seed):
    assert cliente.get("/grades/9999/visao").status_code == 404


def test_tipo_de_visao_invalido_e_recusado(cliente, escopo_seed, db):
    _, grade_id = _preparar(cliente, db)
    assert cliente.get(f"/grades/{grade_id}/visao?tipo=aluno").status_code == 422


def test_colunas_por_turma_mostram_o_turno_e_vem_na_ordem_do_dia():
    """Duas turmas "DSM 1o sem", uma de manha e outra a noite, eram duas colunas
    iguais na tela, e as linhas da manha vazias na coluna da noite pareciam aula
    sem professor. O subtitulo traz o turno, e a manha vem antes da noite."""
    from app.export.visao import _colunas
    from tests.fabrica import HORARIOS_NOTURNO, Cenario

    c = Cenario()  # modelo 1 = noturno
    manha = c.turno(
        2, range(5), [(o, i - 12 * 60, f - 12 * 60, b) for o, i, f, b in HORARIOS_NOTURNO]
    )
    noite = c.turma("1o sem", alunos=40, turno="Noturno")
    cedo = c.turma("1o sem", alunos=36, modelo=manha, turno="Manhã")

    colunas = _colunas(c.estado, [], "turma")
    assert [x.id for x in colunas] == [cedo, noite]
    assert colunas[0].subtitulo == "Manhã · 36 alunos"
    assert colunas[1].subtitulo == "Noturno · 40 alunos"
