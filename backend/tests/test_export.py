"""Etapa 9: cores, quadros, PDF e Excel."""

import re
from datetime import time
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app import schemas as s
from app.export import pdf, xlsx
from app.export.cores import cores_disciplina, hash_fnv, matiz, oklch_hex
from app.export.grade import montar_quadros
from app.models import Unidade

# --------------------------------------------------------------------- cores


def test_matiz_e_o_mesmo_que_a_tela_calcula():
    """Valores conferidos rodando `matizDisciplina` do frontend em Node.

    Se esta lista quebrar, a exportacao passou a pintar as aulas com cores
    diferentes das da tela — que e' exatamente o que a cor estavel evita.
    """
    assert matiz("DW1") == 175.5
    assert matiz("ALP") == 18.0
    assert matiz("BD") == 85.5
    assert matiz("LP") == 40.5
    assert matiz("PAP") == 63.0


def test_hash_respeita_o_estouro_de_32_bits_do_javascript():
    # Math.imul: o produto e' truncado em 32 bits com sinal, nao cresce sem fim.
    assert hash_fnv("DW1") < 2**31
    assert hash_fnv("") == abs(2166136261 - 2**32)


def test_duas_disciplinas_coincidem_ou_ficam_bem_separadas():
    siglas = ["ALP", "BD", "DW1", "ESW1", "SOR", "LP", "PAP", "PI", "QS", "SE", "AI", "ING"]
    for a in siglas:
        for b in siglas:
            distancia = abs(matiz(a) - matiz(b)) % 360
            assert distancia == 0 or 22.5 <= min(distancia, 360 - distancia)


@pytest.mark.parametrize(
    ("luminosidade", "esperado"),
    [(0.0, "#000000"), (1.0, "#FFFFFF")],
)
def test_oklch_sem_croma_vira_cinza(luminosidade, esperado):
    assert oklch_hex(luminosidade, 0.0, 0.0) == esperado


def test_cada_disciplina_tem_fundo_claro_e_texto_escuro():
    fundo, _, texto = cores_disciplina("ALP")
    assert int(fundo[1:3], 16) > int(texto[1:3], 16)


# -------------------------------------------------------------------- quadros


def _visao(tipo="turma") -> s.VisaoGrade:
    """Uma turma de manha com aula as 07h00 e as 09h50 — e o buraco no meio."""
    faixas = [
        (1, time(7, 0), time(7, 50)),
        (2, time(8, 40), time(9, 30)),
        (3, time(9, 50), time(10, 40)),
    ]
    slots = [
        s.SlotRef(
            id=dia * 10 + ordem,
            modelo_turno_id=1,
            dia=dia,
            ordem=ordem,
            inicio=inicio,
            fim=fim,
            bloco_id=1,
        )
        for dia in range(2)
        for ordem, inicio, fim in faixas
    ]
    celulas = [
        s.CelulaGrade(
            alocacao_id=1,
            oferta_id=1,
            disciplina_id=1,
            disciplina_sigla="ALP",
            disciplina_nome="Algoritmos",
            turma_id=10,
            turma_rotulo="DSM 1o sem",
            subturma=None,
            professor_id=5,
            professor_nome="Ana Ribeiro",
            espaco_id=7,
            espaco_nome="Lab 1",
            slot_id=1,
            modelo_turno_id=1,
            dia=0,
            ordem=1,
            inicio=time(7, 0),
            fim=time(7, 50),
            bloco_id=1,
            bloco_idx=0,
            remota=False,
            precisa_laboratorio=True,
            fixada=True,
        )
    ]
    return s.VisaoGrade(
        grade_id=1,
        tipo=tipo,
        colunas=[
            s.ColunaVisao(id=10, titulo="DSM 1o sem", subtitulo="40 alunos", modelo_turno_id=1)
        ],
        horarios=[
            s.LinhaHorario(dia=dia, inicio=inicio, fim=fim, ordens=[ordem])
            for dia in range(2)
            for ordem, inicio, fim in faixas
        ],
        slots=slots,
        celulas=celulas,
    )


def test_o_quadro_mostra_o_horario_vago_do_turno():
    """Tirar as faixas so' das aulas esconderia a janela, que e' o que o
    coordenador precisa enxergar no papel."""
    quadro = montar_quadros(_visao())[0]

    assert quadro.faixas == [
        (time(7, 0), time(7, 50)),
        (time(8, 40), time(9, 30)),
        (time(9, 50), time(10, 40)),
    ]
    assert quadro.aula(0, 0) is not None
    assert quadro.aula(1, 0) is None


def test_o_quadro_por_turma_mostra_professor_e_sala():
    aula = montar_quadros(_visao())[0].aula(0, 0)
    assert aula.linhas == ("Ana Ribeiro", "Lab 1")
    assert aula.fixada


def test_o_quadro_por_professor_mostra_a_turma_no_lugar_do_professor():
    visao = _visao("professor")
    visao.colunas = [s.ColunaVisao(id=5, titulo="Ana Ribeiro")]
    aula = montar_quadros(visao)[0].aula(0, 0)
    assert aula.linhas == ("DSM 1o sem", "Lab 1")


def test_coluna_sem_aula_fica_vazia_e_nao_vai_para_o_papel():
    visao = _visao()
    visao.celulas = []
    assert montar_quadros(visao)[0].vazio


# ---------------------------------------------------------------- PDF e Excel


def _unidade(db, nome="Etec Taquaritinga") -> Unidade:
    return db.scalar(select(Unidade).where(Unidade.nome == nome))


def _grade(cliente, db, nome="Etec Taquaritinga") -> int:
    unidade = _unidade(db, nome)
    cliente.post(f"/unidades/{unidade.id}/atribuicao/sugerir")
    return cliente.post(f"/unidades/{unidade.id}/grades/gerar", json={"tempo_limite_s": 15}).json()[
        "grade_id"
    ]


def test_pdf_sai_em_paisagem_com_uma_pagina_por_turma():
    corpo = pdf.gerar(_visao(), "Etec Teste · Grade 1")
    assert corpo.startswith(b"%PDF")

    caixa = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", corpo)
    largura, altura = (float(x) for x in caixa.groups())
    assert largura > altura  # A4 deitado: a grade e' larga
    assert round(largura) == 842


def test_excel_tem_uma_aba_por_turma_com_a_cor_da_disciplina():
    livro = load_workbook(BytesIO(xlsx.gerar(_visao(), "Etec Teste")))
    assert livro.sheetnames == ["DSM 1o sem"]

    planilha = livro["DSM 1o sem"]
    assert planilha["A4"].value == "Horário"
    assert planilha["B4"].value == "Segunda"
    assert "ALP" in planilha["B5"].value
    fundo, _, _ = cores_disciplina("ALP")
    assert planilha["B5"].fill.fgColor.rgb == "FF" + fundo[1:]


def test_grade_sem_aula_ainda_gera_arquivo_que_abre():
    visao = _visao()
    visao.celulas = []
    livro = load_workbook(BytesIO(xlsx.gerar(visao, "Etec Teste")))
    assert livro.sheetnames == ["Sem aulas"]
    assert pdf.gerar(visao, "Etec Teste").startswith(b"%PDF")


def test_rota_de_exportacao_devolve_pdf_com_nome_de_arquivo(cliente, escopo_seed, db):
    grade_id = _grade(cliente, db)
    r = cliente.get(f"/grades/{grade_id}/exportar?formato=pdf&tipo=turma")

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="etec-taquaritinga-grade-1-turma.pdf"' in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_rota_de_exportacao_devolve_xlsx_por_professor(cliente, escopo_seed, db):
    grade_id = _grade(cliente, db)
    r = cliente.get(f"/grades/{grade_id}/exportar?formato=xlsx&tipo=professor")

    assert r.status_code == 200
    livro = load_workbook(BytesIO(r.content))
    assert "Paulo Serrano" in livro.sheetnames


def test_exportar_uma_coluna_so_traz_aquela_turma(cliente, escopo_seed, db):
    grade_id = _grade(cliente, db)
    visao = cliente.get(f"/grades/{grade_id}/visao").json()
    turma = visao["colunas"][1]

    r = cliente.get(f"/grades/{grade_id}/exportar?formato=xlsx&coluna_id={turma['id']}")
    livro = load_workbook(BytesIO(r.content))
    assert livro.sheetnames == [turma["titulo"][:31]]


def test_coluna_inexistente_responde_404_explicando(cliente, escopo_seed, db):
    grade_id = _grade(cliente, db)
    r = cliente.get(f"/grades/{grade_id}/exportar?coluna_id=99999")
    assert r.status_code == 404
    assert "coluna" in r.json()["detail"]
