"""Etapa 1: o modelo de dados e o seed sustentam os cenarios da spec."""

from sqlalchemy import func, select

from app.models import (
    Curso,
    Disciplina,
    Disponibilidade,
    Espaco,
    Modalidade,
    ModalidadeAula,
    ModoDivisao,
    Oferta,
    Professor,
    Slot,
    StatusDisponibilidade,
    Turma,
    Unidade,
    VinculoUnidade,
)
from app.presets import PRESETS_TURNO, config_regras_para
from app.services import blocos_de

# ------------------------------------------------------------------------ presets


def test_blocos_de_decompoe_carga_semanal():
    assert blocos_de(4, 2) == [2, 2]
    assert blocos_de(5, 2) == [2, 2, 1]
    assert blocos_de(2, 2) == [2]
    assert blocos_de(3, 2) == [2, 1]
    assert blocos_de(0, 2) == []


def test_preset_fatec_noturno_tem_2_blocos_de_2_aulas_sem_atravessar_intervalo():
    preset = PRESETS_TURNO["fatec_noturno"]
    segunda = preset.dias[0]
    assert [len(b) for b in segunda] == [2, 2]
    # o intervalo aparece como descontinuidade entre o fim de um bloco e o inicio do outro
    assert segunda[0][-1][1] == "20:40"
    assert segunda[1][0][0] == "20:50"
    assert sorted(preset.dias) == [0, 1, 2, 3, 4]


def test_preset_etec_noturno_fecha_1900_2300_com_intervalo_2050_2110():
    dia = PRESETS_TURNO["etec_tecnico_noturno"].dias[0]
    assert dia[0][0][0] == "19:00"
    assert dia[0][-1][1] == "20:50"
    assert dia[1][0][0] == "21:10"
    assert dia[1][-1][1] == "23:00"


def test_config_regras_difere_por_tipo_de_unidade():
    from app.models import TipoUnidade

    fatec = config_regras_para(TipoUnidade.FATEC)
    etec = config_regras_para(TipoUnidade.ETEC)
    assert fatec["carga_max_semanal"] == 29
    assert etec["carga_max_semanal"] == 34
    assert fatec["atribuicao"]["regra"] == "FATEC"
    assert etec["atribuicao"]["regra"] == "ETEC"
    # limite diario da CLT antiga nasce desligado (Lei 13.415/2017)
    assert fatec["limite_diario"]["ativo"] is False
    assert etec["interjornada"] == {"modo": "aviso", "horas": 11}


def test_config_regras_nao_compartilha_estado_entre_unidades():
    from app.models import TipoUnidade

    a = config_regras_para(TipoUnidade.FATEC)
    b = config_regras_para(TipoUnidade.FATEC)
    a["pesos"]["janela_turma"] = 1
    assert b["pesos"]["janela_turma"] == 1000


# --------------------------------------------------------------------------- seed


def test_seed_cria_as_duas_unidades_com_presets(escopo_seed, db):
    unidades = {u.nome: u for u in db.scalars(select(Unidade))}
    assert set(unidades) == {"Fatec Taquaritinga", "Etec Taquaritinga"}

    fatec = unidades["Fatec Taquaritinga"]
    assert fatec.config_regras["carga_max_semanal"] == 29
    assert fatec.config_regras["usa_sabado"] is True
    assert {m.preset_origem for m in fatec.modelos_turno} == {
        "fatec_noturno",
        "fatec_noturno_sabado",
        "fatec_manha",
    }

    etec = unidades["Etec Taquaritinga"]
    assert etec.config_regras["carga_max_semanal"] == 34
    assert etec.config_regras["atribuicao"]["regra"] == "ETEC"


def test_slots_do_modelo_agrupam_blocos_contiguos(escopo_seed, db):
    modelo = next(
        m
        for u in db.scalars(select(Unidade))
        for m in u.modelos_turno
        if m.preset_origem == "fatec_noturno_sabado"
    )
    seg = sorted((s for s in modelo.slots if s.dia_semana == 0), key=lambda s: s.ordem)
    assert [(s.ordem, s.bloco_id) for s in seg] == [(1, 1), (2, 1), (3, 2), (4, 2)]
    # sabado tem blocos de 3 aulas
    sab = sorted((s for s in modelo.slots if s.dia_semana == 5), key=lambda s: s.ordem)
    assert [s.bloco_id for s in sab] == [1, 1, 1, 2, 2, 2]
    assert len(modelo.slots) == 4 * 5 + 6


def test_dsm_tem_tres_turmas_de_24_aulas_semanais(escopo_seed, db):
    dsm = db.scalar(select(Curso).where(Curso.sigla == "DSM"))
    assert dsm.modalidade == Modalidade.CST
    assert len(dsm.turmas) == 3
    for turma in dsm.turmas:
        aulas = sum(o.disciplina.aulas_semanais for o in turma.ofertas)
        assert aulas == 24, f"{turma.periodo} tem {aulas} aulas"
        # cabe no modelo com sabado (26 slots), nao caberia em 5 noites (20)
        assert aulas <= len(turma.modelo_turno.slots)


def test_cada_semestre_do_dsm_tem_uma_disciplina_remota_sem_laboratorio(escopo_seed, db):
    dsm = db.scalar(select(Curso).where(Curso.sigla == "DSM"))
    for periodo in ("1o sem", "2o sem", "3o sem"):
        remotas = [
            d
            for d in dsm.disciplinas
            if d.periodo == periodo and d.modalidade == ModalidadeAula.REMOTA
        ]
        assert len(remotas) == 1
        assert remotas[0].precisa_laboratorio is False


def test_divisao_de_turma_gera_duas_ofertas(escopo_seed, db):
    pw = db.scalar(select(Disciplina).where(Disciplina.sigla == "PW"))
    assert pw.divisao_turma is True and pw.modo_divisao == ModoDivisao.PARALELA
    assert sorted(o.subturma for o in pw.ofertas) == ["A", "B"]

    ai = db.scalar(select(Disciplina).where(Disciplina.sigla == "AI"))
    assert ai.modo_divisao == ModoDivisao.SEQUENCIAL
    assert sorted(o.subturma for o in ai.ofertas) == ["A", "B"]

    # disciplina sem divisao continua com uma unica oferta de subturma nula
    lp = db.scalar(select(Disciplina).where(Disciplina.sigla == "LP"))
    assert [o.subturma for o in lp.ofertas] == [None]


def test_sincronizar_ofertas_e_idempotente_e_reage_a_mudanca_de_divisao(escopo_seed, db):
    from app.services import sincronizar_ofertas

    turma = db.scalar(
        select(Turma).join(Curso).where(Curso.sigla == "TDS", Turma.periodo == "Modulo I")
    )
    antes = len(turma.ofertas)
    sincronizar_ofertas(db, turma)
    assert len(turma.ofertas) == antes

    pw = db.scalar(select(Disciplina).where(Disciplina.sigla == "PW"))
    pw.divisao_turma = False
    db.flush()
    sincronizar_ofertas(db, turma)
    assert [o.subturma for o in turma.ofertas if o.disciplina_id == pw.id] == [None]
    assert len(turma.ofertas) == antes - 1


def test_professor_compartilhado_tem_vinculo_nas_duas_unidades(escopo_seed, db):
    paulo = db.scalar(select(Professor).where(Professor.identificador == "paulo.serrano"))
    unidades = {v.unidade.nome for v in paulo.vinculos}
    assert unidades == {"Fatec Taquaritinga", "Etec Taquaritinga"}
    assert {h.disciplina.sigla for h in paulo.habilitacoes} == {"MAT", "LPG"}


def test_cenario_de_interjornada_existe_no_seed(escopo_seed, db):
    """A aula mais tarde da Fatec e a mais cedo da Etec ficam a menos de 11 h."""
    paulo = db.scalar(select(Professor).where(Professor.identificador == "paulo.serrano"))
    modelos = {}
    for vinculo in paulo.vinculos:
        for turma in db.scalars(
            select(Turma).join(Curso).where(Curso.unidade_id == vinculo.unidade_id)
        ):
            for oferta in turma.ofertas:
                if any(h.disciplina_id == oferta.disciplina_id for h in paulo.habilitacoes):
                    modelos[vinculo.unidade.tipo.value] = turma.modelo_turno

    fim_fatec = max(s.fim for s in modelos["FATEC"].slots)
    inicio_etec = min(s.inicio for s in modelos["ETEC"].slots)
    descanso_min = (24 * 60 - fim_fatec.hour * 60 - fim_fatec.minute) + (
        inicio_etec.hour * 60 + inicio_etec.minute
    )
    assert descanso_min < 11 * 60, "o seed precisa de um cenario que viole a interjornada"


def test_cenarios_de_disputa_de_horario(escopo_seed, db):
    def pref(nome: str) -> set[int]:
        prof = db.scalar(select(Professor).where(Professor.nome == nome))
        return {
            d.slot_id
            for d in db.scalars(
                select(Disponibilidade).where(
                    Disponibilidade.professor_id == prof.id,
                    Disponibilidade.status == StatusDisponibilidade.PREFERENCIAL,
                )
            )
        }

    def vinculo(nome: str) -> VinculoUnidade:
        prof = db.scalar(select(Professor).where(Professor.nome == nome))
        return prof.vinculos[0]

    # disputa decidida por pontuacao
    assert pref("Ana Ribeiro") == pref("Bruno Carvalho") != set()
    assert vinculo("Ana Ribeiro").pontuacao > vinculo("Bruno Carvalho").pontuacao

    # disputa com empate, decidida por assiduidade
    assert pref("Gisele Tavares") == pref("Henrique Lopes") != set()
    g, h = vinculo("Gisele Tavares"), vinculo("Henrique Lopes")
    assert g.pontuacao == h.pontuacao
    assert g.pont_assiduidade > h.pont_assiduidade


def test_indisponibilidade_registrada_apenas_onde_ha_restricao(escopo_seed, db):
    """Ausencia de registro significa DISPONIVEL (evita 1 linha por slot/professor)."""
    total_slots = db.scalar(select(func.count()).select_from(Slot))
    total_disp = db.scalar(select(func.count()).select_from(Disponibilidade))
    assert 0 < total_disp < total_slots


def test_laboratorios_cobrem_as_disciplinas_que_exigem(escopo_seed, db):
    for unidade in db.scalars(select(Unidade)):
        exigidos = {
            (d.tipo_laboratorio or "").lower()
            for c in unidade.cursos
            for d in c.disciplinas
            if d.precisa_laboratorio
        }
        disponiveis = {
            (e.tipo_laboratorio or "").lower()
            for e in db.scalars(select(Espaco).where(Espaco.unidade_id == unidade.id))
        }
        assert exigidos <= disponiveis, f"{unidade.nome}: faltam labs {exigidos - disponiveis}"


def test_toda_oferta_pertence_a_uma_turma_do_mesmo_curso_e_periodo(escopo_seed, db):
    for oferta in db.scalars(select(Oferta)):
        assert oferta.disciplina.curso_id == oferta.turma.curso_id
        assert oferta.disciplina.periodo == oferta.turma.periodo
