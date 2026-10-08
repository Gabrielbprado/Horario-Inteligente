"""Modelo CP-SAT da grade de horario (PLANO.md secao 5).

A decisao e' `x[b, s]`: "o bloco `b` comeca no horario `s`". Os horarios
candidatos vem de `candidatos.slots_iniciais`, o mesmo filtro que a
pre-validacao usa — e' o que impede o solver de achar solucoes que a
pre-validacao declarou impossiveis, e vice-versa.

O espaco entra como `w[b, s, e]`: "o bloco `b` comeca em `s` **e** usa o espaco
`e`", com `sum_e w[b,s,e] == x[b,s]`. Ver DECISOES.md D48 para por que esta
formulacao e' preferivel ao par `y[b,e]` + `z[b,e,u]` do plano original.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.models import ModoDivisao, StatusDisponibilidade
from app.scheduling.candidatos import sequencia, slots_iniciais
from app.scheduling.domain import GradeState, OfertaInfo, SlotInfo
from app.schemas import ConfigRegras
from app.services import blocos_de

ESCALA_PREFERENCIA = 100
"""A pontuacao normalizada entra como inteiro de 0 a 100: o CP-SAT so' aceita
coeficientes inteiros no objetivo."""


# ------------------------------------------------------------------ entradas


@dataclass(frozen=True, slots=True)
class Bloco:
    """Um conjunto de aulas geminadas de uma oferta."""

    id: int
    oferta_id: int
    professor_id: int
    tamanho: int
    idx: int
    """Indice do bloco dentro da oferta; vira `Alocacao.bloco_idx`."""


@dataclass(slots=True)
class Parametros:
    tempo_limite_s: float = 60.0
    workers: int = 0
    """0 = usar todos os nucleos. Use 1 para resultado reprodutivel."""
    semente: int = 42
    manter_fixadas: bool = True
    modo_objetivo: str | None = None
    """`None` usa o que estiver em `config_regras`."""
    grade_anterior: list | None = None
    """`AlocacaoInfo` da grade anterior, para o hint e o termo de estabilidade."""
    resolver_avisos: bool = False
    """Janela de turma, janela de professor e interjornada deixam de ser custo e
    viram restricao rigida. E' o botao "Resolver avisos" da tela da grade."""
    relaxar: frozenset[tuple[str, int]] = frozenset()
    """Grupos de `resolver_avisos` que o diagnostico provou impossiveis, ex.
    `("janela_turma", 3)`: voltam a ser so' custo para a grade fechar."""


@dataclass(frozen=True, slots=True)
class Alocado:
    oferta_id: int
    professor_id: int
    slot_id: int
    espaco_id: int | None
    bloco_idx: int


@dataclass(slots=True)
class Solucao:
    status: str
    alocacoes: list[Alocado] = field(default_factory=list)
    objetivo: int | None = None
    limite_inferior: int | None = None
    tempo_s: float = 0.0
    metricas: dict = field(default_factory=dict)

    @property
    def viavel(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


def decompor_em_blocos(estado: GradeState) -> list[Bloco]:
    """Uma oferta de 4 aulas com bloco 2 vira dois blocos de 2."""
    blocos: list[Bloco] = []
    for oferta in sorted(estado.ofertas.values(), key=lambda o: o.id):
        if oferta.professor_id is None:
            continue
        disciplina = estado.disciplina_da(oferta)
        for idx, tamanho in enumerate(
            blocos_de(disciplina.aulas_semanais, disciplina.tamanho_bloco)
        ):
            blocos.append(
                Bloco(
                    id=len(blocos),
                    oferta_id=oferta.id,
                    professor_id=oferta.professor_id,
                    tamanho=tamanho,
                    idx=idx,
                )
            )
    return blocos


# --------------------------------------------------------------------- modelo


class ModeloGrade:
    """Monta o modelo CP-SAT. Separado do `resolver()` para o diagnostico de
    inviabilidade poder remontar o mesmo modelo com literais de suposicao."""

    def __init__(
        self,
        estado: GradeState,
        config: ConfigRegras,
        params: Parametros,
        *,
        com_suposicoes: bool = False,
    ):
        self.estado = estado
        self.config = config
        self.params = params
        self.com_suposicoes = com_suposicoes
        self.suposicoes: dict[tuple[str, int], cp_model.IntVar] = {}
        """Literais que ligam/desligam cada grupo de restricoes, usados pelo
        diagnostico de inviabilidade."""
        self.modelo = cp_model.CpModel()
        self.blocos = decompor_em_blocos(estado)

        self.inicios: dict[int, list[SlotInfo]] = {}
        """Horarios candidatos por bloco."""
        self.span: dict[tuple[int, int], list[SlotInfo]] = {}
        """`(bloco_id, slot_id)` -> os horarios que o bloco ocupa se comecar ali."""
        self.x: dict[tuple[int, int], cp_model.IntVar] = {}
        self.w: dict[tuple[int, int, int], cp_model.IntVar] = {}
        self.w_por_inicio: dict[tuple[int, int], list[tuple[int, cp_model.IntVar]]] = {}
        """`(bloco, slot inicial)` -> [(espaco, variavel)]. Sem este indice,
        montar a ocupacao dos espacos varreria `w` inteiro por horario."""
        self.cobertura: dict[tuple[int, int], list[cp_model.IntVar]] = {}
        """`(bloco, slot ocupado)` -> variaveis `x` que o ocupam."""
        self.termos: dict[str, cp_model.LinearExpr] = {}
        self.concentrada: dict[int, cp_model.IntVar] = {}
        """`oferta -> booleano`: a disciplina marcada para concentrar ficou
        mesmo no mesmo dia e seguida."""
        self.inviaveis: list[Bloco] = []
        """Blocos sem nenhum horario possivel (a pre-validacao ja' avisou)."""

        self._variaveis()
        self._restricoes()
        if not com_suposicoes:
            # O diagnostico so' quer saber o que nao cabe junto; montar o
            # objetivo ali seria trabalho jogado fora.
            self._objetivo()

    # -------------------------------------------------------------- variaveis

    def _variaveis(self) -> None:
        cache: dict[tuple[int, int], list[SlotInfo]] = {}
        fixadas = self._fixadas()

        for bloco in self.blocos:
            oferta = self.estado.ofertas[bloco.oferta_id]
            chave = (oferta.id, bloco.tamanho)
            if chave not in cache:
                cache[chave] = slots_iniciais(self.estado, self.config, oferta, bloco.tamanho)
            candidatos = cache[chave]

            fixo = fixadas.get((bloco.oferta_id, bloco.idx))
            if fixo is not None:
                candidatos = [s for s in candidatos if s.id == fixo]

            self.inicios[bloco.id] = candidatos
            if not candidatos:
                self.inviaveis.append(bloco)
                continue

            compativeis = self._espacos_de(oferta)
            for slot in candidatos:
                var = self.modelo.new_bool_var(f"x_b{bloco.id}_s{slot.id}")
                self.x[(bloco.id, slot.id)] = var
                span = sequencia(self.estado, slot, bloco.tamanho)
                self.span[(bloco.id, slot.id)] = span
                for ocupado in span:
                    self.cobertura.setdefault((bloco.id, ocupado.id), []).append(var)

                if compativeis is None:
                    continue  # aula remota: nao ocupa espaco
                usos = []
                for espaco in compativeis:
                    uso = self.modelo.new_bool_var(f"w_b{bloco.id}_s{slot.id}_e{espaco}")
                    self.w[(bloco.id, slot.id, espaco)] = uso
                    usos.append((espaco, uso))
                self.w_por_inicio[(bloco.id, slot.id)] = usos
                # Escolhe exatamente um espaco quando o bloco cai aqui.
                self.modelo.add(sum(u for _, u in usos) == var)

    def _fixadas(self) -> dict[tuple[int, int], int]:
        """`(oferta_id, bloco_idx)` -> slot inicial travado pelo cadeado."""
        if not self.params.manter_fixadas:
            return {}
        inicio: dict[tuple[int, int], int] = {}
        for a in self.estado.alocacoes:
            if not a.fixada or a.slot_id not in self.estado.slots:
                continue
            chave = (a.oferta_id, a.bloco_idx)
            atual = inicio.get(chave)
            ordem = self.estado.slots[a.slot_id].ordem
            if atual is None or ordem < self.estado.slots[atual].ordem:
                inicio[chave] = a.slot_id
        return inicio

    def _espacos_de(self, oferta: OfertaInfo) -> list[int] | None:
        """Ids de espaco que servem a oferta, ou `None` se ela e' remota."""
        disciplina = self.estado.disciplina_da(oferta)
        if disciplina.remota:
            return None
        turma = self.estado.turma_da(oferta)
        alunos = turma.qtd_alunos if oferta.subturma is None else -(-turma.qtd_alunos // 2)
        return sorted(e.id for e in self.estado.espacos.values() if e.atende(disciplina, alunos))

    def cobre(self, bloco_id: int, slot_id: int) -> list[cp_model.IntVar]:
        """Variaveis `x` que fazem o bloco ocupar este horario."""
        return self.cobertura.get((bloco_id, slot_id), [])

    # ------------------------------------------------------------- restricoes

    def _restricoes(self) -> None:
        self._cada_bloco_uma_vez()
        self._um_por_slot()
        self._divisao_de_turma()
        self._concentrar()
        self._blocos_por_dia()
        self._limite_diario()
        self._interjornada()
        self._sem_janelas()

    def _cada_bloco_uma_vez(self) -> None:
        for bloco in self.blocos:
            candidatos = self.inicios.get(bloco.id)
            if candidatos:
                self.modelo.add_exactly_one(self.x[(bloco.id, s.id)] for s in candidatos)

    def _ocupacao(self) -> dict[str, dict]:
        """Indices `(recurso, slot) -> [variaveis que ocupam]`, montados uma vez."""
        professor: dict[tuple[int, int], list] = {}
        fluxo: dict[tuple[tuple[int, str], int], list] = {}
        espaco: dict[tuple[int, int], list] = {}

        for bloco in self.blocos:
            oferta = self.estado.ofertas[bloco.oferta_id]
            fluxos = self.estado.fluxos_da_oferta(oferta)
            for inicio in self.inicios.get(bloco.id, ()):
                var = self.x[(bloco.id, inicio.id)]
                usos = self.w_por_inicio.get((bloco.id, inicio.id), ())
                for slot in self.span[(bloco.id, inicio.id)]:
                    professor.setdefault((bloco.professor_id, slot.id), []).append(var)
                    for f in fluxos:
                        fluxo.setdefault((f, slot.id), []).append(var)
                    for e_id, uso in usos:
                        espaco.setdefault((e_id, slot.id), []).append(uso)

        return {"professor": professor, "fluxo": fluxo, "espaco": espaco}

    def _suposicao(self, tipo: str, id_: int) -> cp_model.IntVar:
        chave = (tipo, id_)
        if chave not in self.suposicoes:
            self.suposicoes[chave] = self.modelo.new_bool_var(f"sup_{tipo}_{id_}")
        return self.suposicoes[chave]

    def _rigida(self, expressao, tipo: str, id_: int) -> None:
        """Adiciona a restricao; com `com_suposicoes`, atras do literal do grupo."""
        restricao = self.modelo.add(expressao)
        if self.com_suposicoes:
            restricao.only_enforce_if(self._suposicao(tipo, id_))

    def _no_maximo_um(self, variaveis: list, tipo: str, id_: int) -> None:
        """Um recurso, um horario. Com `com_suposicoes`, a restricao fica atras
        de um literal para o diagnostico poder perguntar "e se esta caisse?"."""
        if len(variaveis) <= 1:
            return
        restricao = self.modelo.add(sum(variaveis) <= 1)
        if self.com_suposicoes:
            restricao.only_enforce_if(self._suposicao(tipo, id_))

    def _um_por_slot(self) -> None:
        self.indices = self._ocupacao()
        for (professor_id, _), variaveis in sorted(self.indices["professor"].items()):
            self._no_maximo_um(variaveis, "professor", professor_id)
        for (fluxo, _), variaveis in sorted(
            self.indices["fluxo"].items(), key=lambda kv: (kv[0][0], kv[0][1])
        ):
            self._no_maximo_um(variaveis, "turma", fluxo[0])
        for (espaco_id, _), variaveis in sorted(self.indices["espaco"].items()):
            self._no_maximo_um(variaveis, "espaco", espaco_id)

    def _divisao_de_turma(self) -> None:
        """PARALELA: A e B no mesmo horario (e' o sentido da divisao).
        SEQUENCIAL: horarios diferentes."""
        por_disciplina: dict[tuple[int, int], list[OfertaInfo]] = {}
        for oferta in self.estado.ofertas.values():
            if oferta.subturma:
                por_disciplina.setdefault((oferta.turma_id, oferta.disciplina_id), []).append(
                    oferta
                )

        blocos_de_oferta: dict[int, dict[int, Bloco]] = {}
        for bloco in self.blocos:
            blocos_de_oferta.setdefault(bloco.oferta_id, {})[bloco.idx] = bloco

        for (_, disciplina_id), ofertas in sorted(por_disciplina.items()):
            if len(ofertas) != 2:
                continue
            modo = self.estado.disciplinas[disciplina_id].modo_divisao
            a, b = sorted(ofertas, key=lambda o: o.subturma or "")
            de_a = blocos_de_oferta.get(a.id, {})
            de_b = blocos_de_oferta.get(b.id, {})

            if modo == ModoDivisao.PARALELA:
                for idx, bloco_a in de_a.items():
                    bloco_b = de_b.get(idx)
                    if bloco_b is None:
                        continue
                    candidatos = {s.id for s in self.inicios.get(bloco_a.id, ())} | {
                        s.id for s in self.inicios.get(bloco_b.id, ())
                    }
                    for slot_id in sorted(candidatos):
                        va = self.x.get((bloco_a.id, slot_id))
                        vb = self.x.get((bloco_b.id, slot_id))
                        if va is not None and vb is not None:
                            self.modelo.add(va == vb)
                        elif va is not None:
                            self.modelo.add(va == 0)
                        elif vb is not None:
                            self.modelo.add(vb == 0)

            elif modo == ModoDivisao.SEQUENCIAL:
                for bloco_a in de_a.values():
                    slots_a = {slot_id for (bid, slot_id) in self.cobertura if bid == bloco_a.id}
                    for bloco_b in de_b.values():
                        for slot_id in sorted(slots_a):
                            juntos = self.cobre(bloco_a.id, slot_id) + self.cobre(
                                bloco_b.id, slot_id
                            )
                            if len(juntos) > 1:
                                self.modelo.add(sum(juntos) <= 1)

    def _blocos_por_dia(self) -> None:
        por_oferta: dict[int, list[Bloco]] = {}
        for bloco in self.blocos:
            por_oferta.setdefault(bloco.oferta_id, []).append(bloco)

        for oferta_id, blocos in sorted(por_oferta.items()):
            limite = self.estado.disciplina_da(self.estado.ofertas[oferta_id]).max_blocos_por_dia
            if limite >= len(blocos):
                continue
            # Marcada para concentrar: o limite so' vale se ela nao couber
            # concentrada e tiver de ficar espalhada (ver `_concentrar`).
            concentrada = self.concentrada.get(oferta_id)
            for dia in self._dias():
                no_dia = [
                    self.x[(b.id, s.id)]
                    for b in blocos
                    for s in self.inicios.get(b.id, ())
                    if s.dia == dia
                ]
                if len(no_dia) > limite:
                    restricao = self.modelo.add(sum(no_dia) <= limite)
                    if concentrada is not None:
                        restricao.only_enforce_if(concentrada.negated())
                    elif self.com_suposicoes:
                        restricao.only_enforce_if(self._suposicao("oferta", oferta_id))

    def _concentrar(self) -> None:
        """Disciplina marcada para concentrar: todos os blocos da oferta no
        mesmo dia e em horarios seguidos da turma. E' o "4" do 4 + 2 da Fatec
        — dois pares da mesma disciplina, um de cada lado do intervalo.

        Nao e' regra rigida: e' um booleano por oferta, que o objetivo cobra
        com o peso mais alto de todos. Seis disciplinas concentradas numa
        manha de cinco dias nao cabem (uma por dia); em vez de "sem solucao",
        o solver concentra as cinco que cabem e espalha a que sobrou, que
        volta a obedecer `max_blocos_por_dia` (D123).

        "Seguidos" e' contar trechos: em cada dia, a ocupacao da oferta ao
        longo dos horarios da turma so' pode comecar uma vez.
        """
        por_oferta: dict[int, list[Bloco]] = {}
        for bloco in self.blocos:
            por_oferta.setdefault(bloco.oferta_id, []).append(bloco)

        for oferta_id, blocos in sorted(por_oferta.items()):
            oferta = self.estado.ofertas[oferta_id]
            if len(blocos) < 2 or not self.estado.disciplina_da(oferta).concentrar_no_dia:
                continue
            concentrada = self.modelo.new_bool_var(f"conc_o{oferta_id}")
            self.concentrada[oferta_id] = concentrada

            por_dia: dict[int, list[SlotInfo]] = {}
            turma = self.estado.turma_da(oferta)
            for slot in self.estado.slots_do_modelo(turma.modelo_turno_id):
                por_dia.setdefault(slot.dia, []).append(slot)

            for dia, slots in sorted(por_dia.items()):
                inicios = [
                    [self.x[(b.id, s.id)] for s in self.inicios.get(b.id, ()) if s.dia == dia]
                    for b in blocos
                ]
                if not all(inicios):
                    # Algum bloco nao tem onde comecar neste dia: concentrada
                    # aqui ela nao fica.
                    for variaveis in inicios:
                        for v in variaveis:
                            self.modelo.add(v == 0).only_enforce_if(concentrada)
                    continue

                # Ou todos os blocos estao neste dia, ou nenhum.
                neste_dia = self.modelo.new_bool_var(f"conc_o{oferta_id}_d{dia}")
                for variaveis in inicios:
                    self.modelo.add(sum(variaveis) == neste_dia).only_enforce_if(concentrada)

                trechos = []
                anterior: list[cp_model.IntVar] = []
                for slot in sorted(slots, key=lambda s: s.ordem):
                    atual = [v for b in blocos for v in self.cobre(b.id, slot.id)]
                    if atual:
                        comeca = self.modelo.new_bool_var(
                            f"conc_ini_o{oferta_id}_d{dia}_o{slot.ordem}"
                        )
                        self.modelo.add(comeca >= sum(atual) - sum(anterior))
                        trechos.append(comeca)
                    anterior = atual
                if len(trechos) > 1:
                    self.modelo.add(sum(trechos) <= 1).only_enforce_if(concentrada)

    # ----------------------------------------------------- ocupacao derivada

    def _dias(self) -> list[int]:
        return sorted({s.dia for s in self.estado.slots.values()})

    def _faixas_do_dia(self, dia: int) -> list[tuple[int, int]]:
        """Horarios distintos do dia, em ordem, somando todos os modelos de turno.

        E' o eixo usado para janela do professor: um docente pode ter turma de
        manha e de noite no mesmo dia, e as duas tem uma "1a aula".
        """
        return sorted(
            {(s.inicio_min, s.fim_min) for s in self.estado.slots.values() if s.dia == dia}
        )

    def _ocupa_professor(self) -> dict[tuple[int, int, int], cp_model.IntVar]:
        """`(professor, dia, indice da faixa)` -> booleano de ocupacao."""
        ocupa: dict[tuple[int, int, int], cp_model.IntVar] = {}
        professores = sorted({b.professor_id for b in self.blocos})
        for dia in self._dias():
            faixas = self._faixas_do_dia(dia)
            slots_por_faixa: dict[tuple[int, int], list[int]] = {}
            for s in self.estado.slots.values():
                if s.dia == dia:
                    slots_por_faixa.setdefault((s.inicio_min, s.fim_min), []).append(s.id)

            for professor_id in professores:
                for p, faixa in enumerate(faixas):
                    variaveis = [
                        v
                        for slot_id in slots_por_faixa[faixa]
                        for v in self.indices["professor"].get((professor_id, slot_id), ())
                    ]
                    if not variaveis:
                        continue
                    # OR, e nao `== sum(...)`: com igualdade, um booleano
                    # imporia "no maximo uma aula" aqui dentro — uma
                    # exclusividade escondida que o diagnostico nao consegue
                    # relaxar, e que deixava o nucleo de inviabilidade vazio.
                    var = self.modelo.new_bool_var(f"op_p{professor_id}_d{dia}_f{p}")
                    for v in variaveis:
                        self.modelo.add(var >= v)
                    self.modelo.add(var <= sum(variaveis))
                    ocupa[(professor_id, dia, p)] = var
        return ocupa

    def _ocupa_turma(self) -> dict[tuple[int, int, int], cp_model.IntVar]:
        """`(turma, dia, ordem)` -> booleano. A turma esta' ocupada se qualquer
        um dos seus fluxos (A ou B) esta'."""
        ocupa: dict[tuple[int, int, int], cp_model.IntVar] = {}
        for turma in sorted(self.estado.turmas.values(), key=lambda t: t.id):
            for slot in self.estado.slots_do_modelo(turma.modelo_turno_id):
                por_fluxo = [
                    self.indices["fluxo"].get(((turma.id, sub), slot.id), []) for sub in ("A", "B")
                ]
                if not any(por_fluxo):
                    continue
                var = self.modelo.new_bool_var(f"ot_t{turma.id}_d{slot.dia}_o{slot.ordem}")
                todas = [v for grupo in por_fluxo for v in grupo]
                for v in todas:
                    self.modelo.add(var >= v)
                self.modelo.add(var <= sum(todas))
                ocupa[(turma.id, slot.dia, slot.ordem)] = var
        return ocupa

    def _buracos(
        self, ocupa: dict[tuple[int, int, int], cp_model.IntVar], prefixo: str
    ) -> dict[int, list[cp_model.IntVar]]:
        """Horarios vagos que ainda tem aula depois, no mesmo dia, por recurso
        (turma ou professor).

        Vago no fim do dia nao conta: sair mais cedo e' o resultado desejado, nao
        um defeito (spec 5.4.1).
        """
        cache = self.__dict__.setdefault("_cache_buracos", {})
        if prefixo in cache:
            return cache[prefixo]
        buracos: dict[int, list[cp_model.IntVar]] = {}
        chaves: dict[tuple[int, int], set[int]] = {}
        for recurso, dia, pos in ocupa:
            chaves.setdefault((recurso, dia), set()).add(pos)
        if prefixo == "t":
            # O validador conta todo horario do turno da turma, inclusive o que
            # nenhum bloco poderia ocupar (ex.: unico professor indisponivel na
            # 1a aula). Sem isto o solver "nao via" essa janela e a tela a
            # mostrava mesmo com a grade otima (D114).
            for recurso, dia in list(chaves):
                turma = self.estado.turmas[recurso]
                chaves[(recurso, dia)] |= {
                    s.ordem
                    for s in self.estado.slots_do_modelo(turma.modelo_turno_id)
                    if s.dia == dia
                }

        for (recurso, dia), posicoes in sorted(chaves.items()):
            ordenadas = sorted(posicoes)
            for i, pos in enumerate(ordenadas[:-1]):
                depois = [
                    ocupa[(recurso, dia, p)]
                    for p in ordenadas[i + 1 :]
                    if (recurso, dia, p) in ocupa
                ]
                if not depois:
                    continue
                tem_depois = self.modelo.new_bool_var(f"{prefixo}_dep_{recurso}_{dia}_{pos}")
                for v in depois:
                    self.modelo.add(tem_depois >= v)
                self.modelo.add(tem_depois <= sum(depois))

                buraco = self.modelo.new_bool_var(f"{prefixo}_bur_{recurso}_{dia}_{pos}")
                self.modelo.add(buraco >= tem_depois - ocupa.get((recurso, dia, pos), 0))
                buracos.setdefault(recurso, []).append(buraco)
        cache[prefixo] = buracos
        return buracos

    def _sem_janelas(self) -> None:
        """Com `resolver_avisos`, nenhuma turma e nenhum professor fica com
        janela. Uma restricao por recurso, atras de um literal, para o
        diagnostico poder dizer de quem e' a janela que nao tem jeito."""
        if not self.params.resolver_avisos:
            return
        ocupa_prof = getattr(self, "_cache_ocupa_prof", None) or self._ocupa_professor()
        self._cache_ocupa_prof = ocupa_prof
        for tipo, grupos in (
            ("janela_turma", self._buracos(self._ocupa_turma(), "t")),
            ("janela_professor", self._buracos(ocupa_prof, "p")),
        ):
            for recurso, variaveis in grupos.items():
                if (tipo, recurso) in self.params.relaxar:
                    continue
                restricao = self.modelo.add(sum(variaveis) == 0)
                if self.com_suposicoes:
                    restricao.only_enforce_if(self._suposicao(tipo, recurso))

    # -------------------------------------------------- limites configuraveis

    def _limite_diario(self) -> None:
        regra = self.config.limite_diario
        if not regra.ativo:
            return
        ocupa = getattr(self, "_cache_ocupa_prof", None) or self._ocupa_professor()
        self._cache_ocupa_prof = ocupa

        por_professor_dia: dict[tuple[int, int], list] = {}
        for (professor_id, dia, pos), var in ocupa.items():
            por_professor_dia.setdefault((professor_id, dia), []).append((pos, var))

        for (_, _), pares in sorted(por_professor_dia.items()):
            pares.sort()
            variaveis = [v for _, v in pares]
            self.modelo.add(sum(variaveis) <= regra.max_intercaladas)
            janela = regra.max_consecutivas + 1
            for i in range(len(variaveis) - janela + 1):
                self.modelo.add(sum(variaveis[i : i + janela]) <= regra.max_consecutivas)

    def _interjornada(self) -> None:
        regra = self.config.interjornada
        if regra.modo != "rigida" and not self.params.resolver_avisos:
            return
        descanso = regra.horas * 60
        ocupa = getattr(self, "_cache_ocupa_prof", None) or self._ocupa_professor()
        self._cache_ocupa_prof = ocupa

        externas: dict[tuple[int, int], list] = {}
        for o in self.estado.ocupacoes_externas:
            externas.setdefault((o.professor_id, o.dia), []).append(o)

        dias = self._dias()
        for professor_id in sorted({b.professor_id for b in self.blocos}):
            if ("interjornada", professor_id) in self.params.relaxar:
                continue
            # Aula fixa em outra unidade no dia vizinho proibe os horarios daqui
            # que nao deixariam o descanso minimo.
            for (dia, pos), var in [
                ((d, p), v) for (pid, d, p), v in ocupa.items() if pid == professor_id
            ]:
                inicio, fim = self._faixas_do_dia(dia)[pos]
                conflita = any(
                    (24 * 60 - fim) + o.inicio_min < descanso
                    for o in externas.get((professor_id, dia + 1), ())
                ) or any(
                    (24 * 60 - o.fim_min) + inicio < descanso
                    for o in externas.get((professor_id, dia - 1), ())
                )
                if conflita:
                    self._rigida(var == 0, "interjornada", professor_id)

            for dia, seguinte in zip(dias, dias[1:], strict=False):
                if seguinte != dia + 1:
                    continue
                faixas_hoje = self._faixas_do_dia(dia)
                faixas_amanha = self._faixas_do_dia(seguinte)
                for p, (_, fim) in enumerate(faixas_hoje):
                    hoje = ocupa.get((professor_id, dia, p))
                    if hoje is None:
                        continue
                    for q, (inicio, _) in enumerate(faixas_amanha):
                        amanha = ocupa.get((professor_id, seguinte, q))
                        if amanha is None:
                            continue
                        if (24 * 60 - fim) + inicio < descanso:
                            # Os dois nao podem acontecer: nao sobra descanso.
                            self._rigida(hoje + amanha <= 1, "interjornada", professor_id)

    # --------------------------------------------------------------- objetivo

    def _objetivo(self) -> None:
        pesos = self.config.pesos
        ocupa_turma = self._ocupa_turma()
        ocupa_prof = getattr(self, "_cache_ocupa_prof", None) or self._ocupa_professor()
        self._cache_ocupa_prof = ocupa_prof

        janelas_t = [v for vs in self._buracos(ocupa_turma, "t").values() for v in vs]
        janelas_p = [v for vs in self._buracos(ocupa_prof, "p").values() for v in vs]
        self.termos["nao_concentradas"] = (
            sum(1 - v for v in self.concentrada.values()) if self.concentrada else 0
        )
        self.termos["janela_turma"] = sum(janelas_t) if janelas_t else 0
        self.termos["janela_professor"] = sum(janelas_p) if janelas_p else 0
        self.termos["preferencia"] = -self._preferencia()
        self.termos["dias_professor"] = self._dias_do_professor(ocupa_prof)
        self.termos["estabilidade"] = self._estabilidade()
        self.termos["dia_curto_no_fim"] = self._dia_curto_no_fim(ocupa_turma)

        self.ordem_lexicografica = [
            "nao_concentradas",
            "janela_turma",
            "janela_professor",
            "preferencia",
            "dias_professor",
            "estabilidade",
            "dia_curto_no_fim",
        ]
        self.ponderado = sum(
            getattr(pesos, nome) * self.termos[nome] for nome in self.ordem_lexicografica
        )

    def _pontuacao_normalizada(self) -> dict[int, int]:
        """Pontuacao reescalada para 0..100 entre o menor e o maior da unidade.

        E' o que faz "quem tem mais pontuacao tem prioridade de horario" virar
        peso no objetivo (Portaria CETEC 1.263/2017, art. 7).
        """
        pontos = [v.pontuacao for v in self.estado.vinculos.values()]
        if not pontos:
            return {}
        menor, maior = min(pontos), max(pontos)
        faixa = maior - menor
        return {
            pid: (
                ESCALA_PREFERENCIA
                if faixa == 0
                else round((v.pontuacao - menor) / faixa * ESCALA_PREFERENCIA)
            )
            for pid, v in self.estado.vinculos.items()
        }

    def _preferencia(self) -> cp_model.LinearExpr:
        norma = self._pontuacao_normalizada()
        termos = []
        for bloco in self.blocos:
            peso = norma.get(bloco.professor_id, 0)
            if not peso:
                continue
            for inicio in self.inicios.get(bloco.id, ()):
                atendidos = sum(
                    1
                    for slot in self.span[(bloco.id, inicio.id)]
                    if self.estado.status_disponibilidade(bloco.professor_id, slot.id)
                    == StatusDisponibilidade.PREFERENCIAL
                )
                if atendidos:
                    termos.append(peso * atendidos * self.x[(bloco.id, inicio.id)])
        return sum(termos) if termos else 0

    def _dias_do_professor(self, ocupa) -> cp_model.LinearExpr:
        por_professor_dia: dict[tuple[int, int], list] = {}
        for (professor_id, dia, _), var in ocupa.items():
            por_professor_dia.setdefault((professor_id, dia), []).append(var)

        usados = []
        for (professor_id, dia), variaveis in sorted(por_professor_dia.items()):
            usado = self.modelo.new_bool_var(f"dia_p{professor_id}_d{dia}")
            for v in variaveis:
                self.modelo.add(usado >= v)
            self.modelo.add(usado <= sum(variaveis))
            usados.append(usado)
        return sum(usados) if usados else 0

    def _estabilidade(self) -> cp_model.LinearExpr:
        anterior = self.params.grade_anterior
        if not anterior:
            return 0
        inicio_anterior: dict[tuple[int, int], int] = {}
        for a in anterior:
            slot = self.estado.slots.get(a.slot_id)
            if slot is None:
                continue
            chave = (a.oferta_id, a.bloco_idx)
            atual = inicio_anterior.get(chave)
            if atual is None or slot.ordem < self.estado.slots[atual].ordem:
                inicio_anterior[chave] = a.slot_id

        mudancas = []
        for bloco in self.blocos:
            antes = inicio_anterior.get((bloco.oferta_id, bloco.idx))
            var = self.x.get((bloco.id, antes)) if antes is not None else None
            if var is not None:
                mudancas.append(1 - var)
        return sum(mudancas) if mudancas else 0

    def _dia_curto_no_fim(self, ocupa_turma) -> cp_model.LinearExpr:
        """Desempate leve: prefere encher os primeiros dias e deixar o dia curto
        para o fim da semana."""
        dias = self._dias()
        if len(dias) < 2:
            return 0
        ultimo = max(dias)
        termos = []
        for (_, dia, _), var in ocupa_turma.items():
            peso = ultimo - dia
            if peso:
                termos.append(peso * (1 - var))
        return sum(termos) if termos else 0

    # ------------------------------------------------------------------ hints

    def aplicar_hint(self) -> None:
        anterior = self.params.grade_anterior
        if not anterior:
            return
        inicio: dict[tuple[int, int], int] = {}
        for a in anterior:
            slot = self.estado.slots.get(a.slot_id)
            if slot is None:
                continue
            chave = (a.oferta_id, a.bloco_idx)
            atual = inicio.get(chave)
            if atual is None or slot.ordem < self.estado.slots[atual].ordem:
                inicio[chave] = a.slot_id
        for bloco in self.blocos:
            var = self.x.get((bloco.id, inicio.get((bloco.oferta_id, bloco.idx), -1)))
            if var is not None:
                self.modelo.add_hint(var, 1)

    # ---------------------------------------------------------------- leitura

    def ler(self, valor: Callable[[cp_model.IntVar], int]) -> list[Alocado]:
        alocados: list[Alocado] = []
        for bloco in self.blocos:
            for inicio in self.inicios.get(bloco.id, ()):
                if not valor(self.x[(bloco.id, inicio.id)]):
                    continue
                espaco_id = next(
                    (
                        e
                        for e, var in self.w_por_inicio.get((bloco.id, inicio.id), ())
                        if valor(var)
                    ),
                    None,
                )
                for slot in self.span[(bloco.id, inicio.id)]:
                    alocados.append(
                        Alocado(
                            oferta_id=bloco.oferta_id,
                            professor_id=bloco.professor_id,
                            slot_id=slot.id,
                            espaco_id=espaco_id,
                            bloco_idx=bloco.idx,
                        )
                    )
        return alocados


# ------------------------------------------------------------------ execucao


class _Callback(cp_model.CpSolverSolutionCallback):
    """Guarda a melhor solucao encontrada ate' agora para a tela desenhar ao vivo."""

    def __init__(self, modelo: ModeloGrade, aviso: Callable[[Solucao], None] | None):
        super().__init__()
        self._modelo = modelo
        self._aviso = aviso
        self.solucoes = 0
        self.melhor: Solucao | None = None

    def on_solution_callback(self) -> None:  # pragma: no cover - chamado pelo CP-SAT
        self.solucoes += 1
        self.melhor = Solucao(
            status="FEASIBLE",
            alocacoes=self._modelo.ler(self.value),
            objetivo=round(self.objective_value),
            limite_inferior=round(self.best_objective_bound),
            tempo_s=self.wall_time,
        )
        if self._aviso:
            self._aviso(self.melhor)


def _configurar(solver: cp_model.CpSolver, params: Parametros) -> None:
    """Semente fixa e limite de tempo de relogio.

    A semente torna a busca de **um** worker reprodutivel. Com varios workers e
    limite de tempo de relogio, quem prova a otimalidade primeiro e' uma corrida,
    entao duas execucoes podem devolver otimos diferentes de mesmo custo. Para
    resultado byte-a-byte identico, use `workers=1` (ver DECISOES.md D50).
    """
    solver.parameters.max_time_in_seconds = params.tempo_limite_s
    solver.parameters.num_search_workers = params.workers or (os.cpu_count() or 1)
    solver.parameters.random_seed = params.semente


def resolver(
    estado: GradeState,
    config: ConfigRegras,
    params: Parametros | None = None,
    *,
    aviso: Callable[[Solucao], None] | None = None,
) -> Solucao:
    """Resolve a grade. `aviso` recebe cada solucao intermediaria melhor."""
    params = params or Parametros()
    modelo = ModeloGrade(estado, config, params)
    modo = params.modo_objetivo or config.modo_objetivo

    if modelo.inviaveis:
        return Solucao(
            status="INFEASIBLE",
            metricas={
                "blocos_sem_horario": [
                    estado.rotulo_oferta(estado.ofertas[b.oferta_id]) for b in modelo.inviaveis
                ]
            },
        )

    if modo == "lexicografico":
        return _resolver_lexicografico(modelo, params, aviso)
    return _resolver_ponderado(modelo, params, aviso)


def _finalizar(
    modelo: ModeloGrade, solver: cp_model.CpSolver, status: int, callback: _Callback
) -> Solucao:
    nome = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Solucao(status=nome, tempo_s=solver.wall_time)

    return Solucao(
        status=nome,
        alocacoes=modelo.ler(solver.value),
        objetivo=round(solver.objective_value),
        limite_inferior=round(solver.best_objective_bound),
        tempo_s=solver.wall_time,
        metricas={
            "solucoes": callback.solucoes,
            **{
                nome_termo: int(solver.value(expr)) if not isinstance(expr, int) else expr
                for nome_termo, expr in modelo.termos.items()
            },
        },
    )


def _resolver_ponderado(
    modelo: ModeloGrade, params: Parametros, aviso: Callable[[Solucao], None] | None
) -> Solucao:
    modelo.modelo.minimize(modelo.ponderado)
    modelo.aplicar_hint()

    solver = cp_model.CpSolver()
    _configurar(solver, params)
    callback = _Callback(modelo, aviso)
    status = solver.solve(modelo.modelo, callback)
    return _finalizar(modelo, solver, status, callback)


def _resolver_lexicografico(
    modelo: ModeloGrade, params: Parametros, aviso: Callable[[Solucao], None] | None
) -> Solucao:
    """Otimiza um criterio por vez: resolve o primeiro, trava o valor otimo como
    restricao e passa ao seguinte. Cada etapa herda o tempo que sobrou."""
    modelo.aplicar_hint()
    solver = cp_model.CpSolver()
    callback = _Callback(modelo, aviso)
    status = cp_model.UNKNOWN
    restante = params.tempo_limite_s
    etapas = [n for n in modelo.ordem_lexicografica if not isinstance(modelo.termos[n], int)]

    for i, nome in enumerate(etapas):
        modelo.modelo.minimize(modelo.termos[nome])
        _configurar(solver, params)
        solver.parameters.max_time_in_seconds = max(1.0, restante / (len(etapas) - i))
        status = solver.solve(modelo.modelo, callback)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        restante = max(0.0, restante - solver.wall_time)
        modelo.modelo.add(modelo.termos[nome] <= round(solver.objective_value))

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # O ultimo `solve` ja' respeita todos os criterios travados.
        return _finalizar(modelo, solver, status, callback)
    return Solucao(status=solver.status_name(status), tempo_s=solver.wall_time)
