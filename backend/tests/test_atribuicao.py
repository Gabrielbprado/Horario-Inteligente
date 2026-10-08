"""Etapa 4: atribuicao sugerida (app/scheduling/assignment.py)."""

from app.models import OrigemHabilitacao, Severidade, TipoContrato
from app.scheduling.assignment import (
    classificar,
    criterio_decisivo,
    ociosidade,
    sugerir_atribuicao,
)
from tests.fabrica import Cenario


def _habilita(c: Cenario, professor: int, disciplina: int, origem=OrigemHabilitacao.CONCURSO):
    c.estado.habilitacoes[(professor, disciplina)] = origem


def _sugerir(c: Cenario, **kw):
    return sugerir_atribuicao(c.estado, c.config, **kw)


# --------------------------------------------------------------- classificacao


def test_classificacao_ordena_por_pontuacao():
    c = Cenario()
    baixa = c.professor("Baixa", pontuacao=50)
    alta = c.professor("Alta", pontuacao=90)
    media = c.professor("Media", pontuacao=70)

    assert [v.professor_id for v in classificar(c.estado, c.config)] == [alta, media, baixa]


def test_empate_de_pontuacao_vai_para_a_assiduidade():
    c = Cenario()
    gisele = c.professor("Gisele", pontuacao=61, pont_assiduidade=20, pont_titulacao=24)
    henrique = c.professor("Henrique", pontuacao=61, pont_assiduidade=12, pont_titulacao=26)

    assert [v.professor_id for v in classificar(c.estado, c.config)] == [gisele, henrique]


def test_ordem_dos_desempates_e_configuravel():
    """Trocar a ordem em config_regras muda quem fica na frente."""
    c = Cenario()
    a = c.professor("A", pontuacao=61, pont_assiduidade=20, pont_titulacao=10)
    b = c.professor("B", pontuacao=61, pont_assiduidade=12, pont_titulacao=90)

    assert [v.professor_id for v in classificar(c.estado, c.config)][0] == a

    c.config.atribuicao.desempates = ["titulacao", "assiduidade"]
    assert [v.professor_id for v in classificar(c.estado, c.config)][0] == b


def test_fatec_poe_contrato_indeterminado_na_frente():
    c = Cenario()
    c.config.atribuicao.regra = "FATEC"
    temporario = c.professor("Temporário", pontuacao=95, tipo_contrato=TipoContrato.DETERMINADO)
    efetivo = c.professor("Efetivo", pontuacao=40, tipo_contrato=TipoContrato.INDETERMINADO)

    assert [v.professor_id for v in classificar(c.estado, c.config)] == [efetivo, temporario]


def test_etec_ignora_o_tipo_de_contrato_na_ordenacao():
    c = Cenario()
    c.config.atribuicao.regra = "ETEC"
    temporario = c.professor("Temporário", pontuacao=95, tipo_contrato=TipoContrato.DETERMINADO)
    efetivo = c.professor("Efetivo", pontuacao=40, tipo_contrato=TipoContrato.INDETERMINADO)

    assert [v.professor_id for v in classificar(c.estado, c.config)] == [temporario, efetivo]


# ----------------------------------------------------------- criterio decisivo


def test_criterio_cita_as_duas_pontuacoes():
    c = Cenario()
    ana = c.professor("Ana", pontuacao=87.5)
    bruno = c.professor("Bruno", pontuacao=72)
    texto = criterio_decisivo(c.estado.vinculos[ana], c.estado.vinculos[bruno], c.config)
    assert texto == "maior pontuação (87,5 × 72)"


def test_criterio_de_empate_nomeia_o_desempate_usado():
    c = Cenario()
    gisele = c.professor("Gisele", pontuacao=61, pont_assiduidade=20)
    henrique = c.professor("Henrique", pontuacao=61, pont_assiduidade=12)
    texto = criterio_decisivo(c.estado.vinculos[gisele], c.estado.vinculos[henrique], c.config)
    assert "empate em 61 pontos" in texto
    assert "assiduidade e pontualidade (20 × 12)" in texto


def test_criterio_na_fatec_menciona_o_contrato():
    c = Cenario()
    c.config.atribuicao.regra = "FATEC"
    efetivo = c.professor("Efetivo", pontuacao=40, tipo_contrato=TipoContrato.INDETERMINADO)
    temp = c.professor("Temp", pontuacao=95, tipo_contrato=TipoContrato.DETERMINADO)
    texto = criterio_decisivo(c.estado.vinculos[efetivo], c.estado.vinculos[temp], c.config)
    assert texto == "contrato por prazo indeterminado"


# ------------------------------------------------------------------ sugestao


def test_melhor_classificado_leva_a_oferta_disputada():
    c = Cenario()
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4)
    oferta = c.oferta(turma, d)
    ana = c.professor("Ana", pontuacao=87.5)
    bruno = c.professor("Bruno", pontuacao=72)
    _habilita(c, ana, d)
    _habilita(c, bruno, d)

    resultado = _sugerir(c)
    assert resultado.atribuicoes[oferta] == ana
    assert resultado.sem_professor == []

    disputa = resultado.disputas[0]
    assert disputa.vencedor_id == ana
    assert disputa.perdedores_ids == [bruno]
    assert disputa.criterio == "maior pontuação (87,5 × 72)"


def test_aviso_de_prioridade_cita_ganhador_perdedor_e_motivo():
    c = Cenario()
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4)
    c.oferta(turma, d)
    ana = c.professor("Ana", pontuacao=87.5)
    c.professor("Bruno", pontuacao=72)
    for pid in c.estado.vinculos:
        _habilita(c, pid, d)

    aviso = next(v for v in _sugerir(c).avisos if v.tipo == "PRIORIDADE_NA_ATRIBUICAO")
    assert aviso.severidade == Severidade.ALERTA
    assert "Ana" in aviso.mensagem and "Bruno" in aviso.mensagem
    assert "maior pontuação (87,5 × 72)" in aviso.mensagem
    assert "art. 7º" in aviso.mensagem
    assert aviso.entidades["vencedor_id"] == ana


def test_disputa_com_empate_registra_o_desempate():
    c = Cenario()
    turma = c.turma()
    d = c.disciplina("DW1", aulas=4)
    c.oferta(turma, d)
    gisele = c.professor("Gisele", pontuacao=61, pont_assiduidade=20)
    henrique = c.professor("Henrique", pontuacao=61, pont_assiduidade=12)
    _habilita(c, gisele, d)
    _habilita(c, henrique, d)

    disputa = _sugerir(c).disputas[0]
    assert disputa.vencedor_id == gisele
    assert "assiduidade e pontualidade (20 × 12)" in disputa.criterio


def test_sem_disputa_quando_so_um_docente_esta_habilitado():
    c = Cenario()
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4)
    c.oferta(turma, d)
    ana = c.professor("Ana", pontuacao=87.5)
    c.professor("Bruno", pontuacao=72)  # nao habilitado
    _habilita(c, ana, d)

    resultado = _sugerir(c)
    assert resultado.disputas == []
    assert resultado.avisos == []


def test_carga_maxima_limita_quanto_o_primeiro_classificado_leva():
    c = Cenario()
    turma = c.turma()
    ana = c.professor("Ana", pontuacao=90, carga_max_semanal=4)
    bruno = c.professor("Bruno", pontuacao=50, carga_max_semanal=20)
    ofertas = []
    for sigla in ("A", "B", "C"):
        d = c.disciplina(sigla, aulas=4)
        ofertas.append(c.oferta(turma, d))
        _habilita(c, ana, d)
        _habilita(c, bruno, d)

    resultado = _sugerir(c)
    assert list(resultado.atribuicoes.values()).count(ana) == 1
    assert list(resultado.atribuicoes.values()).count(bruno) == 2
    assert resultado.sem_professor == []


def test_oferta_sem_ninguem_habilitado_vira_aviso_bloqueante():
    c = Cenario()
    turma = c.turma()
    oferta = c.oferta(turma, c.disciplina("ALP"))
    c.professor("Ana")

    resultado = _sugerir(c)
    assert resultado.sem_professor == [oferta]
    aviso = next(v for v in resultado.avisos if v.tipo == "OFERTA_SEM_CANDIDATO")
    assert aviso.severidade == Severidade.BLOQUEANTE
    assert "nenhum docente com vínculo nesta unidade está habilitado" in aviso.mensagem


def test_oferta_sem_ninguem_com_carga_livre_explica_a_diferenca():
    c = Cenario()
    turma = c.turma()
    d1 = c.disciplina("A", aulas=4)
    d2 = c.disciplina("B", aulas=4)
    c.oferta(turma, d1)
    c.oferta(turma, d2)
    ana = c.professor("Ana", carga_max_semanal=4)
    _habilita(c, ana, d1)
    _habilita(c, ana, d2)

    aviso = next(v for v in _sugerir(c).avisos if v.tipo == "OFERTA_SEM_CANDIDATO")
    assert "já estão com a carga máxima" in aviso.mensagem


def test_prioridade_de_componente_concurso_antes_de_habilitado():
    """Na vez do docente, ele pega primeiro o componente do concurso dele."""
    c = Cenario()
    turma = c.turma()
    concurso = c.disciplina("CONC", aulas=4)
    outro = c.disciplina("OUTRO", aulas=4)
    o_concurso = c.oferta(turma, concurso)
    o_outro = c.oferta(turma, outro)

    ana = c.professor("Ana", pontuacao=90, carga_max_semanal=4)
    bruno = c.professor("Bruno", pontuacao=50, carga_max_semanal=20)
    _habilita(c, ana, outro, OrigemHabilitacao.HABILITADO)
    _habilita(c, ana, concurso, OrigemHabilitacao.CONCURSO)
    _habilita(c, bruno, concurso)
    _habilita(c, bruno, outro)

    resultado = _sugerir(c)
    assert resultado.atribuicoes[o_concurso] == ana
    assert resultado.atribuicoes[o_outro] == bruno


# --------------------------------------------------- manutencao x ampliacao


def test_etec_roda_a_manutencao_antes_da_ampliacao():
    """Kelly (menor pontuação) mantém o que já lecionava, mesmo com Iara
    habilitada e melhor classificada."""
    c = Cenario()
    c.config.atribuicao.regra = "ETEC"
    turma = c.turma()
    pw = c.disciplina("PW", aulas=4)
    lp = c.disciplina("LP", aulas=4)
    o_pw = c.oferta(turma, pw)
    o_lp = c.oferta(turma, lp)

    iara = c.professor("Iara", pontuacao=91, carga_max_semanal=8)
    kelly = c.professor("Kelly", pontuacao=70, carga_max_semanal=8)
    _habilita(c, iara, pw)
    _habilita(c, iara, lp)
    _habilita(c, kelly, pw, OrigemHabilitacao.ANTERIOR)

    resultado = _sugerir(c)
    assert resultado.atribuicoes[o_pw] == kelly, "manutenção vem antes da ampliação"
    assert resultado.atribuicoes[o_lp] == iara


def test_fatec_nao_tem_passada_de_manutencao():
    """Na Fatec a mesma situação dá o componente ao melhor classificado."""
    c = Cenario()
    c.config.atribuicao.regra = "FATEC"
    turma = c.turma()
    pw = c.disciplina("PW", aulas=4)
    o_pw = c.oferta(turma, pw)

    iara = c.professor("Iara", pontuacao=91, carga_max_semanal=8)
    kelly = c.professor("Kelly", pontuacao=70, carga_max_semanal=8)
    _habilita(c, iara, pw)
    _habilita(c, kelly, pw, OrigemHabilitacao.ANTERIOR)

    assert _sugerir(c).atribuicoes[o_pw] == iara


def test_manutencao_tambem_respeita_a_ordem_de_classificacao():
    c = Cenario()
    c.config.atribuicao.regra = "ETEC"
    turma = c.turma()
    pw = c.disciplina("PW", aulas=4)
    o_pw = c.oferta(turma, pw)

    melhor = c.professor("Melhor", pontuacao=80, carga_max_semanal=4)
    pior = c.professor("Pior", pontuacao=60, carga_max_semanal=4)
    _habilita(c, melhor, pw, OrigemHabilitacao.ANTERIOR)
    _habilita(c, pior, pw, OrigemHabilitacao.ANTERIOR)

    assert _sugerir(c).atribuicoes[o_pw] == melhor


# ------------------------------------------------------------- preservacao


def test_atribuicao_manual_e_preservada_e_conta_na_carga():
    c = Cenario()
    turma = c.turma()
    d1 = c.disciplina("A", aulas=4)
    d2 = c.disciplina("B", aulas=4)
    o1, o2 = c.oferta(turma, d1), c.oferta(turma, d2)
    ana = c.professor("Ana", pontuacao=90, carga_max_semanal=4)
    bruno = c.professor("Bruno", pontuacao=50, carga_max_semanal=20)
    for d in (d1, d2):
        _habilita(c, ana, d)
        _habilita(c, bruno, d)

    resultado = _sugerir(c, preservar={o1: ana})
    assert resultado.atribuicoes[o1] == ana
    assert resultado.novas == {o2: bruno}, "Ana já está no limite por causa da manual"


def test_sugerir_e_reproduzivel():
    def montar() -> Cenario:
        c = Cenario()
        turma = c.turma()
        for i in range(5):
            d = c.disciplina(f"D{i}", aulas=4)
            c.oferta(turma, d)
        for i in range(4):
            p = c.professor(f"P{i}", pontuacao=50 + i, carga_max_semanal=8)
            for did in list(c.estado.disciplinas):
                _habilita(c, p, did)
        return c

    assert _sugerir(montar()).atribuicoes == _sugerir(montar()).atribuicoes


def test_ociosidade_mostra_quanto_ainda_cabe():
    c = Cenario()
    turma = c.turma()
    d = c.disciplina("ALP", aulas=4)
    c.oferta(turma, d)
    ana = c.professor("Ana", carga_max_semanal=10)
    _habilita(c, ana, d)

    resultado = _sugerir(c)
    assert ociosidade(c.estado, c.config, resultado)[ana] == 6


# ------------------------------------------------------------ divisao paralela


def test_divisao_paralela_nao_pode_cair_toda_no_mesmo_professor():
    """A e B acontecem ao mesmo tempo em salas diferentes: precisam de dois
    docentes, senao a grade fica impossível de montar."""
    from app.models import ModoDivisao

    c = Cenario()
    turma = c.turma()
    pw = c.disciplina("PW", aulas=4, divisao=ModoDivisao.PARALELA)
    a = c.oferta(turma, pw, subturma="A")
    b = c.oferta(turma, pw, subturma="B")
    kelly = c.professor("Kelly", pontuacao=90, carga_max_semanal=20)
    joao = c.professor("Joao", pontuacao=70, carga_max_semanal=20)
    _habilita(c, kelly, pw)
    _habilita(c, joao, pw)

    resultado = _sugerir(c)
    assert resultado.atribuicoes[a] == kelly
    assert resultado.atribuicoes[b] == joao


def test_divisao_paralela_com_um_unico_habilitado_fica_sem_professor():
    from app.models import ModoDivisao

    c = Cenario()
    turma = c.turma()
    pw = c.disciplina("PW", aulas=4, divisao=ModoDivisao.PARALELA)
    a = c.oferta(turma, pw, subturma="A")
    b = c.oferta(turma, pw, subturma="B")
    kelly = c.professor("Kelly", carga_max_semanal=20)
    _habilita(c, kelly, pw)

    resultado = _sugerir(c)
    assert resultado.atribuicoes[a] == kelly
    assert resultado.sem_professor == [b]


def test_divisao_sequencial_pode_ficar_com_o_mesmo_professor():
    """Na sequencial A e B sao em horários diferentes — é o mesmo docente."""
    from app.models import ModoDivisao

    c = Cenario()
    turma = c.turma()
    ai = c.disciplina("AI", aulas=2, divisao=ModoDivisao.SEQUENCIAL)
    a = c.oferta(turma, ai, subturma="A")
    b = c.oferta(turma, ai, subturma="B")
    kelly = c.professor("Kelly", carga_max_semanal=20)
    _habilita(c, kelly, ai)

    resultado = _sugerir(c)
    assert resultado.atribuicoes[a] == kelly
    assert resultado.atribuicoes[b] == kelly


def test_manutencao_nao_e_descrita_como_maior_pontuacao():
    """O vencedor da manutenção pode estar ABAIXO na classificação; dizer
    "maior pontuação (70 × 78,5)" seria falso."""
    c = Cenario()
    c.config.atribuicao.regra = "ETEC"
    turma = c.turma()
    pw = c.disciplina("PW", aulas=4)
    c.oferta(turma, pw)
    kelly = c.professor("Kelly", pontuacao=70, carga_max_semanal=20)
    joao = c.professor("Joao", pontuacao=78.5, carga_max_semanal=20)
    _habilita(c, kelly, pw, OrigemHabilitacao.ANTERIOR)
    _habilita(c, joao, pw)

    disputa = _sugerir(c).disputas[0]
    assert disputa.vencedor_id == kelly
    assert "maior pontuação" not in disputa.criterio
    assert "manutenção" in disputa.criterio

    aviso = next(v for v in _sugerir(c).avisos if v.tipo == "PRIORIDADE_NA_ATRIBUICAO")
    assert "Deliberação CEETEPS 23/2015" in aviso.mensagem
    assert "art. 7º" not in aviso.mensagem, "a citação precisa acompanhar o motivo"


def test_manutencao_do_melhor_classificado_cita_a_pontuacao():
    c = Cenario()
    c.config.atribuicao.regra = "ETEC"
    turma = c.turma()
    pw = c.disciplina("PW", aulas=4)
    c.oferta(turma, pw)
    melhor = c.professor("Melhor", pontuacao=90, carga_max_semanal=20)
    pior = c.professor("Pior", pontuacao=60, carga_max_semanal=20)
    _habilita(c, melhor, pw, OrigemHabilitacao.ANTERIOR)
    _habilita(c, pior, pw)

    disputa = _sugerir(c).disputas[0]
    assert disputa.vencedor_id == melhor
    assert disputa.criterio == "maior pontuação (90 × 60)"
