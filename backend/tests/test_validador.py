"""Etapa 3: o validador unico (app/scheduling/validator.py)."""

from dataclasses import replace

import pytest

from app.models import ModoDivisao, Severidade, StatusDisponibilidade, TipoEspaco
from tests.fabrica import Cenario, cenario_valido, slot_id


def test_grade_correta_nao_gera_violacao():
    assert cenario_valido().validar() == []


def test_violacoes_vem_das_mais_graves_para_as_menos_graves():
    c = cenario_valido()
    # tira uma aula (BLOQUEANTE) e deixa uma preferencia nao atendida (INFO)
    c.estado.alocacoes.pop()
    c.preferencial(c.ids["ana"], dia=4, ordens=[1])
    severidades = [v.severidade for v in c.validar()]
    assert severidades == sorted(
        severidades,
        key=lambda s: [Severidade.BLOQUEANTE, Severidade.ALERTA, Severidade.INFO].index(s),
    )


# ------------------------------------------------------------------ estrutura


def test_oferta_com_menos_aulas_que_o_previsto():
    c = cenario_valido()
    c.estado.alocacoes.pop()
    violacao = c.de_tipo("QUANTIDADE_DE_AULAS")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "3 de 4 aulas semanais" in violacao.mensagem


def test_oferta_sem_nenhuma_aula():
    c = Cenario()
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP")
    c.oferta(turma, d, prof)
    assert "não tem nenhuma aula na grade" in c.de_tipo("QUANTIDADE_DE_AULAS")[0].mensagem


def test_bloco_que_atravessa_o_intervalo():
    """2a e 3a aula sao seguidas no relogio mas tem o intervalo entre elas."""
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2)
    o = c.oferta(turma, d, prof)
    c.aloca(o, dia=0, ordem=2, espaco=sala, bloco_idx=0)
    c.aloca(o, dia=0, ordem=3, espaco=sala, bloco_idx=0)

    violacao = c.de_tipo("BLOCO_ATRAVESSA_INTERVALO")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "atravessa o intervalo" in violacao.mensagem
    assert "segunda" in violacao.mensagem


def test_bloco_espalhado_entre_dias():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2)
    o = c.oferta(turma, d, prof)
    c.aloca(o, dia=0, ordem=1, espaco=sala, bloco_idx=0)
    c.aloca(o, dia=1, ordem=1, espaco=sala, bloco_idx=0)
    assert "BLOCO_PARTIDO" in c.tipos()


def test_bloco_com_buraco_no_meio():
    c = Cenario(horarios=[(o, 8 * 60 + o * 50, 8 * 60 + (o + 1) * 50, 1) for o in range(1, 5)])
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2)
    o = c.oferta(turma, d, prof)
    c.aloca(o, dia=0, ordem=1, espaco=sala, bloco_idx=0)
    c.aloca(o, dia=0, ordem=3, espaco=sala, bloco_idx=0)
    assert "BLOCO_NAO_CONTIGUO" in c.tipos()


def test_blocos_fora_do_padrao_sao_alerta_e_nao_bloqueiam():
    """4 aulas deveriam virar 2+2; 3+1 funciona mas foge da matriz."""
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4, max_blocos_por_dia=2)
    o = c.oferta(turma, d, prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, tamanho=2, espaco=sala, bloco_idx=0)
    c.aloca(o, dia=0, ordem=3, espaco=sala, bloco_idx=1)
    c.aloca(o, dia=1, ordem=1, espaco=sala, bloco_idx=2)

    violacao = c.de_tipo("BLOCOS_FORA_DO_PADRAO")[0]
    assert violacao.severidade == Severidade.ALERTA
    assert "2+1+1" in violacao.mensagem and "2+2" in violacao.mensagem


def test_mais_blocos_por_dia_que_o_permitido():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4, max_blocos_por_dia=1)
    o = c.oferta(turma, d, prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=0, ordem_inicial=3, espaco=sala, bloco_idx=1)

    violacao = c.de_tipo("BLOCOS_POR_DIA")[0]
    assert "2 blocos na segunda" in violacao.mensagem


def test_aula_em_horario_de_outro_modelo_de_turno():
    c = Cenario()
    manha = c.turno(2, range(0, 5), [(1, 7 * 60, 7 * 60 + 50, 1), (2, 7 * 60 + 50, 8 * 60 + 40, 1)])
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()  # usa o modelo noturno
    d = c.disciplina("ALP", aulas=1, tamanho_bloco=1)
    o = c.oferta(turma, d, prof)
    c.aloca(o, dia=0, ordem=1, espaco=sala, slot=manha * 1000 + 0 * 10 + 1)

    assert "HORARIO_DE_OUTRO_TURNO" in c.tipos()


def test_sabado_bloqueado_quando_a_unidade_nao_usa():
    c = Cenario(dias=6, usa_sabado=False)
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2)
    o = c.oferta(turma, d, prof)
    c.aloca_bloco(o, dia=5, ordem_inicial=1, espaco=sala)

    assert "AULA_EM_DIA_NAO_PERMITIDO" in c.tipos()
    assert "sábado" in c.de_tipo("AULA_EM_DIA_NAO_PERMITIDO")[0].mensagem

    c.config.usa_sabado = True
    assert "AULA_EM_DIA_NAO_PERMITIDO" not in c.tipos()


def test_professor_da_grade_precisa_ser_o_da_atribuicao():
    c = cenario_valido()
    c.estado.alocacoes[0] = replace(c.estado.alocacoes[0], professor_id=c.ids["bruno"])
    violacao = c.de_tipo("PROFESSOR_DIFERENTE_DA_ATRIBUICAO")[0]
    assert "Bruno" in violacao.mensagem and "Ana" in violacao.mensagem


# -------------------------------------------------------------------- choques


def test_choque_de_professor():
    c = Cenario()
    sala1, sala2 = c.espaco("Sala 1"), c.espaco("Sala 2")
    prof = c.professor("Ana")
    t1, t2 = c.turma("1o sem"), c.turma("2o sem")
    d1, d2 = c.disciplina("ALP", aulas=2), c.disciplina("ESW", aulas=2)
    o1, o2 = c.oferta(t1, d1, prof), c.oferta(t2, d2, prof)
    c.aloca_bloco(o1, dia=0, ordem_inicial=1, espaco=sala1)
    c.aloca_bloco(o2, dia=0, ordem_inicial=1, espaco=sala2)

    violacoes = c.de_tipo("CHOQUE_PROFESSOR")
    assert len(violacoes) == 2  # uma por horario do bloco
    assert "Ana" in violacoes[0].mensagem
    assert violacoes[0].severidade == Severidade.BLOQUEANTE


def test_choque_de_turma():
    c = Cenario()
    sala1, sala2 = c.espaco("Sala 1"), c.espaco("Sala 2")
    pa, pb = c.professor("Ana"), c.professor("Bruno")
    turma = c.turma()
    d1, d2 = c.disciplina("ALP", aulas=2), c.disciplina("ESW", aulas=2)
    c.aloca_bloco(c.oferta(turma, d1, pa), dia=0, ordem_inicial=1, espaco=sala1)
    c.aloca_bloco(c.oferta(turma, d2, pb), dia=0, ordem_inicial=1, espaco=sala2)

    violacoes = c.de_tipo("CHOQUE_TURMA")
    assert len(violacoes) == 2
    assert "DSM 1o sem" in violacoes[0].mensagem


def test_choque_de_espaco():
    c = Cenario()
    sala = c.espaco("Sala 1")
    pa, pb = c.professor("Ana"), c.professor("Bruno")
    t1, t2 = c.turma("1o sem"), c.turma("2o sem")
    d1, d2 = c.disciplina("ALP", aulas=2), c.disciplina("ESW", aulas=2)
    c.aloca_bloco(c.oferta(t1, d1, pa), dia=0, ordem_inicial=1, espaco=sala)
    c.aloca_bloco(c.oferta(t2, d2, pb), dia=0, ordem_inicial=1, espaco=sala)

    assert len(c.de_tipo("CHOQUE_ESPACO")) == 2
    assert "Sala 1" in c.de_tipo("CHOQUE_ESPACO")[0].mensagem


# --------------------------------------------------------------------- espaco


def test_disciplina_presencial_sem_sala():
    c = Cenario()
    c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=None)
    assert len(c.de_tipo("SEM_ESPACO")) == 2


def test_disciplina_remota_nao_precisa_de_sala():
    c = Cenario()
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("MCT", aulas=2, remota=True)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=None)
    assert c.tipos() == set()


def test_disciplina_remota_ocupando_sala_gera_alerta():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("MCT", aulas=2, remota=True)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=sala)

    violacao = c.de_tipo("ESPACO_EM_AULA_REMOTA")[0]
    assert violacao.severidade == Severidade.ALERTA


def test_laboratorio_do_tipo_errado():
    c = Cenario()
    quimica = c.espaco("Lab Química", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="química")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2, laboratorio="informática")
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=quimica)

    violacao = c.de_tipo("ESPACO_INCOMPATIVEL")[0]
    assert "informática" in violacao.mensagem and "química" in violacao.mensagem


def test_aula_de_laboratorio_em_sala_comum():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2, laboratorio="informática")
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=sala)
    assert "é sala comum" in c.de_tipo("ESPACO_INCOMPATIVEL")[0].mensagem


def test_capacidade_insuficiente_e_alerta_nao_bloqueio():
    c = Cenario()
    sala = c.espaco("Sala 1", capacidade=20)
    prof = c.professor("Ana")
    turma = c.turma(alunos=40)
    d = c.disciplina("ALP", aulas=2)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=sala)

    violacao = c.de_tipo("CAPACIDADE_INSUFICIENTE")[0]
    assert violacao.severidade == Severidade.ALERTA
    assert "40 alunos" in violacao.mensagem


def test_subturma_conta_metade_dos_alunos():
    c = Cenario()
    sala = c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    prof = c.professor("Ana")
    turma = c.turma(alunos=36)
    d = c.disciplina("PW", aulas=2, laboratorio="info", divisao=ModoDivisao.PARALELA)
    c.aloca_bloco(c.oferta(turma, d, prof, subturma="A"), dia=0, ordem_inicial=1, espaco=sala)
    assert "CAPACIDADE_INSUFICIENTE" not in c.tipos()


# ------------------------------------------------------------ disponibilidade


def test_aula_em_horario_marcado_como_indisponivel():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=2)
    c.indisponivel(prof, dia=0)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=sala)

    violacoes = c.de_tipo("PROFESSOR_INDISPONIVEL")
    assert len(violacoes) == 2
    assert violacoes[0].severidade == Severidade.BLOQUEANTE


def test_preferencia_nao_atendida_e_apenas_informativa():
    c = cenario_valido()
    c.preferencial(c.ids["ana"], dia=4, ordens=[1, 2])
    violacao = c.de_tipo("PREFERENCIA_NAO_ATENDIDA")[0]
    assert violacao.severidade == Severidade.INFO
    assert "2 horário(s)" in violacao.mensagem


# ------------------------------------------------------------ divisao de turma


def test_divisao_paralela_deve_cair_no_mesmo_horario():
    c = Cenario()
    lab1 = c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    lab2 = c.espaco("Lab 2", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    pa, pb = c.professor("Ana"), c.professor("Bruno")
    turma = c.turma(alunos=36)
    d = c.disciplina("PW", aulas=2, laboratorio="info", divisao=ModoDivisao.PARALELA)
    oa = c.oferta(turma, d, pa, subturma="A")
    ob = c.oferta(turma, d, pb, subturma="B")

    c.aloca_bloco(oa, dia=0, ordem_inicial=1, espaco=lab1)
    c.aloca_bloco(ob, dia=0, ordem_inicial=1, espaco=lab2)
    assert c.tipos() == set(), "A e B no mesmo horario e' o esperado numa divisao paralela"

    c.estado.alocacoes = [a for a in c.estado.alocacoes if a.oferta_id != ob]
    c.aloca_bloco(ob, dia=1, ordem_inicial=1, espaco=lab2)
    assert "DIVISAO_PARALELA_SEPARADA" in c.tipos()


def test_divisao_sequencial_nao_pode_coincidir():
    c = Cenario()
    lab1 = c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    lab2 = c.espaco("Lab 2", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=20)
    pa = c.professor("Ana")
    turma = c.turma(alunos=36)
    d = c.disciplina("AI", aulas=2, laboratorio="info", divisao=ModoDivisao.SEQUENCIAL)
    oa = c.oferta(turma, d, pa, subturma="A")
    ob = c.oferta(turma, d, pa, subturma="B")

    c.aloca_bloco(oa, dia=0, ordem_inicial=1, espaco=lab1)
    c.aloca_bloco(ob, dia=0, ordem_inicial=3, espaco=lab2)
    assert "DIVISAO_SEQUENCIAL_SOBREPOSTA" not in c.tipos()

    c.estado.alocacoes = [a for a in c.estado.alocacoes if a.oferta_id != ob]
    c.aloca_bloco(ob, dia=0, ordem_inicial=1, espaco=lab2)
    assert "DIVISAO_SEQUENCIAL_SOBREPOSTA" in c.tipos()


def test_aula_de_turma_inteira_nao_pode_coincidir_com_subturma():
    c = Cenario()
    lab = c.espaco("Lab 1", tipo=TipoEspaco.LABORATORIO, tipo_laboratorio="info", capacidade=40)
    sala = c.espaco("Sala 1")
    pa, pb = c.professor("Ana"), c.professor("Bruno")
    turma = c.turma(alunos=36)
    dividida = c.disciplina("PW", aulas=2, laboratorio="info", divisao=ModoDivisao.PARALELA)
    inteira = c.disciplina("BD", aulas=2)

    c.aloca_bloco(c.oferta(turma, dividida, pa, subturma="A"), 0, 1, espaco=lab)
    c.aloca_bloco(c.oferta(turma, inteira, pb), 0, 1, espaco=sala)
    assert "CHOQUE_TURMA" in c.tipos()


# ------------------------------------------------------------ carga e jornada


def test_carga_semanal_acima_do_limite_do_vinculo():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana", carga_max_semanal=2)
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4)
    o = c.oferta(turma, d, prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=1, ordem_inicial=1, espaco=sala, bloco_idx=1)

    violacao = c.de_tipo("CARGA_ACIMA_DO_LIMITE")[0]
    assert "4 aulas semanais" in violacao.mensagem and "limite do vínculo é 2" in violacao.mensagem


def test_carga_sem_limite_no_vinculo_usa_o_da_unidade():
    c = Cenario(carga_max_semanal=2)
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4)
    o = c.oferta(turma, d, prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=1, ordem_inicial=1, espaco=sala, bloco_idx=1)
    assert "CARGA_ACIMA_DO_LIMITE" in c.tipos()


def test_choque_entre_unidades():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    d = c.disciplina("MAT", aulas=2)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=sala)
    c.aula_em_outra_unidade(prof, dia=0, inicio_min=19 * 60, fim_min=20 * 60)

    violacao = c.de_tipo("CHOQUE_ENTRE_UNIDADES")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "Etec Teste" in violacao.mensagem and "Paulo" in violacao.mensagem


def test_deslocamento_insuficiente_entre_unidades():
    c = Cenario(deslocamento_entre_unidades_min=45)
    sala = c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    d = c.disciplina("MAT", aulas=2)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=1, espaco=sala)
    # termina 18h40 na outra unidade, comeca 19h00 aqui: 20 min de janela
    c.aula_em_outra_unidade(prof, dia=0, inicio_min=17 * 60 + 50, fim_min=18 * 60 + 40)

    violacao = c.de_tipo("DESLOCAMENTO_INSUFICIENTE")[0]
    assert violacao.severidade == Severidade.ALERTA
    assert "20 min" in violacao.mensagem and "45 min" in violacao.mensagem


def test_interjornada_somando_as_duas_unidades():
    """22h30 na Fatec e 07h00 na Etec do dia seguinte = 8,5 h de descanso."""
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    d = c.disciplina("MAT", aulas=2)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=3, espaco=sala)
    c.aula_em_outra_unidade(prof, dia=1, inicio_min=7 * 60, fim_min=7 * 60 + 50)

    violacao = c.de_tipo("INTERJORNADA")[0]
    assert violacao.severidade == Severidade.ALERTA  # padrao e' "aviso"
    assert "8,5 h de descanso" in violacao.mensagem
    assert "art. 66" in violacao.mensagem


@pytest.mark.parametrize(
    ("modo", "esperado"),
    [("off", None), ("aviso", Severidade.ALERTA), ("rigida", Severidade.BLOQUEANTE)],
)
def test_interjornada_respeita_o_modo_configurado(modo, esperado):
    c = Cenario()
    c.config.interjornada.modo = modo
    sala = c.espaco("Sala 1")
    prof = c.professor("Paulo")
    turma = c.turma()
    d = c.disciplina("MAT", aulas=2)
    c.aloca_bloco(c.oferta(turma, d, prof), dia=0, ordem_inicial=3, espaco=sala)
    c.aula_em_outra_unidade(prof, dia=1, inicio_min=7 * 60, fim_min=7 * 60 + 50)

    violacoes = c.de_tipo("INTERJORNADA")
    if esperado is None:
        assert violacoes == []
    else:
        assert violacoes[0].severidade == esperado


def test_limite_diario_desligado_por_padrao():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4, max_blocos_por_dia=2)
    o = c.oferta(turma, d, prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=0, ordem_inicial=3, espaco=sala, bloco_idx=1)
    assert "LIMITE_DIARIO" not in c.tipos()


def test_limite_diario_de_aulas_consecutivas_quando_ligado():
    c = Cenario()
    c.config.limite_diario.ativo = True
    c.config.limite_diario.max_consecutivas = 2
    c.config.limite_diario.max_intercaladas = 6
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=3, tamanho_bloco=3, max_blocos_por_dia=1)
    o = c.oferta(turma, d, prof)
    for ordem in (1, 2, 3):
        c.aloca(o, dia=0, ordem=ordem, espaco=sala, bloco_idx=0)

    violacao = next(v for v in c.de_tipo("LIMITE_DIARIO") if "seguidas" in v.mensagem)
    assert "3 aulas seguidas" in violacao.mensagem


def test_limite_diario_de_aulas_no_dia_quando_ligado():
    c = Cenario()
    c.config.limite_diario.ativo = True
    c.config.limite_diario.max_intercaladas = 2
    c.config.limite_diario.max_consecutivas = 8
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4, max_blocos_por_dia=2)
    o = c.oferta(turma, d, prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=0, ordem_inicial=3, espaco=sala, bloco_idx=1)

    violacao = next(v for v in c.de_tipo("LIMITE_DIARIO") if "na segunda" in v.mensagem)
    assert "4 aulas na segunda" in violacao.mensagem


# -------------------------------------------------------------------- janelas


def test_horario_vago_no_fim_do_dia_nao_e_janela():
    c = cenario_valido()  # todas as turmas saem depois da 2a aula
    assert "JANELA_TURMA" not in c.tipos()


def test_horario_vago_no_meio_do_dia_e_janela_da_turma():
    c = Cenario()
    sala = c.espaco("Sala 1")
    pa, pb = c.professor("Ana"), c.professor("Bruno")
    turma = c.turma()
    d1, d2 = (
        c.disciplina("ALP", aulas=1, tamanho_bloco=1),
        c.disciplina("ESW", aulas=1, tamanho_bloco=1),
    )
    sala2 = c.espaco("Sala 2")
    c.aloca(c.oferta(turma, d1, pa), dia=0, ordem=1, espaco=sala)
    c.aloca(c.oferta(turma, d2, pb), dia=0, ordem=3, espaco=sala2)

    violacoes = c.de_tipo("JANELA_TURMA")
    assert len(violacoes) == 1
    assert "2ª aula está vaga" in violacoes[0].mensagem
    assert violacoes[0].entidades["ordem"] == 2


def test_janela_do_professor_conta_o_tamanho_do_buraco():
    c = Cenario()
    sala = c.espaco("Sala 1")
    sala2 = c.espaco("Sala 2")
    prof = c.professor("Ana")
    t1, t2 = c.turma("1o sem"), c.turma("2o sem")
    d1 = c.disciplina("ALP", aulas=1, tamanho_bloco=1)
    d2 = c.disciplina("ESW", aulas=1, tamanho_bloco=1)
    c.aloca(c.oferta(t1, d1, prof), dia=0, ordem=1, espaco=sala)
    c.aloca(c.oferta(t2, d2, prof), dia=0, ordem=4, espaco=sala2)

    violacao = c.de_tipo("JANELA_PROFESSOR")[0]
    assert violacao.entidades["dia"] == 0
    assert len(violacao.entidades["faixas"]) == 2


def test_janela_do_professor_nao_confunde_turnos_diferentes():
    """Manha e noite tem, cada uma, uma "1a aula"; contar por `ordem`
    inventaria uma janela que nao existe."""
    c = Cenario()
    manha = c.turno(2, range(0, 5), [(1, 7 * 60, 7 * 60 + 50, 1), (2, 7 * 60 + 50, 8 * 60 + 40, 1)])
    sala, sala2 = c.espaco("Sala 1"), c.espaco("Sala 2")
    prof = c.professor("Paulo")
    noturna = c.turma("1o sem")
    diurna = c.turma("1a série", modelo=manha)
    d1 = c.disciplina("MAT", aulas=1, tamanho_bloco=1)
    d2 = c.disciplina("LPG", aulas=1, tamanho_bloco=1)

    c.aloca(c.oferta(noturna, d1, prof), dia=0, ordem=1, espaco=sala)
    c.aloca(c.oferta(diurna, d2, prof), dia=0, ordem=1, espaco=sala2, slot=manha * 1000 + 1)

    janelas = c.de_tipo("JANELA_PROFESSOR")
    # so' a janela real: entre a aula da manha (termina 07h50) e a da noite (19h00)
    assert all("segunda" in v.mensagem for v in janelas)
    assert len(janelas) <= 1


# ------------------------------------------------------------------ robustez


def test_referencia_para_slot_inexistente_nao_quebra_o_validador():
    c = cenario_valido()
    c.aloca(list(c.estado.ofertas)[0], dia=0, ordem=1, slot=999_999)
    violacao = c.de_tipo("REFERENCIA_QUEBRADA")[0]
    assert violacao.severidade == Severidade.BLOQUEANTE
    assert "999999" in violacao.mensagem


def test_grade_vazia_sem_ofertas_nao_gera_violacao():
    assert Cenario().validar() == []


def test_todo_slot_id_da_fabrica_segue_a_convencao():
    assert slot_id(0, 1) == 1
    assert slot_id(4, 3) == 43


def test_ausencia_de_marcacao_significa_disponivel():
    c = cenario_valido()
    assert (
        c.estado.status_disponibilidade(c.ids["ana"], slot_id(0, 1))
        == StatusDisponibilidade.DISPONIVEL
    )


# -------------------------------------------------------- concentrar no dia


def test_disciplina_concentrada_em_dois_dias_e_alerta():
    """Alerta, nao bloqueante: e' o aviso que diz qual disciplina o solver nao
    conseguiu concentrar, e bloquear impediria mover a disciplina de dia na
    edicao manual (arrastar leva um par por vez)."""
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    o = c.oferta(turma, c.disciplina("ALP", aulas=4, concentrar=True), prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=2, ordem_inicial=1, espaco=sala, bloco_idx=1)

    violacao = c.de_tipo("AULAS_NAO_CONCENTRADAS")[0]
    assert violacao.severidade == Severidade.ALERTA
    assert "segunda e quarta" in violacao.mensagem
    assert "BLOCOS_POR_DIA" not in c.tipos()


def test_disciplina_concentrada_no_mesmo_dia_mas_partida_e_alerta():
    manha = [
        (1, 450, 500, 1),
        (2, 500, 550, 1),
        (3, 560, 610, 2),
        (4, 610, 660, 2),
        (5, 670, 720, 3),
        (6, 720, 770, 3),
    ]
    c = Cenario(horarios=manha)
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    o = c.oferta(turma, c.disciplina("ALP", aulas=4, concentrar=True), prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=0, ordem_inicial=5, espaco=sala, bloco_idx=1)

    violacao = c.de_tipo("AULAS_NAO_CONCENTRADAS")[0]
    assert "não estão seguidas" in violacao.mensagem


def test_disciplina_concentrada_e_seguida_nao_gera_aviso_nem_estoura_blocos_por_dia():
    c = Cenario()
    sala = c.espaco("Sala 1")
    prof = c.professor("Ana")
    turma = c.turma()
    o = c.oferta(turma, c.disciplina("ALP", aulas=4, concentrar=True), prof)
    c.aloca_bloco(o, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(o, dia=0, ordem_inicial=3, espaco=sala, bloco_idx=1)

    assert {"AULAS_NAO_CONCENTRADAS", "BLOCOS_POR_DIA"} & c.tipos() == set()
