"""O que cada planilha importa, coluna por coluna.

Um `Modelo` é ao mesmo tempo a documentação, o arquivo de exemplo que o usuário
baixa e o código que aplica a linha — três coisas que, separadas, saem do ar uma
da outra na primeira mudança de cadastro.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.importacao.campos import ValorInvalido, booleano, decimal, inteiro, opcao, texto
from app.importacao.relatorio import Relatorio


@dataclass(frozen=True, slots=True)
class Coluna:
    nome: str
    ajuda: str
    exemplo: str = ""
    obrigatoria: bool = False


@dataclass(frozen=True, slots=True)
class Modelo:
    tipo: str
    titulo: str
    descricao: str
    colunas: tuple[Coluna, ...]
    aplicar_linha: Callable[[Session, m.Unidade, dict[str, Any]], tuple[str, str]]
    """Devolve (ação, descrição). Levanta `ValorInvalido` com o motivo."""
    chaves: tuple[str, ...] = ()
    """Colunas que identificam a linha, para a mensagem de erro."""

    def cabecalho(self) -> list[str]:
        return [c.nome for c in self.colunas]

    def exemplo_linha(self) -> list[str]:
        return [c.exemplo for c in self.colunas]


# ------------------------------------------------------------------- auxiliares


def _curso(db: Session, unidade: m.Unidade, sigla: str) -> m.Curso:
    curso = db.scalar(
        select(m.Curso).where(m.Curso.unidade_id == unidade.id, m.Curso.sigla == sigla)
    )
    if curso is None:
        raise ValorInvalido(f"A unidade não tem o curso de sigla '{sigla}'. Cadastre-o antes.")
    return curso


def _modelo_turno(db: Session, unidade: m.Unidade, nome: str) -> m.ModeloTurno:
    modelo = db.scalar(
        select(m.ModeloTurno).where(
            m.ModeloTurno.unidade_id == unidade.id, m.ModeloTurno.nome == nome
        )
    )
    if modelo is None:
        raise ValorInvalido(f"A unidade não tem o modelo de turno '{nome}'.")
    return modelo


def _professor(db: Session, unidade: m.Unidade, identificador: str) -> m.Professor:
    professor = db.scalar(
        select(m.Professor).where(
            m.Professor.escopo_id == unidade.escopo_id,
            m.Professor.identificador == identificador,
        )
    )
    if professor is None:
        raise ValorInvalido(f"Não há professor com identificador '{identificador}' no escopo.")
    return professor


def _aplicar(objeto, valores: dict[str, Any]) -> bool:
    """Escreve só o que mudou; devolve se alguma coisa mudou de fato."""
    mudou = False
    for campo, valor in valores.items():
        if valor is not None and getattr(objeto, campo) != valor:
            setattr(objeto, campo, valor)
            mudou = True
    return mudou


# ---------------------------------------------------------------- professores


def _linha_professor(db: Session, unidade: m.Unidade, linha: dict) -> tuple[str, str]:
    """Cria (ou atualiza) o professor no escopo e o vínculo com esta unidade.

    O professor vive no escopo, não na unidade: o mesmo docente pode lecionar na
    Fatec e na Etec da cidade. Importar na unidade B um identificador que já
    existe na unidade A **não duplica** o docente, acrescenta o vínculo — é
    justamente esse o caso que gera choque entre unidades.
    """
    identificador = texto(linha.get("identificador", ""), "identificador", maximo=40)
    nome = texto(linha.get("nome", ""), "nome", maximo=160)

    professor = db.scalar(
        select(m.Professor).where(
            m.Professor.escopo_id == unidade.escopo_id,
            m.Professor.identificador == identificador,
        )
    )
    criou = professor is None
    if professor is None:
        professor = m.Professor(escopo_id=unidade.escopo_id, identificador=identificador, nome=nome)
        db.add(professor)
        db.flush()
    else:
        _aplicar(professor, {"nome": nome})

    email = texto(linha.get("email", ""), "email", obrigatorio=False)
    _aplicar(professor, {"email": email or None})

    vinculo = db.scalar(
        select(m.VinculoUnidade).where(
            m.VinculoUnidade.professor_id == professor.id,
            m.VinculoUnidade.unidade_id == unidade.id,
        )
    )
    criou_vinculo = vinculo is None
    if vinculo is None:
        vinculo = m.VinculoUnidade(professor_id=professor.id, unidade_id=unidade.id)
        db.add(vinculo)

    _aplicar(
        vinculo,
        {
            "tipo_contrato": opcao(
                linha.get("tipo_contrato", ""),
                "tipo_contrato",
                m.TipoContrato,
                padrao=m.TipoContrato.INDETERMINADO,
            ),
            "pontuacao": decimal(linha.get("pontuacao", ""), "pontuacao"),
            "pont_assiduidade": decimal(linha.get("pont_assiduidade", ""), "pont_assiduidade"),
            "pont_titulacao": decimal(linha.get("pont_titulacao", ""), "pont_titulacao"),
            "tempo_exercicio_meses": inteiro(
                linha.get("tempo_exercicio_meses", ""), "tempo_exercicio_meses", padrao=0
            ),
            "num_filhos": inteiro(linha.get("num_filhos", ""), "num_filhos", padrao=0),
            "carga_max_semanal": inteiro(
                linha.get("carga_max_semanal", ""), "carga_max_semanal", minimo=1
            ),
        },
    )
    db.flush()

    acao = "criar" if criou or criou_vinculo else "atualizar"
    return acao, f"{nome} ({identificador})"


# ---------------------------------------------------------------- disciplinas


def _linha_disciplina(db: Session, unidade: m.Unidade, linha: dict) -> tuple[str, str]:
    curso = _curso(db, unidade, texto(linha.get("curso_sigla", ""), "curso_sigla", maximo=20))
    periodo = texto(linha.get("periodo", ""), "periodo", maximo=40)
    sigla = texto(linha.get("sigla", ""), "sigla", maximo=20)

    disciplina = db.scalar(
        select(m.Disciplina).where(
            m.Disciplina.curso_id == curso.id,
            m.Disciplina.periodo == periodo,
            m.Disciplina.sigla == sigla,
        )
    )
    criou = disciplina is None
    if disciplina is None:
        disciplina = m.Disciplina(curso_id=curso.id, periodo=periodo, sigla=sigla, nome=sigla)
        db.add(disciplina)

    _aplicar(
        disciplina,
        {
            "nome": texto(linha.get("nome", ""), "nome", maximo=160),
            "aulas_semanais": inteiro(
                linha.get("aulas_semanais", ""), "aulas_semanais", minimo=1, padrao=2
            ),
            "tamanho_bloco": inteiro(
                linha.get("tamanho_bloco", ""), "tamanho_bloco", minimo=1, padrao=2
            ),
            "modalidade": opcao(
                linha.get("modalidade", ""),
                "modalidade",
                m.ModalidadeAula,
                padrao=m.ModalidadeAula.PRESENCIAL,
            ),
            "precisa_laboratorio": booleano(
                linha.get("precisa_laboratorio", ""), "precisa_laboratorio"
            ),
            "tipo_laboratorio": texto(
                linha.get("tipo_laboratorio", ""), "tipo_laboratorio", obrigatorio=False, maximo=60
            )
            or None,
            "divisao_turma": booleano(linha.get("divisao_turma", ""), "divisao_turma"),
            "modo_divisao": opcao(
                linha.get("modo_divisao", ""),
                "modo_divisao",
                m.ModoDivisao,
                padrao=m.ModoDivisao.INDIFERENTE,
            ),
            "max_blocos_por_dia": inteiro(
                linha.get("max_blocos_por_dia", ""), "max_blocos_por_dia", minimo=1, padrao=1
            ),
        },
    )
    db.flush()
    return ("criar" if criou else "atualizar"), f"{sigla} — {curso.sigla} {periodo}"


# --------------------------------------------------------------------- turmas


def _linha_turma(db: Session, unidade: m.Unidade, linha: dict) -> tuple[str, str]:
    curso = _curso(db, unidade, texto(linha.get("curso_sigla", ""), "curso_sigla", maximo=20))
    periodo = texto(linha.get("periodo", ""), "periodo", maximo=40)
    modelo = _modelo_turno(db, unidade, texto(linha.get("modelo_turno", ""), "modelo_turno"))

    turma = db.scalar(
        select(m.Turma).where(m.Turma.curso_id == curso.id, m.Turma.periodo == periodo)
    )
    criou = turma is None
    if turma is None:
        turma = m.Turma(
            curso_id=curso.id, periodo=periodo, turno=modelo.nome, modelo_turno_id=modelo.id
        )
        db.add(turma)

    _aplicar(
        turma,
        {
            "turno": texto(linha.get("turno", ""), "turno", obrigatorio=False, maximo=40)
            or modelo.nome,
            "modelo_turno_id": modelo.id,
            "qtd_alunos": inteiro(linha.get("qtd_alunos", ""), "qtd_alunos", minimo=1, padrao=40),
        },
    )
    db.flush()
    return ("criar" if criou else "atualizar"), f"{curso.sigla} {periodo}"


# --------------------------------------------------------------------- espaços


def _linha_espaco(db: Session, unidade: m.Unidade, linha: dict) -> tuple[str, str]:
    nome = texto(linha.get("nome", ""), "nome", maximo=80)
    espaco = db.scalar(
        select(m.Espaco).where(m.Espaco.unidade_id == unidade.id, m.Espaco.nome == nome)
    )
    criou = espaco is None
    if espaco is None:
        espaco = m.Espaco(unidade_id=unidade.id, nome=nome, tipo=m.TipoEspaco.SALA)
        db.add(espaco)

    _aplicar(
        espaco,
        {
            "tipo": opcao(linha.get("tipo", ""), "tipo", m.TipoEspaco, padrao=m.TipoEspaco.SALA),
            "tipo_laboratorio": texto(
                linha.get("tipo_laboratorio", ""), "tipo_laboratorio", obrigatorio=False, maximo=60
            )
            or None,
            "capacidade": inteiro(linha.get("capacidade", ""), "capacidade", minimo=1, padrao=40),
        },
    )
    db.flush()
    return ("criar" if criou else "atualizar"), nome


# --------------------------------------------------------------- habilitações


def _linha_habilitacao(db: Session, unidade: m.Unidade, linha: dict) -> tuple[str, str]:
    professor = _professor(
        db, unidade, texto(linha.get("professor_identificador", ""), "professor_identificador")
    )
    curso = _curso(db, unidade, texto(linha.get("curso_sigla", ""), "curso_sigla", maximo=20))
    periodo = texto(linha.get("periodo", ""), "periodo", maximo=40)
    sigla = texto(linha.get("disciplina_sigla", ""), "disciplina_sigla", maximo=20)

    disciplina = db.scalar(
        select(m.Disciplina).where(
            m.Disciplina.curso_id == curso.id,
            m.Disciplina.periodo == periodo,
            m.Disciplina.sigla == sigla,
        )
    )
    if disciplina is None:
        raise ValorInvalido(f"Não há a disciplina '{sigla}' em {curso.sigla} {periodo}.")

    origem = opcao(
        linha.get("origem", ""),
        "origem",
        m.OrigemHabilitacao,
        padrao=m.OrigemHabilitacao.HABILITADO,
    )
    habilitacao = db.scalar(
        select(m.Habilitacao).where(
            m.Habilitacao.professor_id == professor.id,
            m.Habilitacao.disciplina_id == disciplina.id,
        )
    )
    criou = habilitacao is None
    if habilitacao is None:
        habilitacao = m.Habilitacao(
            professor_id=professor.id, disciplina_id=disciplina.id, origem=origem
        )
        db.add(habilitacao)
    else:
        _aplicar(habilitacao, {"origem": origem})
    db.flush()
    return ("criar" if criou else "atualizar"), f"{professor.nome} → {sigla}"


# ---------------------------------------------------------------- os modelos


MODELOS: dict[str, Modelo] = {
    modelo.tipo: modelo
    for modelo in (
        Modelo(
            tipo="professores",
            titulo="Professores e pontuação",
            descricao=(
                "Cria o docente no escopo e o vincula a esta unidade. Reimportar "
                "atualiza a pontuação sem duplicar ninguém: a chave é o identificador."
            ),
            chaves=("identificador",),
            colunas=(
                Coluna("identificador", "Identificador do docente no CPS.", "P001", True),
                Coluna("nome", "Nome completo.", "Ana Ribeiro", True),
                Coluna("email", "Opcional.", "ana@cps.sp.gov.br"),
                Coluna("tipo_contrato", "INDETERMINADO ou DETERMINADO.", "INDETERMINADO"),
                Coluna("pontuacao", "Pontuação da classificação. Aceita vírgula.", "87,5"),
                Coluna("pont_assiduidade", "Primeiro desempate.", "20"),
                Coluna("pont_titulacao", "Segundo desempate.", "30"),
                Coluna("tempo_exercicio_meses", "Terceiro desempate, em meses.", "120"),
                Coluna("num_filhos", "Quarto desempate.", "0"),
                Coluna("carga_max_semanal", "Vazio usa o padrão da unidade.", ""),
            ),
            aplicar_linha=_linha_professor,
        ),
        Modelo(
            tipo="disciplinas",
            titulo="Matriz curricular",
            descricao="Componentes de um curso já cadastrado, por período.",
            chaves=("curso_sigla", "periodo", "sigla"),
            colunas=(
                Coluna("curso_sigla", "Sigla do curso já cadastrado.", "DSM", True),
                Coluna("periodo", "Semestre, módulo ou série.", "1º sem", True),
                Coluna("sigla", "Sigla do componente.", "ALP", True),
                Coluna("nome", "Nome do componente.", "Algoritmos e Programação", True),
                Coluna("aulas_semanais", "Total de aulas por semana.", "4"),
                Coluna("tamanho_bloco", "Aulas geminadas por bloco.", "2"),
                Coluna("modalidade", "PRESENCIAL ou REMOTA.", "PRESENCIAL"),
                Coluna("precisa_laboratorio", "sim ou não.", "sim"),
                Coluna("tipo_laboratorio", "Tipo exigido, se houver.", "informatica"),
                Coluna("divisao_turma", "Divide a turma em A e B?", "nao"),
                Coluna("modo_divisao", "PARALELA, SEQUENCIAL ou INDIFERENTE.", "INDIFERENTE"),
                Coluna("max_blocos_por_dia", "Blocos do componente no mesmo dia.", "1"),
            ),
            aplicar_linha=_linha_disciplina,
        ),
        Modelo(
            tipo="turmas",
            titulo="Turmas",
            descricao="Uma turma por período de curso, ligada a um modelo de turno.",
            chaves=("curso_sigla", "periodo"),
            colunas=(
                Coluna("curso_sigla", "Sigla do curso já cadastrado.", "DSM", True),
                Coluna("periodo", "Semestre, módulo ou série.", "1º sem", True),
                Coluna("modelo_turno", "Nome do modelo de turno da unidade.", "Noturno", True),
                Coluna("turno", "Rótulo do turno. Vazio usa o nome do modelo.", "Noturno"),
                Coluna("qtd_alunos", "Alunos matriculados.", "40"),
            ),
            aplicar_linha=_linha_turma,
        ),
        Modelo(
            tipo="espacos",
            titulo="Salas e laboratórios",
            descricao="Espaços da unidade. A chave é o nome.",
            chaves=("nome",),
            colunas=(
                Coluna("nome", "Nome do espaço.", "Lab Informática 1", True),
                Coluna("tipo", "SALA ou LABORATORIO.", "LABORATORIO"),
                Coluna("tipo_laboratorio", "Tipo, quando for laboratório.", "informatica"),
                Coluna("capacidade", "Lugares.", "40"),
            ),
            aplicar_linha=_linha_espaco,
        ),
        Modelo(
            tipo="habilitacoes",
            titulo="Habilitações",
            descricao=(
                "Quem pode lecionar o quê. A origem entra no desempate da "
                "atribuição: componente do concurso vem antes de quem já lecionou."
            ),
            chaves=("professor_identificador", "disciplina_sigla"),
            colunas=(
                Coluna("professor_identificador", "Identificador do docente.", "P001", True),
                Coluna("curso_sigla", "Sigla do curso.", "DSM", True),
                Coluna("periodo", "Período da disciplina.", "1º sem", True),
                Coluna("disciplina_sigla", "Sigla da disciplina.", "ALP", True),
                Coluna("origem", "CONCURSO, ANTERIOR ou HABILITADO.", "CONCURSO"),
            ),
            aplicar_linha=_linha_habilitacao,
        ),
    )
}


def _identificar(modelo: Modelo, linha: dict) -> str:
    partes = [linha.get(chave, "") for chave in modelo.chaves]
    return " / ".join(p for p in partes if p) or "linha sem identificação"


def processar(
    db: Session, unidade: m.Unidade, modelo: Modelo, linhas: list[dict], *, aplicar: bool
) -> Relatorio:
    """Roda a importação inteira e devolve o que aconteceu (ou aconteceria).

    Sempre executa tudo: a simulação e a aplicação precisam percorrer o mesmo
    código, senão o relatório do "conferir antes" não vale nada. Quem decide se
    grava é o chamador, pelo commit — este código nunca faz commit.
    """
    relatorio = Relatorio(tipo=modelo.tipo, aplicado=aplicar)
    for i, linha in enumerate(linhas, start=2):  # 1 é o cabeçalho
        try:
            with db.begin_nested():
                acao, descricao = modelo.aplicar_linha(db, unidade, linha)
            relatorio.registrar(i, acao, descricao)
        except ValorInvalido as erro:
            relatorio.registrar(i, "erro", _identificar(modelo, linha), str(erro))
        except Exception as erro:  # erro de banco numa linha não derruba o arquivo
            motivo = f"{type(erro).__name__}: {erro}"
            relatorio.registrar(i, "erro", _identificar(modelo, linha), motivo)
    return relatorio
