"""Atribuicao sugerida: quem da' qual aula.

Reproduz o ato de atribuicao das normas do CPS, que e' literalmente um algoritmo
guloso sobre a lista de classificacao docente:

- **Etec** (Deliberacao CEETEPS 23/2015 + Portaria CETEC 1.263/2017): a lista
  classificada e' percorrida **duas vezes** — primeiro para *manutencao* das
  aulas que o docente ja' lecionava, depois para *ampliacao* de carga.
- **Fatec** (Deliberacao CEETEPS 52/2019): passada unica, com os contratos por
  prazo indeterminado antes dos demais.

Em ambas, dentro da vez de cada docente as ofertas saem por prioridade de
componente: concurso > lecionava antes > habilitado.

Quando mais de um docente podia assumir a mesma oferta, o melhor classificado
leva (Portaria CETEC 1.263/2017, art. 7) e os demais viram um aviso de
prioridade que diz **qual criterio decidiu**.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.models import ModoDivisao, OrigemHabilitacao, Severidade, TipoContrato
from app.scheduling.domain import GradeState, OfertaInfo, VinculoInfo, Violacao
from app.schemas import ConfigRegras

# Ordem em que um docente escolhe entre as ofertas disponiveis na sua vez.
PRIORIDADE_COMPONENTE = {
    OrigemHabilitacao.CONCURSO: 0,
    OrigemHabilitacao.ANTERIOR: 1,
    OrigemHabilitacao.HABILITADO: 2,
}

ROTULO_COMPONENTE = {
    OrigemHabilitacao.CONCURSO: "componente do concurso",
    OrigemHabilitacao.ANTERIOR: "lecionava no período anterior",
    OrigemHabilitacao.HABILITADO: "habilitado",
}

# Criterios de desempate. A ordem vem de `config.atribuicao.desempates`, entao a
# unidade pode mudar a sequencia sem tocar no codigo.
CRITERIOS: dict[str, tuple[str, Callable[[VinculoInfo], float]]] = {
    "assiduidade": ("assiduidade e pontualidade", lambda v: v.pont_assiduidade),
    "titulacao": ("titulação e atualização", lambda v: v.pont_titulacao),
    "tempo_exercicio": ("tempo de exercício na unidade", lambda v: v.tempo_exercicio_meses),
    "filhos": ("número de filhos", lambda v: v.num_filhos),
}


def _num(valor: float) -> str:
    """Numero em pt-BR, sem casa decimal quando e' inteiro."""
    texto = f"{valor:.1f}" if valor % 1 else f"{valor:.0f}"
    return texto.replace(".", ",")


# ------------------------------------------------------------- classificacao


def chave_classificacao(vinculo: VinculoInfo, config: ConfigRegras) -> tuple:
    """Chave de ordenacao crescente = ordem da lista de classificacao.

    Na Fatec o tipo de contrato entra antes de tudo: quem tem prazo
    indeterminado escolhe primeiro (Deliberacao 52/2019).
    """
    prefixo: tuple = ()
    if config.atribuicao.regra == "FATEC":
        prefixo = (0 if vinculo.tipo_contrato == TipoContrato.INDETERMINADO else 1,)
    desempates = tuple(
        -CRITERIOS[nome][1](vinculo) for nome in config.atribuicao.desempates if nome in CRITERIOS
    )
    return (*prefixo, -vinculo.pontuacao, *desempates, vinculo.professor_id)


def classificar(estado: GradeState, config: ConfigRegras) -> list[VinculoInfo]:
    """Vinculos da unidade na ordem de classificacao docente."""
    return sorted(estado.vinculos.values(), key=lambda v: chave_classificacao(v, config))


MOTIVO_MANUTENCAO = (
    "direito de manutenção das aulas que já lecionava no período anterior "
    "(Deliberação CEETEPS 23/2015)"
)


def criterio_decisivo(
    vencedor: VinculoInfo,
    perdedor: VinculoInfo,
    config: ConfigRegras,
    *,
    manutencao: bool = False,
) -> str:
    """Frase que explica por que `vencedor` passou na frente de `perdedor`.

    Na passada de manutencao o vencedor pode estar **abaixo** do perdedor na
    classificacao: quem decidiu foi o direito de manutencao, nao a pontuacao.
    Dizer "maior pontuação (70 × 78,5)" ali seria simplesmente falso.
    """
    if manutencao and chave_classificacao(perdedor, config) < chave_classificacao(vencedor, config):
        return MOTIVO_MANUTENCAO

    if config.atribuicao.regra == "FATEC" and vencedor.tipo_contrato != perdedor.tipo_contrato:
        if vencedor.tipo_contrato == TipoContrato.INDETERMINADO:
            return "contrato por prazo indeterminado"

    if vencedor.pontuacao != perdedor.pontuacao:
        return f"maior pontuação ({_num(vencedor.pontuacao)} × {_num(perdedor.pontuacao)})"

    for nome in config.atribuicao.desempates:
        rotulo, extrair = CRITERIOS.get(nome, (None, None))
        if extrair is None:
            continue
        a, b = extrair(vencedor), extrair(perdedor)
        if a != b:
            return (
                f"empate em {_num(vencedor.pontuacao)} pontos, decidido por "
                f"{rotulo} ({_num(a)} × {_num(b)})"
            )

    return "empate em todos os critérios, decidido pela ordem de cadastro"


# ------------------------------------------------------------------ resultado


@dataclass(frozen=True, slots=True)
class Disputa:
    oferta_id: int
    vencedor_id: int
    perdedores_ids: list[int]
    criterio: str


@dataclass(slots=True)
class Resultado:
    atribuicoes: dict[int, int] = field(default_factory=dict)
    """`oferta_id` -> `professor_id`, incluindo as que ja' existiam."""
    novas: dict[int, int] = field(default_factory=dict)
    """Só o que esta sugestao criou."""
    sem_professor: list[int] = field(default_factory=list)
    disputas: list[Disputa] = field(default_factory=list)
    avisos: list[Violacao] = field(default_factory=list)


# -------------------------------------------------------------------- motor


def sugerir_atribuicao(
    estado: GradeState,
    config: ConfigRegras,
    *,
    preservar: dict[int, int] | None = None,
) -> Resultado:
    """Distribui as ofertas sem professor seguindo a regra da unidade.

    `preservar` sao atribuicoes manuais que ficam como estao — a carga delas
    conta para o limite do docente.
    """
    resultado = Resultado(atribuicoes=dict(preservar or {}))
    ordem = classificar(estado, config)

    carga: dict[int, int] = dict.fromkeys(estado.vinculos, 0)
    for oferta_id, professor_id in resultado.atribuicoes.items():
        oferta = estado.ofertas.get(oferta_id)
        if oferta is not None and professor_id in carga:
            carga[professor_id] += estado.disciplina_da(oferta).aulas_semanais

    def limite(professor_id: int) -> int:
        vinculo = estado.vinculos.get(professor_id)
        return vinculo.carga_max(config.carga_max_semanal) if vinculo else 0

    def cabe(professor_id: int, oferta: OfertaInfo) -> bool:
        aulas = estado.disciplina_da(oferta).aulas_semanais
        return carga[professor_id] + aulas <= limite(professor_id)

    def candidatos(oferta: OfertaInfo) -> list[VinculoInfo]:
        """Docentes habilitados, com vinculo e com carga sobrando agora."""
        return [
            v
            for v in ordem
            if estado.habilitacao(v.professor_id, oferta.disciplina_id) is not None
            and cabe(v.professor_id, oferta)
        ]

    def bloqueada_por_paralela(professor_id: int, oferta: OfertaInfo) -> bool:
        """Numa divisao PARALELA, A e B acontecem ao mesmo tempo em salas
        diferentes: precisam de dois docentes. Dar as duas ao mesmo professor
        tornaria a grade impossivel."""
        disciplina = estado.disciplina_da(oferta)
        if oferta.subturma is None or disciplina.modo_divisao != ModoDivisao.PARALELA:
            return False
        return any(
            outra.turma_id == oferta.turma_id
            and outra.disciplina_id == oferta.disciplina_id
            and outra.id != oferta.id
            and resultado.atribuicoes.get(outra.id) == professor_id
            for outra in estado.ofertas.values()
        )

    def vez_de(vinculo: VinculoInfo, apenas: OrigemHabilitacao | None = None) -> None:
        """O docente escolhe tudo que pode, na ordem de prioridade de componente."""
        while True:
            disponiveis = [
                (PRIORIDADE_COMPONENTE[origem], oferta)
                for oferta in estado.ofertas.values()
                if oferta.id not in resultado.atribuicoes
                and (origem := estado.habilitacao(vinculo.professor_id, oferta.disciplina_id))
                is not None
                and (apenas is None or origem == apenas)
                and cabe(vinculo.professor_id, oferta)
                and not bloqueada_por_paralela(vinculo.professor_id, oferta)
            ]
            if not disponiveis:
                return
            # Prioridade do componente primeiro; depois a turma e o id, so' para
            # a sugestao ser reproduzivel.
            _, escolhida = min(disponiveis, key=lambda par: (par[0], par[1].turma_id, par[1].id))
            _atribuir(escolhida, vinculo, manutencao=apenas == OrigemHabilitacao.ANTERIOR)

    def _atribuir(oferta: OfertaInfo, vencedor: VinculoInfo, *, manutencao: bool) -> None:
        concorrentes = [
            v
            for v in candidatos(oferta)
            if v.professor_id != vencedor.professor_id
            and not bloqueada_por_paralela(v.professor_id, oferta)
        ]
        resultado.atribuicoes[oferta.id] = vencedor.professor_id
        resultado.novas[oferta.id] = vencedor.professor_id
        carga[vencedor.professor_id] += estado.disciplina_da(oferta).aulas_semanais

        if concorrentes:
            resultado.disputas.append(
                Disputa(
                    oferta_id=oferta.id,
                    vencedor_id=vencedor.professor_id,
                    perdedores_ids=[v.professor_id for v in concorrentes],
                    criterio=criterio_decisivo(
                        vencedor, concorrentes[0], config, manutencao=manutencao
                    ),
                )
            )

    if config.atribuicao.regra == "ETEC":
        # Passada 1: manutencao das aulas do periodo anterior.
        for vinculo in ordem:
            vez_de(vinculo, apenas=OrigemHabilitacao.ANTERIOR)

    # Passada de ampliacao (Etec) ou passada unica (Fatec).
    for vinculo in ordem:
        vez_de(vinculo)

    resultado.sem_professor = sorted(
        o.id for o in estado.ofertas.values() if o.id not in resultado.atribuicoes
    )
    resultado.avisos = _avisos(estado, config, resultado)
    return resultado


def _avisos(estado: GradeState, config: ConfigRegras, resultado: Resultado) -> list[Violacao]:
    avisos: list[Violacao] = []

    for disputa in resultado.disputas:
        oferta = estado.ofertas[disputa.oferta_id]
        perdedores = ", ".join(estado.nome_professor(pid) for pid in disputa.perdedores_ids)
        # A citacao acompanha o motivo: a manutencao vem da Deliberacao 23/2015,
        # a prioridade por classificacao vem do art. 7 da Portaria 1.263/2017.
        fonte = (
            "" if disputa.criterio == MOTIVO_MANUTENCAO else " (Portaria CETEC 1.263/2017, art. 7º)"
        )
        avisos.append(
            Violacao(
                "PRIORIDADE_NA_ATRIBUICAO",
                Severidade.ALERTA,
                f"{estado.nome_professor(disputa.vencedor_id)} e {perdedores} podiam assumir "
                f"{estado.rotulo_oferta(oferta)}. A prioridade ficou com "
                f"{estado.nome_professor(disputa.vencedor_id)} por {disputa.criterio}"
                f"{fonte}.",
                {
                    "oferta_id": disputa.oferta_id,
                    "vencedor_id": disputa.vencedor_id,
                    "perdedores_ids": disputa.perdedores_ids,
                    "criterio": disputa.criterio,
                },
            )
        )

    for oferta_id in resultado.sem_professor:
        oferta = estado.ofertas[oferta_id]
        disciplina = estado.disciplina_da(oferta)
        habilitados = [
            v
            for v in estado.vinculos.values()
            if estado.habilitacao(v.professor_id, disciplina.id) is not None
        ]
        if not habilitados:
            motivo = "nenhum docente com vínculo nesta unidade está habilitado nela"
        else:
            motivo = f"os {len(habilitados)} docentes habilitados já estão com a carga máxima"
        avisos.append(
            Violacao(
                "OFERTA_SEM_CANDIDATO",
                Severidade.BLOQUEANTE,
                f"{estado.rotulo_oferta(oferta)} ficou sem professor: {motivo}.",
                {"oferta_id": oferta_id, "disciplina_id": disciplina.id},
            )
        )

    return avisos


def ociosidade(estado: GradeState, config: ConfigRegras, resultado: Resultado) -> dict[int, int]:
    """Aulas que ainda cabem na carga de cada docente, depois da atribuicao."""
    usado: dict[int, int] = dict.fromkeys(estado.vinculos, 0)
    for oferta_id, professor_id in resultado.atribuicoes.items():
        if professor_id in usado:
            usado[professor_id] += estado.disciplina_da(estado.ofertas[oferta_id]).aulas_semanais
    return {
        pid: vinculo.carga_max(config.carga_max_semanal) - usado[pid]
        for pid, vinculo in estado.vinculos.items()
    }
