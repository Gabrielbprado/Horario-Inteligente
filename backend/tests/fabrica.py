"""Construtor de cenarios para os testes do validador e do solver.

Monta um `GradeState` a mao, sem banco, para cada teste descrever exatamente a
situacao que quer checar. Os ids de slot sao `dia * 10 + ordem`, entao
`aloca(oferta, dia=0, ordem=1)` e' legivel e o slot e' facil de referenciar.
"""

from __future__ import annotations

from app.models import (
    ModalidadeAula,
    ModoDivisao,
    StatusDisponibilidade,
    TipoContrato,
    TipoEspaco,
)
from app.scheduling.domain import (
    AlocacaoInfo,
    DisciplinaInfo,
    EspacoInfo,
    GradeState,
    OcupacaoExterna,
    OfertaInfo,
    ProfessorInfo,
    SlotInfo,
    TurmaInfo,
    VinculoInfo,
    Violacao,
)
from app.scheduling.prevalidate import prevalidar
from app.scheduling.validator import validar
from app.schemas import ConfigRegras

MODELO_PADRAO = 1

# Preset "Fatec noturno": 4 aulas em 2 blocos, intervalo entre a 2a e a 3a.
HORARIOS_NOTURNO = [
    (1, 19 * 60, 19 * 60 + 50, 1),
    (2, 19 * 60 + 50, 20 * 60 + 40, 1),
    (3, 20 * 60 + 50, 21 * 60 + 40, 2),
    (4, 21 * 60 + 40, 22 * 60 + 30, 2),
]


def slot_id(dia: int, ordem: int) -> int:
    return dia * 10 + ordem


class Cenario:
    def __init__(
        self,
        *,
        dias: int = 5,
        horarios: list[tuple[int, int, int, int]] | None = None,
        modelo: int = MODELO_PADRAO,
        **config,
    ):
        self.config = ConfigRegras.model_validate(config)
        self.estado = GradeState(unidade_id=1, unidade_nome="Fatec Teste")
        self.modelo = modelo
        self._proximo_id = 1
        self.ids: dict[str, int] = {}

        for dia in range(dias):
            for ordem, inicio, fim, bloco in horarios or HORARIOS_NOTURNO:
                sid = slot_id(dia, ordem)
                self.estado.slots[sid] = SlotInfo(
                    id=sid,
                    modelo_turno_id=modelo,
                    dia=dia,
                    ordem=ordem,
                    bloco_id=bloco,
                    inicio_min=inicio,
                    fim_min=fim,
                )

    # ------------------------------------------------------------- criacao

    def _id(self) -> int:
        self._proximo_id += 1
        return self._proximo_id

    def turno(self, modelo: int, dias: range, horarios: list[tuple[int, int, int, int]]) -> int:
        """Um segundo modelo de turno (ex.: manha) na mesma unidade."""
        for dia in dias:
            for ordem, inicio, fim, bloco in horarios:
                sid = modelo * 1000 + dia * 10 + ordem
                self.estado.slots[sid] = SlotInfo(
                    id=sid,
                    modelo_turno_id=modelo,
                    dia=dia,
                    ordem=ordem,
                    bloco_id=bloco,
                    inicio_min=inicio,
                    fim_min=fim,
                )
        return modelo

    def professor(self, nome: str, **vinculo) -> int:
        pid = self._id()
        self.estado.professores[pid] = ProfessorInfo(id=pid, nome=nome)
        self.estado.vinculos[pid] = VinculoInfo(
            professor_id=pid,
            unidade_id=1,
            tipo_contrato=vinculo.pop("tipo_contrato", TipoContrato.INDETERMINADO),
            pontuacao=vinculo.pop("pontuacao", 50.0),
            pont_assiduidade=vinculo.pop("pont_assiduidade", 0.0),
            pont_titulacao=vinculo.pop("pont_titulacao", 0.0),
            tempo_exercicio_meses=vinculo.pop("tempo_exercicio_meses", 0),
            num_filhos=vinculo.pop("num_filhos", 0),
            carga_max_semanal=vinculo.pop("carga_max_semanal", None),
        )
        assert not vinculo, f"campos desconhecidos: {sorted(vinculo)}"
        return pid

    def espaco(
        self,
        nome: str,
        *,
        tipo: TipoEspaco = TipoEspaco.SALA,
        tipo_laboratorio: str | None = None,
        capacidade: int = 40,
    ) -> int:
        eid = self._id()
        self.estado.espacos[eid] = EspacoInfo(
            id=eid,
            nome=nome,
            tipo=tipo,
            tipo_laboratorio=tipo_laboratorio,
            capacidade=capacidade,
        )
        return eid

    def turma(
        self,
        periodo: str = "1o sem",
        *,
        alunos: int = 40,
        modelo: int | None = None,
        turno: str = "",
    ) -> int:
        tid = self._id()
        self.estado.turmas[tid] = TurmaInfo(
            id=tid,
            curso_id=1,
            curso_sigla="DSM",
            periodo=periodo,
            modelo_turno_id=modelo or self.modelo,
            qtd_alunos=alunos,
            turno=turno,
        )
        return tid

    def disciplina(
        self,
        sigla: str,
        *,
        aulas: int = 4,
        tamanho_bloco: int = 2,
        remota: bool = False,
        laboratorio: str | None = None,
        divisao: ModoDivisao | None = None,
        max_blocos_por_dia: int = 1,
        concentrar: bool = False,
    ) -> int:
        did = self._id()
        self.estado.disciplinas[did] = DisciplinaInfo(
            id=did,
            nome=sigla,
            sigla=sigla,
            aulas_semanais=aulas,
            tamanho_bloco=tamanho_bloco,
            modalidade=ModalidadeAula.REMOTA if remota else ModalidadeAula.PRESENCIAL,
            precisa_laboratorio=laboratorio is not None,
            tipo_laboratorio=laboratorio,
            divisao_turma=divisao is not None,
            modo_divisao=divisao or ModoDivisao.INDIFERENTE,
            max_blocos_por_dia=max_blocos_por_dia,
            concentrar_no_dia=concentrar,
        )
        return did

    def oferta(
        self,
        turma: int,
        disciplina: int,
        professor: int | None = None,
        subturma: str | None = None,
    ) -> int:
        oid = self._id()
        self.estado.ofertas[oid] = OfertaInfo(
            id=oid,
            turma_id=turma,
            disciplina_id=disciplina,
            subturma=subturma,
            professor_id=professor,
        )
        return oid

    # ------------------------------------------------------------ alocacao

    def aloca(
        self,
        oferta: int,
        dia: int,
        ordem: int,
        *,
        espaco: int | None = None,
        bloco_idx: int = 0,
        professor: int | None = None,
        slot: int | None = None,
    ) -> AlocacaoInfo:
        info = self.estado.ofertas[oferta]
        alocacao = AlocacaoInfo(
            id=self._id(),
            oferta_id=oferta,
            professor_id=professor if professor is not None else (info.professor_id or 0),
            slot_id=slot if slot is not None else slot_id(dia, ordem),
            espaco_id=espaco,
            bloco_idx=bloco_idx,
        )
        self.estado.alocacoes.append(alocacao)
        return alocacao

    def aloca_bloco(
        self,
        oferta: int,
        dia: int,
        ordem_inicial: int,
        tamanho: int = 2,
        *,
        espaco: int | None = None,
        bloco_idx: int = 0,
    ) -> None:
        for passo in range(tamanho):
            self.aloca(oferta, dia, ordem_inicial + passo, espaco=espaco, bloco_idx=bloco_idx)

    def marca(self, professor: int, dia: int, ordem: int, status: StatusDisponibilidade) -> None:
        self.estado.disponibilidade[(professor, slot_id(dia, ordem))] = status

    def indisponivel(self, professor: int, dia: int, ordens: range | list[int] | None = None):
        for ordem in ordens or [h[0] for h in HORARIOS_NOTURNO]:
            self.marca(professor, dia, ordem, StatusDisponibilidade.INDISPONIVEL)

    def preferencial(self, professor: int, dia: int, ordens: range | list[int]):
        for ordem in ordens:
            self.marca(professor, dia, ordem, StatusDisponibilidade.PREFERENCIAL)

    def aula_em_outra_unidade(
        self,
        professor: int,
        dia: int,
        inicio_min: int,
        fim_min: int,
        *,
        unidade: str = "Etec Teste",
        unidade_id: int = 2,
        rotulo: str = "LP (TDS Módulo I)",
    ) -> None:
        self.estado.ocupacoes_externas.append(
            OcupacaoExterna(
                professor_id=professor,
                unidade_id=unidade_id,
                unidade_nome=unidade,
                dia=dia,
                inicio_min=inicio_min,
                fim_min=fim_min,
                rotulo=rotulo,
            )
        )

    # ------------------------------------------------------------ execucao

    def validar(self) -> list[Violacao]:
        return validar(self.estado, self.config)

    def prevalidar(self) -> list[Violacao]:
        return prevalidar(self.estado, self.config)

    def tipos(self) -> set[str]:
        return {v.tipo for v in self.validar()}

    def tipos_pre(self) -> set[str]:
        return {v.tipo for v in self.prevalidar()}

    def de_tipo(self, tipo: str) -> list[Violacao]:
        return [v for v in self.validar() if v.tipo == tipo]

    def pre_de_tipo(self, tipo: str) -> list[Violacao]:
        return [v for v in self.prevalidar() if v.tipo == tipo]


def cenario_valido() -> Cenario:
    """Uma turma com duas disciplinas de 4 aulas, tudo encaixado sem violacao.

    Os ids ficam em `c.ids` para os testes referenciarem sem adivinhar numeros.
    """
    c = Cenario()
    sala = c.espaco("Sala 1")
    sala2 = c.espaco("Sala 2")
    ana = c.professor("Ana", pontuacao=80)
    bruno = c.professor("Bruno", pontuacao=60)
    turma = c.turma()
    d1 = c.disciplina("ALP")
    d2 = c.disciplina("ESW")
    alp = c.oferta(turma, d1, ana)
    esw = c.oferta(turma, d2, bruno)

    # segunda e terca 1a-2a aula; quarta e quinta 1a-2a aula
    c.aloca_bloco(alp, dia=0, ordem_inicial=1, espaco=sala, bloco_idx=0)
    c.aloca_bloco(alp, dia=1, ordem_inicial=1, espaco=sala, bloco_idx=1)
    c.aloca_bloco(esw, dia=2, ordem_inicial=1, espaco=sala2, bloco_idx=0)
    c.aloca_bloco(esw, dia=3, ordem_inicial=1, espaco=sala2, bloco_idx=1)

    c.ids = {
        "sala": sala,
        "sala2": sala2,
        "ana": ana,
        "bruno": bruno,
        "turma": turma,
        "oferta_alp": alp,
        "oferta_esw": esw,
    }
    return c
