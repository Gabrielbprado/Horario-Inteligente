"""Etapa 3: pre-validacao (app/scheduling/prevalidate.py).

Cada teste monta uma inviabilidade e confere que a mensagem **nomeia a entidade
responsavel** — e' isso que diferencia um diagnostico util de um INFEASIBLE seco.
"""

from app.models import ModoDivisao, Severidade, TipoEspaco
from tests.fabrica import Cenario, cenario_valido


def test_cenario_viavel_passa_sem_nenhuma_pendencia():
    assert cenario_valido().prevalidar() == []


# ------------------------------------------------------------------ atribuicao


def test_oferta_sem_professor():
    c = Cenario()
    c.espaco("Sala 1")
    turma = c.turma()
    c.oferta(turma, c.disciplina("ALP"))

    violacao = c.pre_de_tipo("OFERTA_SEM_PROFESSOR")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "ALP (DSM 1o sem)" in violacao.mensagem
    assert "Sugerir atribuição" in violacao.mensagem


def test_professor_atribuido_sem_vinculo_na_unidade():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    del c.estado.vinculos[prof]
    c.oferta(c.turma(), c.disciplina("ALP"), prof)

    violacao = c.pre_de_tipo("PROFESSOR_SEM_VINCULO")[0]
    assert "Ana" in violacao.mensagem and "Fatec Teste" in violacao.mensagem


def test_carga_atribuida_acima_do_limite():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=6)
    turma = c.turma()
    for sigla in ("ALP", "ESW", "BD"):
        c.oferta(turma, c.disciplina(sigla, aulas=4), prof)

    violacao = c.pre_de_tipo("CARGA_ATRIBUIDA_ACIMA_DO_LIMITE")[0]
    assert "12 aulas semanais" in violacao.mensagem
    assert "limite do vínculo é 6" in violacao.mensagem
    assert "Remova 6 aula(s)" in violacao.mensagem


def test_professor_com_mais_aulas_que_horarios_disponiveis():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    # so' sobra a segunda-feira: 4 horarios para 8 aulas
    for dia in (1, 2, 3, 4):
        c.indisponivel(prof, dia=dia)
    for sigla in ("ALP", "ESW"):
        c.oferta(turma, c.disciplina(sigla, aulas=4), prof)

    violacao = c.pre_de_tipo("PROFESSOR_SEM_HORARIO_SUFICIENTE")[0]
    assert "8 aulas atribuídas" in violacao.mensagem
    assert "4 horário(s) disponível(is)" in violacao.mensagem


# ------------------------------------------------------------------ capacidade


def test_turma_com_mais_aulas_que_horarios_no_turno():
    c = Cenario()  # 5 dias x 4 aulas = 20 horarios
    c.espaco("Sala 1", capacidade=40)
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    for i in range(6):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4), prof)

    violacao = c.pre_de_tipo("TURMA_NAO_CABE_NO_TURNO")[0]
    assert "24 aulas semanais" in violacao.mensagem
    assert "só comporta 20" in violacao.mensagem
    assert "sábado" in violacao.mensagem  # sugestao acionavel


def test_sugestao_muda_quando_o_sabado_ja_esta_ligado():
    c = Cenario(dias=5, usa_sabado=True)
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    for i in range(6):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4), prof)

    violacao = c.pre_de_tipo("TURMA_NAO_CABE_NO_TURNO")[0]
    assert "acrescente horários ao turno" in violacao.mensagem


def test_sabado_desligado_reduz_os_horarios_contados():
    c = Cenario(dias=6, usa_sabado=False)
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    for i in range(6):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4), prof)
    assert "TURMA_NAO_CABE_NO_TURNO" in c.tipos_pre()

    c.config.usa_sabado = True  # agora sao 24 horarios para 24 aulas
    assert "TURMA_NAO_CABE_NO_TURNO" not in c.tipos_pre()


def test_disciplina_exige_laboratorio_que_a_unidade_nao_tem():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    c.oferta(turma, c.disciplina("ALP", laboratorio="informática"), prof)

    violacao = c.pre_de_tipo("LABORATORIO_INEXISTENTE")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "ALP" in violacao.mensagem
    assert "informática" in violacao.mensagem
    assert "Fatec Teste" in violacao.mensagem


def test_demanda_de_laboratorio_acima_da_capacidade_diz_quantos_faltam():
    c = Cenario()  # 20 horarios
    c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info")
    prof = c.professor("Ana", carga_max_semanal=99)
    # 6 turmas x 4 aulas de laboratorio = 24 aulas para 1 lab x 20 horarios
    for i in range(6):
        turma = c.turma(f"{i}o sem")
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4, laboratorio="info"), prof)

    violacao = c.pre_de_tipo("LABORATORIO_INSUFICIENTE")[0]
    assert "24 aulas por semana" in violacao.mensagem
    assert "Falta(m) 1 laboratório(s)" in violacao.mensagem


def test_unidade_sem_nenhum_espaco_cadastrado():
    c = Cenario()
    prof = c.professor("Ana")
    c.oferta(c.turma(), c.disciplina("ALP"), prof)
    assert "SEM_ESPACOS_CADASTRADOS" in c.tipos_pre()


def test_nenhuma_sala_comporta_a_turma():
    c = Cenario()
    c.espaco("Sala pequena", capacidade=20)
    prof = c.professor("Ana")
    c.oferta(c.turma(alunos=45), c.disciplina("ALP"), prof)

    violacao = c.pre_de_tipo("SEM_ESPACO_COMPATIVEL")[0]
    assert "45 alunos" in violacao.mensagem


def test_subturma_cabe_onde_a_turma_inteira_nao_caberia():
    c = Cenario()
    c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    prof = c.professor("Ana")
    turma = c.turma(alunos=36)
    d = c.disciplina("PW", aulas=4, laboratorio="info", divisao=ModoDivisao.PARALELA)
    c.oferta(turma, d, prof, subturma="A")
    assert "SEM_ESPACO_COMPATIVEL" not in c.tipos_pre()


def test_disciplina_remota_nao_entra_na_conta_de_espacos():
    c = Cenario()
    prof = c.professor("Ana")
    c.oferta(c.turma(), c.disciplina("MCT", remota=True), prof)
    assert c.prevalidar() == []


# -------------------------------------------------------------------- horarios


def test_oferta_sem_nenhum_horario_possivel_explica_o_motivo():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    for dia in range(5):
        c.indisponivel(prof, dia=dia)
    c.oferta(turma, c.disciplina("ALP", aulas=2), prof)

    violacao = c.pre_de_tipo("SEM_HORARIO_POSSIVEL")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "ALP (DSM 1o sem)" in violacao.mensagem
    assert "Ana" in violacao.mensagem
    assert "indisponível" in violacao.mensagem


def test_bloco_geminado_sem_par_de_horarios_contiguos():
    """Um turno de 1 aula por bloco nao comporta uma disciplina geminada."""
    c = Cenario(horarios=[(1, 19 * 60, 19 * 60 + 50, 1), (2, 20 * 60, 20 * 60 + 50, 2)])
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    c.oferta(turma, c.disciplina("ALP", aulas=2, tamanho_bloco=2), prof)

    violacao = c.pre_de_tipo("SEM_HORARIO_POSSIVEL")[0]
    assert "aulas seguidas suficientes sem intervalo" in violacao.mensagem


def test_aula_em_outra_unidade_no_mesmo_horario_aparece_no_motivo():
    c = Cenario(
        horarios=[(1, 19 * 60, 19 * 60 + 50, 1), (2, 19 * 60 + 50, 20 * 60 + 40, 1)], dias=1
    )
    c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    c.oferta(turma, c.disciplina("MAT", aulas=2), prof)
    c.aula_em_outra_unidade(prof, dia=0, inicio_min=19 * 60, fim_min=20 * 60 + 40)

    violacao = c.pre_de_tipo("SEM_HORARIO_POSSIVEL")[0]
    assert "outra unidade" in violacao.mensagem
    assert "Etec Teste" in violacao.mensagem


def test_deslocamento_entre_unidades_entra_no_motivo():
    c = Cenario(
        horarios=[(1, 19 * 60, 19 * 60 + 50, 1), (2, 19 * 60 + 50, 20 * 60 + 40, 1)], dias=1
    )
    c.config.deslocamento_entre_unidades_min = 90
    c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    c.oferta(turma, c.disciplina("MAT", aulas=2), prof)
    # termina 18h30 na outra unidade; 30 min ate' as 19h00, e sao exigidos 90
    c.aula_em_outra_unidade(prof, dia=0, inicio_min=17 * 60 + 40, fim_min=18 * 60 + 30)

    violacao = c.pre_de_tipo("SEM_HORARIO_POSSIVEL")[0]
    assert "deslocamento" in violacao.mensagem


def test_disciplina_precisa_de_mais_dias_do_que_o_professor_tem():
    """4 aulas em blocos de 2, um bloco por dia, com o docente livre so' num dia."""
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    for dia in (1, 2, 3, 4):
        c.indisponivel(prof, dia=dia)
    c.oferta(turma, c.disciplina("ALP", aulas=4, max_blocos_por_dia=1), prof)

    violacao = c.pre_de_tipo("POUCOS_DIAS_PARA_A_DISCIPLINA")[0]
    assert "2 blocos em dias diferentes" in violacao.mensagem
    assert "1 dia(s): segunda" in violacao.mensagem


def test_turma_sem_ofertas_e_apenas_alerta():
    c = Cenario()
    c.espaco("Sala 1")
    c.turma("5o sem")

    violacao = c.pre_de_tipo("TURMA_SEM_OFERTAS")[0]
    assert violacao.severidade == Severidade.ALERTA
    assert "DSM 5o sem" in violacao.mensagem


# ------------------------------------------------------------------ integracao


def test_prevalidacao_e_validacao_devolvem_o_mesmo_tipo():
    """A UI e a tabela Aviso tratam as duas do mesmo jeito."""
    from app.scheduling.domain import Violacao

    c = Cenario()
    c.turma("5o sem")
    pendencias = c.prevalidar()
    assert pendencias and all(isinstance(v, Violacao) for v in pendencias)


def test_ordem_das_pendencias_prioriza_bloqueantes():
    c = Cenario()
    c.turma("5o sem")  # ALERTA
    turma = c.turma("1o sem")
    c.oferta(turma, c.disciplina("ALP"))  # BLOQUEANTE
    severidades = [v.severidade for v in c.prevalidar()]
    assert severidades[0] == Severidade.BLOQUEANTE
    assert severidades[-1] == Severidade.ALERTA


def test_turma_que_cabe_em_horarios_mas_nao_em_pares_geminados():
    """ETIM/manha: 6 aulas por dia em dois blocos de 3. Sao 30 horarios, mas uma
    geminada nunca atravessa intervalo, entao cada bloco de 3 recebe um par e
    sobra um horario solto: 20 aulas geminadas. 24 aulas em blocos de 2 nao
    cabem, e o solver devolvia INFEASIBLE sem a pre-validacao perceber (D106)."""
    manha = [
        (1, 7 * 60 + 30, 8 * 60 + 20, 1),
        (2, 8 * 60 + 20, 9 * 60 + 10, 1),
        (3, 9 * 60 + 10, 10 * 60, 1),
        (4, 10 * 60 + 25, 11 * 60 + 15, 2),
        (5, 11 * 60 + 15, 12 * 60 + 5, 2),
        (6, 12 * 60 + 5, 12 * 60 + 55, 2),
    ]
    c = Cenario(dias=5, horarios=manha)
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    for i in range(6):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4, tamanho_bloco=2), prof)

    violacao = c.pre_de_tipo("TURMA_NAO_CABE_NO_TURNO")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "24 aulas em blocos de 2" in violacao.mensagem
    assert "só comporta 20" in violacao.mensagem
    assert "intervalo" in violacao.mensagem

    # Com 20 aulas cabe: cinco disciplinas, um par em cada bloco de 3.
    c2 = Cenario(dias=5, horarios=manha)
    c2.espaco("Sala 1")
    prof2 = c2.professor("Ana", carga_max_semanal=40)
    turma2 = c2.turma()
    for i in range(5):
        c2.oferta(turma2, c2.disciplina(f"D{i}", aulas=4, tamanho_bloco=2), prof2)
    assert "TURMA_NAO_CABE_NO_TURNO" not in c2.tipos_pre()


def test_disciplina_concentrada_que_nao_cabe_em_nenhum_dia_e_alerta():
    """6 aulas seguidas numa noite de 4: nenhum dia comporta. Nao impede a
    grade — o solver espalha a disciplina —, mas a tela avisa antes de gerar."""
    c = Cenario()  # noturno: 4 aulas por dia
    c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=40)
    turma = c.turma()
    c.oferta(turma, c.disciplina("PI", aulas=6, concentrar=True, max_blocos_por_dia=2), prof)

    violacao = c.pre_de_tipo("CONCENTRACAO_NAO_CABE")[0]
    assert violacao.severidade == Severidade.ALERTA
    assert "PI" in violacao.mensagem
    assert "6 aulas" in violacao.mensagem and "espalhada" in violacao.mensagem


def test_mais_concentradas_do_que_dias_avisa_quantas_ficam_de_fora():
    """Manha de 6 aulas: uma concentrada de 4 por dia, 5 dias. Seis marcadas ->
    pelo menos uma fica espalhada, e a tela diz isso antes de gerar."""
    manha = [
        (1, 450, 500, 1),
        (2, 500, 550, 1),
        (3, 560, 610, 2),
        (4, 610, 660, 2),
        (5, 670, 720, 3),
        (6, 720, 770, 3),
    ]
    c = Cenario(dias=5, horarios=manha)
    c.espaco("Sala 1")
    turma = c.turma("3o sem")
    for i in range(6):
        c.oferta(turma, c.disciplina(f"D{i}", aulas=4, concentrar=True), c.professor(f"P{i}"))

    violacao = c.pre_de_tipo("CONCENTRACOES_DEMAIS")[0]
    assert violacao.severidade == Severidade.ALERTA
    assert "DSM 3o sem" in violacao.mensagem
    assert "6 disciplinas" in violacao.mensagem and "5" in violacao.mensagem
    assert "pelo menos 1" in violacao.mensagem

    # Com cinco marcadas cabe: sem aviso.
    c2 = Cenario(dias=5, horarios=manha)
    c2.espaco("Sala 1")
    turma2 = c2.turma()
    for i in range(6):
        c2.oferta(turma2, c2.disciplina(f"D{i}", aulas=4, concentrar=i < 5), c2.professor(f"P{i}"))
    assert "CONCENTRACOES_DEMAIS" not in c2.tipos_pre()


def test_disciplina_concentrada_dispensa_dias_diferentes():
    """Com 1 bloco por dia, 2 blocos pedem 2 dias. Concentrada, um dia basta."""
    c = Cenario(dias=1)
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    c.oferta(turma, c.disciplina("ALP", aulas=4, concentrar=True), prof)
    assert c.tipos_pre() == set()
