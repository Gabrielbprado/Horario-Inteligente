"""Dados de exemplo (secao 9 da especificacao).

Cria o escopo "Centro Paula Souza" com a Fatec e a Etec de Taquaritinga,
um professor que leciona nas duas unidades (choque entre unidades + interjornada)
e dois cenarios de disputa de horario (por pontuacao e por desempate).

    uv run python -m scripts.seed          # recria do zero
    uv run python -m scripts.seed --keep   # so adiciona se o banco estiver vazio
"""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import (
    Base,
    Curso,
    Disciplina,
    Disponibilidade,
    Escopo,
    Espaco,
    Habilitacao,
    Modalidade,
    ModalidadeAula,
    ModoDivisao,
    OrigemHabilitacao,
    Professor,
    StatusDisponibilidade,
    TipoContrato,
    TipoEspaco,
    TipoUnidade,
    Turma,
    Unidade,
    VinculoUnidade,
)
from app.presets import aplicar_preset_unidade
from app.services import sincronizar_ofertas

# --------------------------------------------------------------------- utilitarios


def _disciplina(curso: Curso, periodo: str, nome: str, sigla: str, **kw) -> Disciplina:
    d = Disciplina(
        curso_id=curso.id,
        periodo=periodo,
        nome=nome,
        sigla=sigla,
        aulas_semanais=kw.pop("aulas_semanais", 4),
        **kw,
    )
    curso.disciplinas.append(d)
    return d


def _modelo(unidade: Unidade, preset: str):
    for m in unidade.modelos_turno:
        if m.preset_origem == preset:
            return m
    raise LookupError(f"modelo de turno {preset!r} nao encontrado em {unidade.nome}")


def _slots(modelo, dia: int, ordens: range | list[int]):
    alvo = set(ordens)
    return [s for s in modelo.slots if s.dia_semana == dia and s.ordem in alvo]


# -------------------------------------------------------------------------- seed


def seed(db: Session) -> Escopo:
    escopo = Escopo(nome="Centro Paula Souza")
    db.add(escopo)
    db.flush()

    fatec = _seed_fatec(db, escopo)
    etec = _seed_etec(db, escopo)
    _seed_professor_compartilhado(db, escopo, fatec, etec)

    db.commit()
    return escopo


# ------------------------------------------------------------------------- Fatec


def _seed_fatec(db: Session, escopo: Escopo) -> Unidade:
    fatec = Unidade(
        escopo_id=escopo.id,
        nome="Fatec Taquaritinga",
        tipo=TipoUnidade.FATEC,
        cidade="Taquaritinga",
    )
    db.add(fatec)
    db.flush()
    aplicar_preset_unidade(fatec)
    # A matriz do DSM tem 24 aulas semanais por semestre; 5 noites x 4 aulas = 20
    # slots nao comportam, entao a unidade usa sabado (spec secao 1.5).
    fatec.config_regras["usa_sabado"] = True
    db.flush()

    modelo = _modelo(fatec, "fatec_noturno_sabado")

    # espacos: 2 laboratorios de informatica + 3 salas
    for i in (1, 2):
        db.add(
            Espaco(
                unidade_id=fatec.id,
                nome=f"Laboratorio {i}",
                tipo=TipoEspaco.LABORATORIO,
                tipo_laboratorio="informatica",
                capacidade=40,
            )
        )
    for i in (1, 2, 3):
        db.add(Espaco(unidade_id=fatec.id, nome=f"Sala {i}", tipo=TipoEspaco.SALA, capacidade=45))

    dsm = Curso(
        unidade_id=fatec.id,
        nome="Desenvolvimento de Software Multiplataforma",
        sigla="DSM",
        modalidade=Modalidade.CST,
    )
    db.add(dsm)
    db.flush()

    # (nome, sigla, precisa_lab, remota)
    matriz = {
        "1o sem": [
            ("Algoritmos e Logica de Programacao", "ALP", True, False),
            ("Design Digital", "DD", True, False),
            ("Engenharia de Software I", "ESW1", False, False),
            ("Modelagem de Banco de Dados", "MBD", False, False),
            ("Sistemas Operacionais e Redes", "SOR", False, False),
            ("Metodologia Cientifica e Tecnologica", "MCT", False, True),
        ],
        "2o sem": [
            ("Desenvolvimento Web I", "DW1", True, False),
            ("Estrutura de Dados", "ED", True, False),
            ("Banco de Dados Relacional", "BDR", False, False),
            ("Engenharia de Software II", "ESW2", False, False),
            ("Matematica para Computacao", "MAT", False, False),
            ("Ingles Tecnico", "ING", False, True),
        ],
        "3o sem": [
            ("Desenvolvimento Web II", "DW2", True, False),
            ("Programacao para Dispositivos Moveis", "PDM", True, False),
            ("Banco de Dados nao Relacional", "BDN", False, False),
            ("Interface Humano-Computador", "IHC", False, False),
            ("Gestao de Projetos", "GP", False, False),
            ("Empreendedorismo", "EMP", False, True),
        ],
    }
    disciplinas: dict[str, Disciplina] = {}
    for periodo, itens in matriz.items():
        for nome, sigla, lab, remota in itens:
            disciplinas[f"{periodo}/{sigla}"] = _disciplina(
                dsm,
                periodo,
                nome,
                sigla,
                precisa_laboratorio=lab,
                tipo_laboratorio="informatica" if lab else None,
                modalidade=ModalidadeAula.REMOTA if remota else ModalidadeAula.PRESENCIAL,
            )
    db.flush()

    for periodo in matriz:
        turma = Turma(
            curso_id=dsm.id,
            periodo=periodo,
            turno="Noturno",
            modelo_turno_id=modelo.id,
            qtd_alunos=40,
        )
        dsm.turmas.append(turma)
        db.flush()
        sincronizar_ofertas(db, turma)

    _seed_professores_fatec(db, escopo, fatec, disciplinas, modelo)
    return fatec


def _seed_professores_fatec(db, escopo, fatec, disciplinas, modelo) -> None:
    # (nome, pontuacao, assiduidade, titulacao, tempo_meses, filhos, contrato, siglas)
    docentes = [
        (
            "Ana Ribeiro",
            87.5,
            20.0,
            40.0,
            180,
            1,
            TipoContrato.INDETERMINADO,
            ["1o sem/ALP", "2o sem/ED"],
        ),
        (
            "Bruno Carvalho",
            72.0,
            18.0,
            30.0,
            96,
            0,
            TipoContrato.INDETERMINADO,
            ["1o sem/DD", "3o sem/IHC"],
        ),
        (
            "Carla Menezes",
            65.0,
            19.0,
            28.0,
            72,
            2,
            TipoContrato.INDETERMINADO,
            ["1o sem/ESW1", "2o sem/ESW2", "3o sem/GP"],
        ),
        (
            "Diego Nunes",
            58.0,
            17.0,
            22.0,
            48,
            0,
            TipoContrato.DETERMINADO,
            ["1o sem/MBD", "2o sem/BDR", "3o sem/BDN"],
        ),
        (
            "Elaine Prado",
            54.0,
            16.0,
            20.0,
            36,
            1,
            TipoContrato.DETERMINADO,
            ["1o sem/SOR", "2o sem/MAT"],
        ),
        (
            "Fabio Rocha",
            49.0,
            15.0,
            18.0,
            24,
            0,
            TipoContrato.DETERMINADO,
            ["1o sem/MCT", "2o sem/ING", "3o sem/EMP"],
        ),
        # Empate em 61,0 resolvido por assiduidade (Gisele 20,0 > Henrique 12,0).
        (
            "Gisele Tavares",
            61.0,
            20.0,
            24.0,
            60,
            0,
            TipoContrato.INDETERMINADO,
            ["2o sem/DW1", "3o sem/DW2"],
        ),
        (
            "Henrique Lopes",
            61.0,
            12.0,
            26.0,
            84,
            3,
            TipoContrato.INDETERMINADO,
            ["2o sem/DW1", "3o sem/DW2", "3o sem/PDM"],
        ),
    ]
    criados: dict[str, Professor] = {}
    for nome, pont, assid, titul, tempo, filhos, contrato, siglas in docentes:
        prof = Professor(
            escopo_id=escopo.id,
            nome=nome,
            identificador=nome.lower().replace(" ", "."),
            email=f"{nome.lower().replace(' ', '.')}@fatec.sp.gov.br",
        )
        db.add(prof)
        db.flush()
        db.add(
            VinculoUnidade(
                professor_id=prof.id,
                unidade_id=fatec.id,
                tipo_contrato=contrato,
                pontuacao=pont,
                pont_assiduidade=assid,
                pont_titulacao=titul,
                tempo_exercicio_meses=tempo,
                num_filhos=filhos,
            )
        )
        for chave in siglas:
            db.add(
                Habilitacao(
                    professor_id=prof.id,
                    disciplina_id=disciplinas[chave].id,
                    origem=OrigemHabilitacao.CONCURSO,
                )
            )
        criados[nome] = prof
    db.flush()

    # Cenario de disputa por pontuacao: Ana (87,5) e Bruno (72,0) so conseguem
    # segunda no bloco 1; a prioridade vai para Ana (Portaria CETEC 1.263/2017 art. 7).
    seg_b1 = _slots(modelo, 0, [1, 2])
    for prof in (criados["Ana Ribeiro"], criados["Bruno Carvalho"]):
        for slot in seg_b1:
            db.add(
                Disponibilidade(
                    professor_id=prof.id,
                    unidade_id=fatec.id,
                    slot_id=slot.id,
                    status=StatusDisponibilidade.PREFERENCIAL,
                )
            )

    # Cenario de empate: Gisele e Henrique (ambos 61,0) preferem terca bloco 1.
    ter_b1 = _slots(modelo, 1, [1, 2])
    for prof in (criados["Gisele Tavares"], criados["Henrique Lopes"]):
        for slot in ter_b1:
            db.add(
                Disponibilidade(
                    professor_id=prof.id,
                    unidade_id=fatec.id,
                    slot_id=slot.id,
                    status=StatusDisponibilidade.PREFERENCIAL,
                )
            )

    # Fabio Rocha nao da aula as sextas.
    for slot in _slots(modelo, 4, range(1, 5)):
        db.add(
            Disponibilidade(
                professor_id=criados["Fabio Rocha"].id,
                unidade_id=fatec.id,
                slot_id=slot.id,
                status=StatusDisponibilidade.INDISPONIVEL,
            )
        )
    db.flush()


# -------------------------------------------------------------------------- Etec


def _seed_etec(db: Session, escopo: Escopo) -> Unidade:
    etec = Unidade(
        escopo_id=escopo.id,
        nome="Etec Taquaritinga",
        tipo=TipoUnidade.ETEC,
        cidade="Taquaritinga",
    )
    db.add(etec)
    db.flush()
    aplicar_preset_unidade(etec)
    db.flush()

    noturno = _modelo(etec, "etec_tecnico_noturno")
    etim = _modelo(etec, "etec_etim")

    # Lab 1 comporta a turma inteira; os dois menores existem porque e' a
    # falta de maquinas que justifica a divisao de turma (spec 1.3).
    for nome, capacidade in (
        ("Lab Informatica 1", 40),
        ("Lab Informatica 2", 20),
        ("Lab Informatica 3", 20),
    ):
        db.add(
            Espaco(
                unidade_id=etec.id,
                nome=nome,
                tipo=TipoEspaco.LABORATORIO,
                tipo_laboratorio="informatica",
                capacidade=capacidade,
            )
        )
    for i in (1, 2):
        db.add(Espaco(unidade_id=etec.id, nome=f"Sala {i}", tipo=TipoEspaco.SALA, capacidade=40))

    tds = Curso(
        unidade_id=etec.id,
        nome="Tecnico em Desenvolvimento de Sistemas",
        sigla="TDS",
        modalidade=Modalidade.TECNICO_MODULAR,
    )
    db.add(tds)
    db.flush()

    comp: dict[str, Disciplina] = {}
    comp["I/LP"] = _disciplina(
        tds,
        "Modulo I",
        "Logica de Programacao",
        "LP",
        precisa_laboratorio=True,
        tipo_laboratorio="informatica",
    )
    # Divisao PARALELA: turmas A e B no mesmo horario, dois professores, dois labs.
    comp["I/PW"] = _disciplina(
        tds,
        "Modulo I",
        "Programacao Web",
        "PW",
        precisa_laboratorio=True,
        tipo_laboratorio="informatica",
        divisao_turma=True,
        modo_divisao=ModoDivisao.PARALELA,
    )
    comp["I/BD"] = _disciplina(tds, "Modulo I", "Banco de Dados", "BD")
    comp["I/ING"] = _disciplina(tds, "Modulo I", "Ingles Instrumental", "ING", aulas_semanais=2)
    # Divisao SEQUENCIAL: mesmo professor, horarios diferentes para A e B.
    comp["I/AI"] = _disciplina(
        tds,
        "Modulo I",
        "Aplicativos Informatizados",
        "AI",
        aulas_semanais=2,
        precisa_laboratorio=True,
        tipo_laboratorio="informatica",
        divisao_turma=True,
        modo_divisao=ModoDivisao.SEQUENCIAL,
    )
    comp["II/PAP"] = _disciplina(
        tds,
        "Modulo II",
        "Programacao de Aplicativos",
        "PAP",
        precisa_laboratorio=True,
        tipo_laboratorio="informatica",
    )
    comp["II/QS"] = _disciplina(tds, "Modulo II", "Qualidade de Software", "QS", aulas_semanais=2)
    comp["II/SE"] = _disciplina(
        tds,
        "Modulo II",
        "Sistemas Embarcados",
        "SE",
        precisa_laboratorio=True,
        tipo_laboratorio="informatica",
    )
    comp["II/PI"] = _disciplina(tds, "Modulo II", "Projeto Integrador", "PI")
    db.flush()

    for periodo in ("Modulo I", "Modulo II"):
        turma = Turma(
            curso_id=tds.id,
            periodo=periodo,
            turno="Noturno",
            modelo_turno_id=noturno.id,
            qtd_alunos=36,
        )
        tds.turmas.append(turma)
        db.flush()
        sincronizar_ofertas(db, turma)

    # ETIM diurno: existe para o cenario de interjornada (aula as 07:00 no dia
    # seguinte a uma aula que termina as 22:30 na Fatec).
    etim_curso = Curso(
        unidade_id=etec.id,
        nome="Ensino Medio com Habilitacao Tecnica em Desenvolvimento de Sistemas",
        sigla="ETIM-DS",
        modalidade=Modalidade.ETIM,
    )
    db.add(etim_curso)
    db.flush()
    comp["ETIM/LPG"] = _disciplina(
        etim_curso,
        "1a serie",
        "Linguagem de Programacao",
        "LPG",
        aulas_semanais=4,
        precisa_laboratorio=True,
        tipo_laboratorio="informatica",
    )
    comp["ETIM/MAT"] = _disciplina(etim_curso, "1a serie", "Matematica", "MATE", aulas_semanais=4)
    comp["ETIM/POR"] = _disciplina(
        etim_curso, "1a serie", "Lingua Portuguesa", "POR", aulas_semanais=4
    )
    db.flush()
    turma_etim = Turma(
        curso_id=etim_curso.id,
        periodo="1a serie",
        turno="Manha",
        modelo_turno_id=etim.id,
        qtd_alunos=38,
    )
    etim_curso.turmas.append(turma_etim)
    db.flush()
    sincronizar_ofertas(db, turma_etim)

    _seed_professores_etec(db, escopo, etec, comp)
    return etec


def _seed_professores_etec(db, escopo, etec, comp) -> None:
    # A ultima coluna e' o componente que o docente ja' lecionava no periodo
    # anterior: ele tem direito de manutencao na primeira passada do ato de
    # atribuicao (Deliberacao CEETEPS 23/2015).
    docentes = [
        ("Iara Figueiredo", 91.0, 20.0, 45.0, 144, 2, ["I/LP", "II/PAP"], "II/PAP"),
        ("Joao Batista", 78.5, 19.0, 33.0, 108, 1, ["I/PW", "II/SE"], "II/SE"),
        ("Kelly Souza", 70.0, 18.0, 30.0, 84, 0, ["I/PW", "I/AI"], "I/PW"),
        ("Lucas Moreira", 66.0, 17.0, 27.0, 60, 1, ["I/BD", "II/QS", "II/PI"], "I/BD"),
        ("Marta Oliveira", 59.0, 16.0, 21.0, 36, 0, ["I/ING", "ETIM/POR"], None),
        ("Nelson Araujo", 55.0, 15.0, 19.0, 24, 2, ["ETIM/MAT"], None),
    ]
    for nome, pont, assid, titul, tempo, filhos, chaves, anterior in docentes:
        prof = Professor(
            escopo_id=escopo.id,
            nome=nome,
            identificador=nome.lower().replace(" ", "."),
            email=f"{nome.lower().replace(' ', '.')}@etec.sp.gov.br",
        )
        db.add(prof)
        db.flush()
        db.add(
            VinculoUnidade(
                professor_id=prof.id,
                unidade_id=etec.id,
                tipo_contrato=TipoContrato.INDETERMINADO,
                pontuacao=pont,
                pont_assiduidade=assid,
                pont_titulacao=titul,
                tempo_exercicio_meses=tempo,
                num_filhos=filhos,
            )
        )
        for chave in chaves:
            db.add(
                Habilitacao(
                    professor_id=prof.id,
                    disciplina_id=comp[chave].id,
                    origem=(
                        OrigemHabilitacao.ANTERIOR
                        if chave == anterior
                        else OrigemHabilitacao.CONCURSO
                    ),
                )
            )
    db.flush()


# --------------------------------------------------- professor nas duas unidades


def _seed_professor_compartilhado(db, escopo, fatec, etec) -> None:
    """Paulo Serrano da aula no DSM noturno (Fatec, termina 22:30) e na 1a serie
    do ETIM (Etec, comeca 07:00). Os dois vinculos existem para o sistema testar
    choque entre unidades e interjornada de 11 h (CLT art. 66)."""
    paulo = Professor(
        escopo_id=escopo.id,
        nome="Paulo Serrano",
        identificador="paulo.serrano",
        email="paulo.serrano@cps.sp.gov.br",
    )
    db.add(paulo)
    db.flush()

    for unidade, pont in ((fatec, 64.0), (etec, 74.0)):
        db.add(
            VinculoUnidade(
                professor_id=paulo.id,
                unidade_id=unidade.id,
                tipo_contrato=TipoContrato.INDETERMINADO,
                pontuacao=pont,
                pont_assiduidade=18.0,
                pont_titulacao=25.0,
                tempo_exercicio_meses=120,
                num_filhos=1,
                carga_max_semanal=20,
            )
        )

    alvos = {
        (fatec.id, "MAT"),  # DSM 2o sem, noturno
        (etec.id, "LPG"),  # ETIM 1a serie, manha
    }
    for disciplina in db.scalars(
        select(Disciplina).join(Curso).where(Curso.unidade_id.in_([fatec.id, etec.id]))
    ):
        if (disciplina.curso.unidade_id, disciplina.sigla) in alvos:
            db.add(
                Habilitacao(
                    professor_id=paulo.id,
                    disciplina_id=disciplina.id,
                    origem=OrigemHabilitacao.CONCURSO,
                )
            )
    db.flush()


# --------------------------------------------------------------------------- CLI


def main() -> None:
    manter = "--keep" in sys.argv
    if not manter:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if manter and db.scalar(select(Escopo).limit(1)):
            print("Banco ja populado; nada a fazer.")
            return
        escopo = seed(db)
        unidades = db.scalars(select(Unidade).where(Unidade.escopo_id == escopo.id)).all()
        print(f"Escopo {escopo.nome!r} criado com {len(unidades)} unidades:")
        for u in unidades:
            turmas = sum(len(c.turmas) for c in u.cursos)
            ofertas = sum(len(t.ofertas) for c in u.cursos for t in c.turmas)
            print(
                f"  - {u.nome}: {len(u.cursos)} cursos, {turmas} turmas, "
                f"{ofertas} ofertas, {len(u.espacos)} espacos, {len(u.vinculos)} vinculos"
            )


if __name__ == "__main__":
    main()
