"""Massa de dados: um escopo grande, para ver o sistema cheio.

O `scripts.seed` cria o exemplo mínimo da seção 9 da spec — duas unidades e os
cenários de disputa que os testes conferem. Este aqui é o oposto: enche o banco
com o porte de uma região inteira do Centro Paula Souza, para navegar nas telas
com dados de verdade e medir o solver em grades cheias.

    uv run python -m scripts.massa                  # 4 cidades (8 unidades)
    uv run python -m scripts.massa --escala grande  # 8 cidades (16 unidades)
    uv run python -m scripts.massa --limpar         # apaga tudo antes
    uv run python -m scripts.massa --gerar-grades   # e ainda roda o solver

**Toda unidade gerada fecha grade, e isso é conferido.** Massa de dados em que
o botão "Gerar grade" responde "sem solução" pareceria defeito do sistema, não
dos dados. Por isso:

- `capacidade_em_aulas` mede o turno em **aulas geminadas**, não em horários —
  um bloco de três aulas comporta um par e sobra um horário solto;
- `_criar_espacos` dimensiona sala e laboratório pela demanda de cada turno;
- o teto de carga do vínculo é o que cabe nos horários livres do docente;
- `_conferir_viabilidade` roda a pré-validação de verdade em cada unidade no
  fim, e o script sai com erro se alguma não fechar.

`tests/test_massa.py` guarda essas promessas — inclusive rodando o solver.
"""

from __future__ import annotations

import argparse
import random
import sys
import time as relogio
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import (
    Atribuicao,
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
    Oferta,
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
from app.presets import PRESETS_TURNO, aplicar_preset_unidade
from app.services import sincronizar_ofertas

SEMENTE = 20260930
"""Fixa para a massa ser a mesma a cada execução — bug encontrado nela se
reproduz na próxima."""

ESCOPO = "Centro Paula Souza — Região de Campinas"


def capacidade_em_aulas(preset: str, tamanho_bloco: int = 2) -> int:
    """Quantas aulas de verdade cabem numa semana daquele turno.

    Não é o número de horários. Uma aula geminada nunca atravessa intervalo
    (regra do CPS), então cada bloco contíguo do turno comporta
    `len(bloco) // tamanho_bloco` pares — e o resto é horário que sobra sem
    poder receber par nenhum.

    O ETIM tem dois blocos de **três** aulas por dia: 30 horários na semana,
    mas só 20 aulas geminadas. Contar os 30 punha 26 aulas numa turma que
    comporta 20, e o solver devolvia INFEASIBLE. Desde D119 a pré-validação
    também conta pares; aqui a conta existe para a massa nascer certa.
    """
    layout = PRESETS_TURNO[preset].dias
    return sum(
        (len(bloco) // tamanho_bloco) * tamanho_bloco
        for blocos_do_dia in layout.values()
        for bloco in blocos_do_dia
    )


# ------------------------------------------------------------------ catálogo


@dataclass(frozen=True, slots=True)
class Componente:
    nome: str
    sigla: str
    area: str
    aulas: int = 4
    lab: bool = False
    remota: bool = False
    divisao: ModoDivisao | None = None


@dataclass(frozen=True, slots=True)
class CursoModelo:
    nome: str
    sigla: str
    modalidade: Modalidade
    preset: str
    periodos: tuple[str, ...]
    matriz: tuple[Componente, ...]
    """A mesma matriz se repete em todos os períodos, com a mesma sigla.

    Duas disciplinas de semestres diferentes acabam com a sigla igual — é o que
    o cadastro permite, e serve para exercitar a tela, que mostra o período ao
    lado da sigla justamente para desempatar.
    """


# Áreas usadas para decidir quem pode lecionar o quê. Um docente de "exatas"
# não vira professor de enfermagem só porque faltou gente.
AREAS = ("computacao", "exatas", "gestao", "linguagens", "saude", "industrial")

_COMP_COMPUTACAO = (
    Componente("Algoritmos e Lógica de Programação", "ALP", "computacao", 4, lab=True),
    Componente("Banco de Dados", "BD", "computacao", 4, lab=True),
    Componente(
        "Desenvolvimento Web", "DW", "computacao", 4, lab=True, divisao=ModoDivisao.PARALELA
    ),
    Componente("Engenharia de Software", "ESW", "computacao", 4),
    Componente("Matemática Aplicada", "MAT", "exatas", 2),
)

_COMP_GESTAO = (
    Componente("Administração Geral", "ADM", "gestao", 4),
    Componente("Contabilidade Gerencial", "CTB", "gestao", 4),
    Componente("Estatística Aplicada", "EST", "exatas", 4),
    Componente("Marketing", "MKT", "gestao", 4),
    Componente("Comunicação Empresarial", "COM", "linguagens", 2, remota=True),
)

_COMP_INDUSTRIAL = (
    Componente("Desenho Técnico", "DES", "industrial", 4, lab=True),
    Componente("Processos de Fabricação", "PRF", "industrial", 4, lab=True),
    Componente("Física Aplicada", "FIS", "exatas", 4),
    Componente("Manutenção Industrial", "MNT", "industrial", 4),
    Componente("Segurança do Trabalho", "SEG", "industrial", 2, remota=True),
)

_COMP_ENFERMAGEM = (
    Componente("Anatomia e Fisiologia", "ANF", "saude", 4),
    Componente("Enfermagem Clínica", "ENC", "saude", 4, lab=True, divisao=ModoDivisao.SEQUENCIAL),
    Componente("Saúde Coletiva", "SCO", "saude", 4),
    Componente("Primeiros Socorros", "PSO", "saude", 4, lab=True),
    Componente("Ética Profissional", "ETI", "saude", 2, remota=True),
)

_COMP_ETIM = (
    Componente("Língua Portuguesa", "POR", "linguagens", 4),
    Componente("Matemática", "MTM", "exatas", 4),
    Componente("Programação de Computadores", "PRG", "computacao", 4, lab=True),
    Componente("Banco de Dados", "BDD", "computacao", 4, lab=True),
    Componente("História e Geografia", "HGE", "linguagens", 4),
    Componente("Inglês Técnico", "ING", "linguagens", 4),
    Componente("Educação Física", "EDF", "saude", 2),
)

CURSOS_FATEC = (
    CursoModelo(
        "Desenvolvimento de Software Multiplataforma",
        "DSM",
        Modalidade.CST,
        "fatec_noturno",
        ("1º sem", "2º sem", "3º sem", "4º sem", "5º sem", "6º sem"),
        _COMP_COMPUTACAO,
    ),
    CursoModelo(
        "Gestão Empresarial",
        "GE",
        Modalidade.CST,
        "fatec_noturno",
        ("1º sem", "2º sem", "3º sem", "4º sem"),
        _COMP_GESTAO,
    ),
    CursoModelo(
        "Manutenção Industrial",
        "MI",
        Modalidade.CST,
        "fatec_manha",
        ("1º sem", "2º sem", "3º sem", "4º sem"),
        _COMP_INDUSTRIAL,
    ),
)

CURSOS_ETEC = (
    CursoModelo(
        "Técnico em Desenvolvimento de Sistemas",
        "TDS",
        Modalidade.TECNICO_MODULAR,
        "etec_tecnico_noturno",
        ("Módulo I", "Módulo II", "Módulo III"),
        _COMP_COMPUTACAO,
    ),
    CursoModelo(
        "Técnico em Administração",
        "TAD",
        Modalidade.TECNICO_MODULAR,
        # Mesmo turno noturno dos outros cursos: uma unidade tem um horário
        # noturno só. Dois presets que se sobrepõem no relógio disputavam as
        # mesmas salas sem que a contagem de espaços percebesse.
        "etec_tecnico_noturno",
        ("Módulo I", "Módulo II", "Módulo III"),
        _COMP_GESTAO,
    ),
    CursoModelo(
        "Técnico em Enfermagem",
        "TEN",
        Modalidade.TECNICO_MODULAR,
        "etec_tecnico_noturno",
        ("Módulo I", "Módulo II"),
        _COMP_ENFERMAGEM,
    ),
    CursoModelo(
        "Desenvolvimento de Sistemas (ETIM)",
        "ETIM-DS",
        Modalidade.ETIM,
        "etec_etim",
        ("1ª série", "2ª série", "3ª série"),
        _COMP_ETIM,
    ),
)

# Cidades com unidade do CPS na região; o par (Fatec, Etec) na mesma cidade é o
# que produz docente compartilhado e choque entre unidades.
CIDADES = (
    "Campinas",
    "Americana",
    "Indaiatuba",
    "Limeira",
    "Piracicaba",
    "Sumaré",
    "Itapira",
    "Mogi Mirim",
)

# Nomes montados por combinação: 60 prenomes × 60 sobrenomes dão 3.600
# possibilidades, de sobra para as centenas de docentes de uma região. A versão
# anterior tinha uma lista fixa de 59 e caía num "Docente 184" genérico a partir
# daí — numa massa feita para olhar na tela, isso estraga toda a demonstração.
PRENOMES = (
    "Adriana",
    "Alberto",
    "Aline",
    "Amanda",
    "Anderson",
    "Beatriz",
    "Bruno",
    "Caio",
    "Camila",
    "Carlos",
    "Cecília",
    "Cláudio",
    "Cristina",
    "Daniel",
    "Débora",
    "Diego",
    "Edson",
    "Elaine",
    "Eduardo",
    "Fabiana",
    "Felipe",
    "Fernanda",
    "Gabriel",
    "Giovana",
    "Gustavo",
    "Helena",
    "Henrique",
    "Isabela",
    "Ivan",
    "Joana",
    "Jorge",
    "Juliana",
    "Kleber",
    "Larissa",
    "Leandro",
    "Letícia",
    "Lucas",
    "Luciana",
    "Marcelo",
    "Mariana",
    "Mauro",
    "Michele",
    "Nádia",
    "Natália",
    "Otávio",
    "Patrícia",
    "Paulo",
    "Rafael",
    "Raquel",
    "Renato",
    "Roberta",
    "Rodrigo",
    "Sandra",
    "Sérgio",
    "Sílvia",
    "Tatiana",
    "Thiago",
    "Vanessa",
    "Vítor",
    "Yara",
)

SOBRENOMES = (
    "Aguiar",
    "Amaral",
    "Andrade",
    "Antunes",
    "Arantes",
    "Assunção",
    "Barreto",
    "Bastos",
    "Bertolini",
    "Bezerra",
    "Bicalho",
    "Bittencourt",
    "Braga",
    "Bueno",
    "Camargo",
    "Cavalcanti",
    "Cordeiro",
    "Correia",
    "Duarte",
    "Estevam",
    "Fagundes",
    "Ferraz",
    "Figueira",
    "Fontes",
    "Godoy",
    "Loureiro",
    "Marcondes",
    "Menezes",
    "Monteiro",
    "Moraes",
    "Moretti",
    "Moura",
    "Nogueira",
    "Nunes",
    "Peixoto",
    "Pimentel",
    "Pires",
    "Pontes",
    "Portela",
    "Prado",
    "Quintela",
    "Ramalho",
    "Rangel",
    "Rezende",
    "Rocha",
    "Salgado",
    "Salles",
    "Sampaio",
    "Sarmento",
    "Siqueira",
    "Tavares",
    "Teixeira",
    "Toledo",
    "Vasconcelos",
    "Vasques",
    "Vilanova",
    "Vilela",
    "Xavier",
    "Lima",
    "Bastos",
)


def nomes_possiveis(aleatorio: random.Random) -> list[str]:
    """Todos os pares prenome+sobrenome, embaralhados. Sem repetição."""
    todos = [f"{p} {s}" for p in PRENOMES for s in dict.fromkeys(SOBRENOMES)]
    aleatorio.shuffle(todos)
    return todos


TIPOS_LAB = {
    "computacao": "informatica",
    "industrial": "mecanica",
    "saude": "enfermagem",
    "exatas": "informatica",
    "gestao": "informatica",
    "linguagens": "informatica",
}


# ----------------------------------------------------------------- geração


@dataclass(slots=True)
class Contagem:
    unidades: int = 0
    cursos: int = 0
    turmas: int = 0
    disciplinas: int = 0
    ofertas: int = 0
    espacos: int = 0
    professores: int = 0
    vinculos: int = 0
    habilitacoes: int = 0
    disponibilidades: int = 0
    avisos: list[str] = field(default_factory=list)


def _identificador(nome: str, usados: set[str]) -> str:
    plano = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    base = ".".join(plano.split()[:2])
    ident, n = base, 2
    while ident in usados:
        ident = f"{base}{n}"
        n += 1
    usados.add(ident)
    return ident


def _modelo_de(unidade: Unidade, preset: str):
    for m in unidade.modelos_turno:
        if m.preset_origem == preset:
            return m
    raise LookupError(f"a unidade {unidade.nome} não tem o turno {preset!r}")


def _horarios_que_consome(componente: Componente) -> int:
    """Horários da turma que o componente ocupa — não é o mesmo que aulas.

    Numa divisão SEQUENCIAL as subturmas A e B têm aula em momentos
    diferentes, então a turma gasta o dobro de horários. Na PARALELA as duas
    acontecem juntas e o custo é o mesmo de uma disciplina comum. Contar as
    aulas cruas punha 22 aulas num turno de 20 e a pré-validação reprovava.
    """
    return componente.aulas * (2 if componente.divisao is ModoDivisao.SEQUENCIAL else 1)


def _matriz_que_cabe(modelo_curso: CursoModelo) -> tuple[Componente, ...]:
    """Corta a matriz até caber no turno, com folga de pelo menos duas aulas.

    Grade sem folga nenhuma é resolvível mas frágil: qualquer indisponibilidade
    de docente já a torna inviável, e o usuário veria "sem solução" numa massa
    de dados feita para funcionar.
    """
    limite = capacidade_em_aulas(modelo_curso.preset) - 2
    escolhidos: list[Componente] = []
    total = 0
    for componente in modelo_curso.matriz:
        custo = _horarios_que_consome(componente)
        if total + custo > limite:
            continue
        escolhidos.append(componente)
        total += custo
    return tuple(escolhidos)


def _criar_unidade(
    db: Session,
    escopo: Escopo,
    nome: str,
    tipo: TipoUnidade,
    cidade: str,
    cursos: tuple[CursoModelo, ...],
) -> tuple[Unidade, list[Turma]]:
    unidade = Unidade(escopo_id=escopo.id, nome=nome, tipo=tipo, cidade=cidade)
    db.add(unidade)
    db.flush()
    aplicar_preset_unidade(unidade)
    db.flush()

    turmas: list[Turma] = []
    for modelo_curso in cursos:
        curso = Curso(
            unidade_id=unidade.id,
            nome=modelo_curso.nome,
            sigla=modelo_curso.sigla,
            modalidade=modelo_curso.modalidade,
        )
        db.add(curso)
        db.flush()

        modelo_turno = _modelo_de(unidade, modelo_curso.preset)
        matriz = _matriz_que_cabe(modelo_curso)

        for periodo in modelo_curso.periodos:
            for componente in matriz:
                db.add(
                    Disciplina(
                        curso_id=curso.id,
                        periodo=periodo,
                        nome=componente.nome,
                        sigla=componente.sigla,
                        aulas_semanais=componente.aulas,
                        tamanho_bloco=2 if componente.aulas >= 4 else componente.aulas,
                        modalidade=(
                            ModalidadeAula.REMOTA
                            if componente.remota
                            else ModalidadeAula.PRESENCIAL
                        ),
                        precisa_laboratorio=componente.lab,
                        tipo_laboratorio=TIPOS_LAB[componente.area] if componente.lab else None,
                        divisao_turma=componente.divisao is not None,
                        modo_divisao=componente.divisao or ModoDivisao.INDIFERENTE,
                        max_blocos_por_dia=1,
                    )
                )
            turma = Turma(
                curso_id=curso.id,
                periodo=periodo,
                turno=modelo_turno.nome,
                modelo_turno_id=modelo_turno.id,
                qtd_alunos=30 + (hash((nome, modelo_curso.sigla, periodo)) % 12),
            )
            db.add(turma)
            turmas.append(turma)
        db.flush()

    return unidade, turmas


def _criar_espacos(db: Session, unidade: Unidade, turmas: list[Turma]) -> int:
    """Espaços dimensionados pela demanda, não por palpite.

    O gargalo é por turno: as turmas da noite disputam sala entre si, não com
    as da manhã. Para cada turno conta-se quantos horários de laboratório (por
    tipo) e quantos de sala comum as turmas daquele turno consomem na semana, e
    divide-se pelos horários que o turno tem. Uma divisão PARALELA conta em
    dobro — as duas subturmas ocupam dois espaços ao mesmo tempo.

    A versão anterior usava "60% do número de turmas" e produzia Etecs
    INFEASIBLE: sobrava sala e faltava laboratório de informática.
    """
    maior_turma = max((t.qtd_alunos for t in turmas), default=40)

    por_modelo: dict[int, list[Turma]] = {}
    for turma in turmas:
        por_modelo.setdefault(turma.modelo_turno_id, []).append(turma)

    slots_do_modelo = {m.id: len(m.slots) for m in unidade.modelos_turno}
    disciplinas_do_curso: dict[int, list[Disciplina]] = {}
    for curso in unidade.cursos:
        disciplinas_do_curso[curso.id] = list(curso.disciplinas)

    precisa_lab: dict[str, int] = {}
    precisa_sala = 0
    pico = 0

    for modelo_id, turmas_do_turno in por_modelo.items():
        horarios = slots_do_modelo.get(modelo_id, 1) or 1
        pico = max(pico, len(turmas_do_turno))
        demanda_lab: dict[str, int] = {}
        demanda_sala = 0

        for turma in turmas_do_turno:
            for disciplina in disciplinas_do_curso.get(turma.curso_id, []):
                if disciplina.periodo != turma.periodo:
                    continue
                if disciplina.modalidade is ModalidadeAula.REMOTA:
                    continue  # aula remota não ocupa espaço nenhum
                # PARALELA: duas subturmas ao mesmo tempo, dois espaços.
                # SEQUENCIAL: um espaço, o dobro de horários. Nos dois casos o
                # total de espaço-horário é o mesmo.
                ocupa = disciplina.aulas_semanais * (2 if disciplina.divisao_turma else 1)
                if disciplina.precisa_laboratorio and disciplina.tipo_laboratorio:
                    tipo = disciplina.tipo_laboratorio
                    demanda_lab[tipo] = demanda_lab.get(tipo, 0) + ocupa
                else:
                    demanda_sala += ocupa

        for tipo, ocupado in demanda_lab.items():
            # +1 de folga: com ocupação de 100% o solver não tem para onde
            # mover nada e qualquer indisponibilidade derruba a grade.
            necessarios = -(-ocupado // horarios) + 1
            precisa_lab[tipo] = max(precisa_lab.get(tipo, 0), necessarios)
        precisa_sala = max(precisa_sala, -(-demanda_sala // horarios) + 2)

    criados = 0
    for tipo_lab in sorted(precisa_lab):
        for i in range(1, precisa_lab[tipo_lab] + 1):
            db.add(
                Espaco(
                    unidade_id=unidade.id,
                    nome=f"Lab. {tipo_lab.capitalize()} {i}",
                    tipo=TipoEspaco.LABORATORIO,
                    tipo_laboratorio=tipo_lab,
                    # A pré-validação recusa espaço menor que a turma.
                    capacidade=maior_turma,
                )
            )
            criados += 1

    # Nunca menos que o pico de turmas simultâneas: mesmo que a conta de
    # horários dê menos, cada turma precisa estar em algum lugar.
    for i in range(1, max(precisa_sala, pico) + 1):
        db.add(
            Espaco(
                unidade_id=unidade.id,
                nome=f"Sala {i:02d}",
                tipo=TipoEspaco.SALA,
                capacidade=maior_turma + 5,
            )
        )
        criados += 1
    db.flush()
    return criados


def _carga_por_area(unidade: Unidade) -> dict[str, int]:
    """Quantas aulas por semana cada área precisa cobrir nesta unidade."""
    area_por_sigla = {
        componente.sigla: componente.area
        for modelo in (*CURSOS_FATEC, *CURSOS_ETEC)
        for componente in modelo.matriz
    }
    carga: dict[str, int] = dict.fromkeys(AREAS, 0)
    for curso in unidade.cursos:
        for turma in curso.turmas:
            for disciplina in curso.disciplinas:
                if disciplina.periodo != turma.periodo:
                    continue
                area = area_por_sigla.get(disciplina.sigla, "exatas")
                # Divisão em subturmas dobra o número de aulas a lecionar.
                fator = 2 if disciplina.divisao_turma else 1
                carga[area] += disciplina.aulas_semanais * fator
    return carga


def _criar_professores(
    db: Session,
    escopo: Escopo,
    unidade: Unidade,
    aleatorio: random.Random,
    usados: set[str],
    nomes: list[str],
    compartilhados: list[tuple[Professor, str]],
) -> tuple[int, int, int]:
    """Um corpo docente que cobre a carga da unidade com folga por área.

    Carga alvo por docente bem abaixo do máximo legal: um quadro no limite não
    tem para onde o solver empurrar uma aula, e é o cenário que a spec chama de
    "grade apertada", não o normal de uma unidade.
    """
    carga = _carga_por_area(unidade)

    # Teto por docente, não o máximo legal da unidade. O ato de atribuição não
    # olha disponibilidade: se deixar o teto em 29, ele empilha 28 aulas em
    # quem tirou um dia de folga e só tem 16 horários — e a pré-validação
    # reprova a unidade. Doze cabe em qualquer turno, mesmo com um dia livre.
    teto = 12
    alvo = teto

    disciplinas_por_area: dict[str, list[Disciplina]] = {a: [] for a in AREAS}
    area_por_sigla = {
        componente.sigla: componente.area
        for modelo in (*CURSOS_FATEC, *CURSOS_ETEC)
        for componente in modelo.matriz
    }
    for curso in unidade.cursos:
        for disciplina in curso.disciplinas:
            disciplinas_por_area[area_por_sigla.get(disciplina.sigla, "exatas")].append(disciplina)

    criados = vinculos = habilitacoes = 0
    for area, aulas in carga.items():
        if aulas == 0:
            continue
        # +2 docentes por área: o algoritmo de atribuição precisa de disputa
        # para ter o que decidir, e a disputa é o que as telas mostram.
        quantidade = max(2, -(-aulas // alvo) + 2)  # ceil + folga para haver disputa
        for _ in range(quantidade):
            # 3.600 combinações: a lista não acaba na prática, mas se acabar é
            # melhor um nome feio que um IndexError no meio da geração.
            nome = nomes.pop() if nomes else f"Docente {len(usados) + 1}"
            professor = Professor(
                escopo_id=escopo.id,
                nome=nome,
                identificador=_identificador(nome, usados),
                email=None,
            )
            db.add(professor)
            db.flush()
            criados += 1

            db.add(
                VinculoUnidade(
                    professor_id=professor.id,
                    unidade_id=unidade.id,
                    tipo_contrato=(
                        TipoContrato.INDETERMINADO
                        if aleatorio.random() < 0.7
                        else TipoContrato.DETERMINADO
                    ),
                    pontuacao=round(aleatorio.uniform(40, 95), 1),
                    pont_assiduidade=round(aleatorio.uniform(8, 25), 1),
                    pont_titulacao=round(aleatorio.uniform(10, 35), 1),
                    tempo_exercicio_meses=aleatorio.randint(6, 300),
                    num_filhos=aleatorio.choice([0, 0, 0, 1, 1, 2, 3]),
                    carga_max_semanal=teto,
                )
            )
            vinculos += 1

            for disciplina in disciplinas_por_area[area]:
                db.add(
                    Habilitacao(
                        professor_id=professor.id,
                        disciplina_id=disciplina.id,
                        origem=(
                            OrigemHabilitacao.CONCURSO
                            if aleatorio.random() < 0.35
                            else OrigemHabilitacao.HABILITADO
                        ),
                    )
                )
                habilitacoes += 1

            # Um em cada dez também leciona na outra unidade da mesma cidade:
            # é o que faz aparecer choque entre unidades e interjornada.
            if aleatorio.random() < 0.1:
                compartilhados.append((professor, area))
    db.flush()
    return criados, vinculos, habilitacoes


def _vincular_compartilhados(
    db: Session,
    unidade: Unidade,
    aleatorio: random.Random,
    compartilhados: list[tuple[Professor, str]],
) -> tuple[int, int]:
    """Liga docentes de outra unidade da mesma cidade, sem os sobrecarregar."""
    area_por_sigla = {
        componente.sigla: componente.area
        for modelo in (*CURSOS_FATEC, *CURSOS_ETEC)
        for componente in modelo.matriz
    }
    por_area: dict[str, list[Disciplina]] = {a: [] for a in AREAS}
    for curso in unidade.cursos:
        for disciplina in curso.disciplinas:
            por_area[area_por_sigla.get(disciplina.sigla, "exatas")].append(disciplina)

    vinculos = habilitacoes = 0
    ja_vinculados = {v.professor_id for v in unidade.vinculos}
    for professor, area in compartilhados:
        if not por_area[area] or professor.id in ja_vinculados:
            continue
        ja_vinculados.add(professor.id)
        db.add(
            VinculoUnidade(
                professor_id=professor.id,
                unidade_id=unidade.id,
                tipo_contrato=TipoContrato.DETERMINADO,
                pontuacao=round(aleatorio.uniform(40, 80), 1),
                pont_assiduidade=round(aleatorio.uniform(8, 22), 1),
                pont_titulacao=round(aleatorio.uniform(10, 30), 1),
                tempo_exercicio_meses=aleatorio.randint(6, 180),
                num_filhos=aleatorio.choice([0, 0, 1]),
                # Carga menor: ele já leciona na outra unidade.
                carga_max_semanal=8,
            )
        )
        vinculos += 1
        for disciplina in aleatorio.sample(por_area[area], min(3, len(por_area[area]))):
            db.add(
                Habilitacao(
                    professor_id=professor.id,
                    disciplina_id=disciplina.id,
                    origem=OrigemHabilitacao.HABILITADO,
                )
            )
            habilitacoes += 1
    db.flush()
    return vinculos, habilitacoes


def _marcar_disponibilidade(db: Session, unidade: Unidade, aleatorio: random.Random) -> int:
    """Preferências e indisponibilidades leves.

    No máximo um dia indisponível por docente e por turno: dois já bastam para
    tornar uma unidade cheia inviável, e o objetivo aqui é massa que fecha.
    """
    criadas = 0
    # (professor, slot) já marcados. Consultar o banco não serve: as linhas
    # desta mesma passada ainda não foram para lá, e a segunda marcação do
    # mesmo par estourava a restrição de unicidade.
    marcados: set[tuple[int, int]] = set()

    def marcar(professor_id: int, slots, status: StatusDisponibilidade) -> int:
        n = 0
        for slot in slots:
            if (professor_id, slot.id) in marcados:
                continue
            marcados.add((professor_id, slot.id))
            db.add(
                Disponibilidade(
                    professor_id=professor_id,
                    unidade_id=unidade.id,
                    slot_id=slot.id,
                    status=status,
                )
            )
            n += 1
        return n

    for vinculo in unidade.vinculos:
        for modelo in unidade.modelos_turno:
            slots = list(modelo.slots)
            if not slots:
                continue
            dias = sorted({s.dia_semana for s in slots})
            if len(dias) < 3:
                continue  # turno curto: tirar um dia inteiro pesa demais

            if aleatorio.random() < 0.35:
                dia = aleatorio.choice(dias)
                criadas += marcar(
                    vinculo.professor_id,
                    [s for s in slots if s.dia_semana == dia],
                    StatusDisponibilidade.INDISPONIVEL,
                )
            if aleatorio.random() < 0.5:
                dia = aleatorio.choice(dias)
                criadas += marcar(
                    vinculo.professor_id,
                    [s for s in slots if s.dia_semana == dia],
                    StatusDisponibilidade.PREFERENCIAL,
                )
    db.flush()
    return criadas


# -------------------------------------------------------------------- conferência


def _conferir_viabilidade(db: Session, unidade: Unidade) -> list[str]:
    """Roda a pré-validação de verdade — a mesma que a tela da unidade usa.

    Gerar massa que não fecha grade seria pior que não gerar nada: o usuário
    clicaria em "Gerar grade" e receberia "sem solução" achando que é bug.
    """
    from app.models import Severidade
    from app.scheduling.loader import carregar_estado
    from app.scheduling.prevalidate import prevalidar

    estado, config = carregar_estado(db, unidade.id)
    return [
        f"{unidade.nome}: {v.mensagem}"
        for v in prevalidar(estado, config)
        if v.severidade == Severidade.BLOQUEANTE
    ]


# ---------------------------------------------------------------------- conflitos

"""`--conflitos`: a massa sabotada de propósito.

Tudo acima garante que a região fecha grade. Aqui é o contrário: depois de
povoar, planta-se um conflito de cada tipo que o sistema sabe detectar, para
navegar nas telas e ver a reação — pendência bloqueante, aviso, diagnóstico de
inviabilidade, choque entre unidades. Cada plantio devolve uma frase que o
script imprime no fim: é a lista do que procurar.
"""


def _ofertas_da(db: Session, unidade: Unidade) -> list[Oferta]:
    return db.scalars(
        select(Oferta)
        .join(Turma)
        .join(Curso)
        .where(Curso.unidade_id == unidade.id)
        .order_by(Oferta.id)
    ).all()


def _aulas_por_professor(ofertas: list[Oferta]) -> dict[int, int]:
    carga: dict[int, int] = {}
    for oferta in ofertas:
        if oferta.atribuicao:
            pid = oferta.atribuicao.professor_id
            carga[pid] = carga.get(pid, 0) + oferta.disciplina.aulas_semanais
    return carga


def _marcar_status(
    db: Session, professor_id: int, unidade: Unidade, slots, status: StatusDisponibilidade
) -> None:
    """Grava ou troca o status; (professor, slot) é único no banco."""
    existentes = {
        d.slot_id: d
        for d in db.scalars(
            select(Disponibilidade).where(Disponibilidade.professor_id == professor_id)
        )
    }
    for slot in slots:
        if slot.id in existentes:
            existentes[slot.id].status = status
        else:
            db.add(
                Disponibilidade(
                    professor_id=professor_id,
                    unidade_id=unidade.id,
                    slot_id=slot.id,
                    status=status,
                )
            )
    db.flush()


def _nome(db: Session, professor_id: int) -> str:
    return db.get(Professor, professor_id).nome


def _reatribuir(db: Session, ofertas: list[Oferta], professor_id: int) -> None:
    """Passa as ofertas para o docente, habilitando-o se for preciso."""
    habilitado = {
        h.disciplina_id
        for h in db.scalars(select(Habilitacao).where(Habilitacao.professor_id == professor_id))
    }
    for oferta in ofertas:
        if oferta.disciplina_id not in habilitado:
            db.add(
                Habilitacao(
                    professor_id=professor_id,
                    disciplina_id=oferta.disciplina_id,
                    origem=OrigemHabilitacao.HABILITADO,
                )
            )
            habilitado.add(oferta.disciplina_id)
        if oferta.atribuicao:
            oferta.atribuicao.professor_id = professor_id
        else:
            db.add(Atribuicao(oferta_id=oferta.id, professor_id=professor_id))
    db.flush()


def _plantar_choque(db: Session, fatec: Unidade, etec: Unidade) -> list[str]:
    """Docente das duas unidades da cidade com a noite cheia nas duas, e outro
    com noite na Fatec e manhã na Etec (interjornada). Só aparece de verdade
    depois que a grade da Fatec é publicada: `--gerar-grades` faz isso."""
    em_ambas = sorted(
        {v.professor_id for v in fatec.vinculos} & {v.professor_id for v in etec.vinculos}
    )
    if not em_ambas:
        return []
    ofertas = _ofertas_da(db, etec)
    sem_subturma = [o for o in ofertas if o.subturma is None]
    noturnas = [o for o in sem_subturma if o.turma.modelo_turno.preset_origem != "etec_etim"]
    matutinas = [o for o in sem_subturma if o.turma.modelo_turno.preset_origem == "etec_etim"]
    relatorio = []

    choque = em_ambas[0]
    alvo = noturnas[:3]
    if alvo:
        _reatribuir(db, alvo, choque)
        for v in etec.vinculos:
            if v.professor_id == choque:
                v.carga_max_semanal = 16
        relatorio.append(
            f"Choque entre unidades: {_nome(db, choque)} leciona à noite na {fatec.nome} e "
            f"recebeu {sum(o.disciplina.aulas_semanais for o in alvo)} aulas noturnas na "
            f"{etec.nome}. Publique a grade da Fatec e gere a da Etec."
        )

    if len(em_ambas) > 1 and matutinas:
        madrugador = em_ambas[1]
        alvo = matutinas[:2]
        _reatribuir(db, alvo, madrugador)
        relatorio.append(
            f"Interjornada: {_nome(db, madrugador)} sai às 22h30 da {fatec.nome} e entra às "
            f"07h00 na {etec.nome} (ETIM). Com a grade da Fatec publicada, a da Etec avisa."
        )
    return relatorio


def _plantar_indisponibilidade(
    db: Session, unidade: Unidade, aleatorio: random.Random
) -> list[str]:
    """Três dias bloqueados em quem tem 12 aulas: não cabe nos dois que sobram."""
    ofertas = _ofertas_da(db, unidade)
    carga = _aulas_por_professor(ofertas)
    cheios = [pid for pid, aulas in sorted(carga.items()) if aulas >= 8]
    relatorio = []
    for pid in cheios[:2]:
        turnos = {
            o.turma.modelo_turno
            for o in ofertas
            if o.atribuicao and o.atribuicao.professor_id == pid
        }
        for modelo in turnos:
            dias = sorted({s.dia_semana for s in modelo.slots})
            bloqueados = aleatorio.sample(dias, min(3, len(dias)))
            _marcar_status(
                db,
                pid,
                unidade,
                [s for s in modelo.slots if s.dia_semana in bloqueados],
                StatusDisponibilidade.INDISPONIVEL,
            )
        relatorio.append(
            f"Indisponibilidade: {_nome(db, pid)} ({unidade.nome}) tem {carga[pid]} aulas e "
            "bloqueou 3 dias da semana. A pré-validação deve apontar que não cabe."
        )
    return relatorio


def _plantar_disputa(db: Session, unidade: Unidade, aleatorio: random.Random) -> list[str]:
    """Cinco docentes querendo o mesmo dia, dois deles empatados em tudo."""
    modelo = max(unidade.modelos_turno, key=lambda m: len(m.slots))
    dias = sorted({s.dia_semana for s in modelo.slots})
    if not dias:
        return []
    dia = aleatorio.choice(dias)
    vinculos = sorted(unidade.vinculos, key=lambda v: v.id)[:5]
    for v in vinculos:
        _marcar_status(
            db,
            v.professor_id,
            unidade,
            [s for s in modelo.slots if s.dia_semana == dia],
            StatusDisponibilidade.PREFERENCIAL,
        )
    if len(vinculos) >= 3:
        a, b, c = vinculos[:3]
        b.pontuacao = a.pontuacao
        b.pont_assiduidade = a.pont_assiduidade
        b.pont_titulacao = a.pont_titulacao
        b.tempo_exercicio_meses = a.tempo_exercicio_meses
        b.num_filhos = a.num_filhos + 1  # só o último critério desempata
        c.pontuacao = a.pontuacao
        c.pont_assiduidade = a.pont_assiduidade - 5  # empate decidido na assiduidade
    db.flush()
    nomes = ", ".join(_nome(db, v.professor_id) for v in vinculos)
    return [
        f"Disputa: {nomes} ({unidade.nome}) preferem todos o mesmo dia ({modelo.nome}, dia "
        f"{dia + 1}); os três primeiros têm a mesma pontuação e empatam até o número de filhos."
    ]


def _plantar_oferta_sem_habilitado(db: Session, unidade: Unidade) -> list[str]:
    """Uma disciplina sem ninguém habilitado: pendência que o 'Sugerir' não resolve."""
    ofertas = _ofertas_da(db, unidade)
    disciplinas = sorted({o.disciplina for o in ofertas}, key=lambda d: d.id)
    if not disciplinas:
        return []
    alvo = disciplinas[len(disciplinas) // 2]
    for h in db.scalars(select(Habilitacao).where(Habilitacao.disciplina_id == alvo.id)):
        db.delete(h)
    for o in ofertas:
        if o.disciplina_id == alvo.id and o.atribuicao:
            db.delete(o.atribuicao)
    db.flush()
    return [
        f"Sem habilitado: {alvo.sigla} — {alvo.nome} ({unidade.nome}) ficou sem nenhum docente "
        "habilitado e sem atribuição."
    ]


def _plantar_sobrecarga(db: Session, unidade: Unidade) -> list[str]:
    """Carga máxima do vínculo abaixo do que já foi atribuído."""
    carga = _aulas_por_professor(_ofertas_da(db, unidade))
    if not carga:
        return []
    pid = max(sorted(carga), key=carga.get)
    for v in unidade.vinculos:
        if v.professor_id == pid:
            v.carga_max_semanal = 4
    db.flush()
    return [
        f"Sobrecarga: {_nome(db, pid)} ({unidade.nome}) tem {carga[pid]} aulas atribuídas e "
        "carga máxima de 4."
    ]


def _plantar_lab_faltando(db: Session, unidade: Unidade) -> list[str]:
    """Some com todos os laboratórios de um tipo que a matriz exige."""
    exigidos = sorted(
        {
            d.tipo_laboratorio
            for c in unidade.cursos
            for d in c.disciplinas
            if d.precisa_laboratorio and d.tipo_laboratorio
        }
    )
    if not exigidos:
        return []
    tipo = exigidos[-1]
    apagados = 0
    for e in list(unidade.espacos):
        if e.tipo == TipoEspaco.LABORATORIO and e.tipo_laboratorio == tipo:
            db.delete(e)
            apagados += 1
    db.flush()
    return [
        f"Laboratório faltando: {unidade.nome} perdeu {apagados} laboratório(s) de {tipo}, "
        "que a matriz exige."
    ]


def sabotar(db: Session, *, cidades: int) -> list[str]:
    """Planta os conflitos na região já povoada e devolve o relatório.

    Cada cidade recebe o choque entre unidades (se houver docente em comum) e a
    disputa de horário nas duas unidades. As sabotagens bloqueantes vão em
    rodízio: metade das cidades ainda fecha grade, metade não.
    """
    aleatorio = random.Random(SEMENTE + 1)
    escopo = db.scalar(select(Escopo).where(Escopo.nome == ESCOPO))
    if escopo is None:
        return []
    # Brandas: a pré-validação acusa, mas o solver ainda fecha (a oferta sem
    # docente fica de fora; a carga é regra de atribuição, não da grade).
    # Duras: a grade não fecha, e o diagnóstico tem de explicar.
    brandas = [_plantar_oferta_sem_habilitado, _plantar_sobrecarga]
    duras = [_plantar_indisponibilidade, _plantar_lab_faltando]
    relatorio: list[str] = []
    for i, cidade in enumerate(CIDADES[:cidades]):
        fatec = db.scalar(select(Unidade).where(Unidade.nome == f"Fatec {cidade}"))
        etec = db.scalar(select(Unidade).where(Unidade.nome == f"Etec {cidade}"))
        if fatec is None or etec is None:
            continue
        # Cidade par: as duas unidades fecham, e o choque entre elas aparece.
        # Cidade ímpar: nenhuma fecha, e cada uma por um motivo diferente.
        kinds = brandas if i % 2 == 0 else duras
        relatorio += _plantar_choque(db, fatec, etec)
        for j, unidade in enumerate((fatec, etec)):
            relatorio += _plantar_disputa(db, unidade, aleatorio)
            plantar = kinds[(i // 2 + j) % 2]
            if plantar is _plantar_indisponibilidade:
                relatorio += plantar(db, unidade, aleatorio)
            else:
                relatorio += plantar(db, unidade)
    db.flush()
    return relatorio


# ------------------------------------------------------------------ orquestração


def povoar(db: Session, *, cidades: int, atribuir: bool = True) -> Contagem:
    aleatorio = random.Random(SEMENTE)
    contagem = Contagem()

    escopo = db.scalar(select(Escopo).where(Escopo.nome == ESCOPO))
    if escopo is None:
        escopo = Escopo(nome=ESCOPO)
        db.add(escopo)
        db.flush()

    nomes = nomes_possiveis(aleatorio)
    usados = {
        ident
        for (ident,) in db.execute(
            select(Professor.identificador).where(Professor.escopo_id == escopo.id)
        )
    }

    for cidade in CIDADES[:cidades]:
        compartilhados: list[tuple[Professor, str]] = []

        for tipo, prefixo, cursos in (
            (TipoUnidade.FATEC, "Fatec", CURSOS_FATEC),
            (TipoUnidade.ETEC, "Etec", CURSOS_ETEC),
        ):
            nome = f"{prefixo} {cidade}"
            ja_existe = db.scalar(
                select(Unidade).where(Unidade.nome == nome, Unidade.escopo_id == escopo.id)
            )
            if ja_existe:
                continue

            unidade, turmas = _criar_unidade(db, escopo, nome, tipo, cidade, cursos)
            contagem.unidades += 1
            contagem.cursos += len(unidade.cursos)
            contagem.turmas += len(turmas)
            contagem.espacos += _criar_espacos(db, unidade, turmas)

            # A Etec da cidade recebe os docentes que a **Fatec** marcou como
            # compartilhados, antes de criar os seus. Sem esse `antes`, os
            # docentes recém-criados da própria Etec entravam na lista e eram
            # vinculados de novo à mesma unidade — vínculo e habilitação em
            # duplicata, que o banco recusa.
            if tipo is TipoUnidade.ETEC and compartilhados:
                v, h = _vincular_compartilhados(db, unidade, aleatorio, compartilhados)
                contagem.vinculos += v
                contagem.habilitacoes += h

            criados, vinculos, habilitacoes = _criar_professores(
                db,
                escopo,
                unidade,
                aleatorio,
                usados,
                nomes,
                # Só a Fatec alimenta a lista: quem partilha vai para a Etec da
                # mesma cidade, que já foi atendida acima.
                compartilhados if tipo is TipoUnidade.FATEC else [],
            )
            contagem.professores += criados
            contagem.vinculos += vinculos
            contagem.habilitacoes += habilitacoes

            for turma in turmas:
                contagem.ofertas += len(sincronizar_ofertas(db, turma))
            # `sincronizar_ofertas` não faz flush; sem este, `_atribuir` carrega
            # o estado do banco e não encontra oferta nenhuma para distribuir.
            db.flush()
            contagem.disciplinas += sum(len(c.disciplinas) for c in unidade.cursos)
            contagem.disponibilidades += _marcar_disponibilidade(db, unidade, aleatorio)

            if atribuir:
                sem_professor = _atribuir(db, unidade)
                if sem_professor:
                    contagem.avisos.append(
                        f"{unidade.nome}: {sem_professor} oferta(s) ficaram sem docente habilitado."
                    )

            contagem.avisos += _conferir_viabilidade(db, unidade)

    db.commit()
    return contagem


def _atribuir(db: Session, unidade: Unidade) -> int:
    """Deixa as aulas já atribuídas: a unidade abre pronta para gerar grade.

    Devolve quantas ofertas ficaram sem docente. O `commit` no fim não é zelo:
    sem ele a `Oferta` que já está no mapa de identidade da sessão continua com
    `atribuicao=None`, e a conferência seguinte reprovaria a unidade inteira
    por "não tem professor atribuído" — foi o que aconteceu ao escrever isto.
    """
    from app.models import Atribuicao
    from app.scheduling.assignment import sugerir_atribuicao
    from app.scheduling.loader import carregar_estado

    estado, config = carregar_estado(db, unidade.id)
    resultado = sugerir_atribuicao(estado, config)
    for oferta_id, professor_id in resultado.novas.items():
        db.add(Atribuicao(oferta_id=oferta_id, professor_id=professor_id))
    db.commit()
    return len(resultado.sem_professor)


def _gerar_grades(
    db: Session, escopo_nome: str, tempo_limite: float, *, publicar_fatec: bool = False
) -> None:
    from app.models import Alocacao, Grade
    from app.scheduling.avisos import avisos_da_grade, gravar_avisos
    from app.scheduling.loader import carregar_estado
    from app.scheduling.solver import Parametros, resolver

    escopo = db.scalar(select(Escopo).where(Escopo.nome == escopo_nome))
    unidades = db.scalars(select(Unidade).where(Unidade.escopo_id == escopo.id)).all()
    # Fatec antes da Etec da mesma cidade: a grade da Fatec publicada é a
    # ocupação externa que a Etec precisa enxergar (choque e interjornada).
    unidades.sort(key=lambda u: (u.cidade or "", u.tipo is not TipoUnidade.FATEC, u.nome))

    print(f"\nGerando grade para {len(unidades)} unidades (até {tempo_limite:.0f} s cada):")
    for unidade in unidades:
        comeco = relogio.monotonic()
        estado, config = carregar_estado(db, unidade.id)
        solucao = resolver(estado, config, Parametros(tempo_limite_s=tempo_limite))
        if not solucao.viavel:
            print(f"  - {unidade.nome}: SEM SOLUÇÃO ({solucao.status})")
            continue

        # O mesmo score que o job real grava (`jobs._gravar`): sem `tempo_s` e
        # `objetivo` o cartão da grade mostra "gerada em — s".
        grade = Grade(
            unidade_id=unidade.id,
            nome="Grade 1",
            score={
                "objetivo": solucao.objetivo,
                "limite_inferior": solucao.limite_inferior,
                "tempo_s": round(solucao.tempo_s, 2),
                **solucao.metricas,
            },
        )
        db.add(grade)
        db.flush()
        for alocada in solucao.alocacoes:
            db.add(
                Alocacao(
                    grade_id=grade.id,
                    oferta_id=alocada.oferta_id,
                    professor_id=alocada.professor_id,
                    slot_id=alocada.slot_id,
                    espaco_id=alocada.espaco_id,
                    bloco_idx=alocada.bloco_idx,
                )
            )
        db.flush()
        estado_final, _ = carregar_estado(db, unidade.id, grade_id=grade.id)
        violacoes = avisos_da_grade(estado_final, config)
        gravar_avisos(db, grade.id, violacoes)
        from app.models import Severidade, StatusGrade

        grade.status = (
            StatusGrade.AGUARDANDO_CIENCIA
            if any(v.severidade == Severidade.ALERTA for v in violacoes)
            else StatusGrade.RASCUNHO
        )
        if publicar_fatec and unidade.tipo is TipoUnidade.FATEC:
            # Publicada, a grade da Fatec vira ocupação externa para a Etec da
            # mesma cidade: é o que faz o choque plantado aparecer.
            grade.status = StatusGrade.PUBLICADA
        db.commit()
        print(
            f"  - {unidade.nome}: {len(solucao.alocacoes)} aulas, "
            f"{solucao.metricas.get('janela_turma', 0)} janela(s) de turma, "
            f"{relogio.monotonic() - comeco:.1f} s"
        )


# --------------------------------------------------------------------------- CLI


ESCALAS = {"pequena": 2, "media": 4, "grande": 8}


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "--escala", choices=sorted(ESCALAS), default="media", help="quantas cidades povoar"
    )
    analisador.add_argument("--limpar", action="store_true", help="apaga o banco antes")
    analisador.add_argument(
        "--gerar-grades", action="store_true", help="roda o solver em cada unidade no fim"
    )
    analisador.add_argument(
        "--tempo-limite", type=float, default=30.0, help="segundos por grade (com --gerar-grades)"
    )
    analisador.add_argument(
        "--conflitos",
        action="store_true",
        help="planta conflitos de propósito depois de povoar (e publica as grades das Fatecs)",
    )
    argumentos = analisador.parse_args()

    if argumentos.limpar:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    cidades = ESCALAS[argumentos.escala]
    comeco = relogio.monotonic()
    with SessionLocal() as db:
        contagem = povoar(db, cidades=cidades)
        conflitos = []
        if argumentos.conflitos:
            conflitos = sabotar(db, cidades=cidades)
            db.commit()
            contagem.avisos = []
            escopo = db.scalar(select(Escopo).where(Escopo.nome == ESCOPO))
            for unidade in db.scalars(select(Unidade).where(Unidade.escopo_id == escopo.id)):
                contagem.avisos += _conferir_viabilidade(db, unidade)

    print(f"Escopo {ESCOPO!r} povoado em {relogio.monotonic() - comeco:.1f} s:")
    for rotulo, valor in (
        ("unidades", contagem.unidades),
        ("cursos", contagem.cursos),
        ("turmas", contagem.turmas),
        ("disciplinas", contagem.disciplinas),
        ("ofertas", contagem.ofertas),
        ("espaços", contagem.espacos),
        ("professores", contagem.professores),
        ("vínculos", contagem.vinculos),
        ("habilitações", contagem.habilitacoes),
        ("disponibilidades", contagem.disponibilidades),
    ):
        print(f"  {valor:>7}  {rotulo}")

    if conflitos:
        print("\nConflitos plantados de propósito (o que procurar nas telas):")
        for linha in conflitos:
            print(f"  * {linha}")

    if contagem.avisos:
        titulo = "de propósito" if conflitos else "ainda"
        print(f"\nUnidades que {titulo} não fecham grade:")
        for aviso in contagem.avisos:
            print(f"  ! {aviso}")
        if not conflitos:
            sys.exit(1)

    if argumentos.gerar_grades:
        with SessionLocal() as db:
            _gerar_grades(db, ESCOPO, argumentos.tempo_limite, publicar_fatec=argumentos.conflitos)


if __name__ == "__main__":
    main()
