"""Comparação entre duas versões da mesma grade.

Função pura sobre dois `GradeState`: a tela de versões, o histórico e qualquer
relatório futuro leem daqui. A unidade de comparação é o **bloco** — o mesmo que
o usuário arrasta e o solver posiciona —, não a hora-aula: mover um bloco de
duas aulas é uma mudança, não duas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.scheduling.domain import GradeState

TipoDiferenca = Literal["igual", "horario", "espaco", "professor", "removida", "adicionada"]

ROTULO = {
    "igual": "sem mudança",
    "horario": "mudou de horário",
    "espaco": "mudou de sala",
    "professor": "mudou de professor",
    "removida": "só na primeira",
    "adicionada": "só na segunda",
}


@dataclass(frozen=True, slots=True)
class Posicao:
    """Onde um bloco está: quando, onde e com quem."""

    slot_id: int
    espaco_id: int | None
    professor_id: int

    def rotulo(self, estado: GradeState) -> str:
        slot = estado.slots.get(self.slot_id)
        espaco = estado.espacos.get(self.espaco_id) if self.espaco_id else None
        partes = [
            slot.rotulo if slot else f"horário {self.slot_id}",
            espaco.nome if espaco else "sem sala",
            estado.nome_professor(self.professor_id),
        ]
        return " · ".join(partes)


@dataclass(slots=True)
class Diferenca:
    tipo: TipoDiferenca
    oferta_id: int
    bloco_idx: int
    rotulo: str
    """Identificação legível do bloco: "BD (TDS Módulo I)"."""
    antes: str | None
    depois: str | None


def _posicoes(estado: GradeState) -> dict[tuple[int, int], Posicao]:
    """Primeira hora-aula de cada bloco. As demais a acompanham por construção."""
    inicio: dict[tuple[int, int], tuple[int, Posicao]] = {}
    for alocacao in estado.alocacoes:
        slot = estado.slots.get(alocacao.slot_id)
        if slot is None:
            continue
        chave = (alocacao.oferta_id, alocacao.bloco_idx)
        ordenacao = (slot.dia, slot.ordem)
        atual = inicio.get(chave)
        if atual is None or ordenacao < atual[0]:
            inicio[chave] = (
                ordenacao,
                Posicao(alocacao.slot_id, alocacao.espaco_id, alocacao.professor_id),
            )
    return {chave: posicao for chave, (_, posicao) in inicio.items()}


def _classificar(antes: Posicao, depois: Posicao) -> TipoDiferenca:
    """Uma mudança de cada vez, na ordem em que interessa a quem lê: o horário
    é o que reorganiza a vida das pessoas; a sala é logística; o professor
    raramente muda entre versões da mesma grade."""
    if antes.slot_id != depois.slot_id:
        return "horario"
    if antes.espaco_id != depois.espaco_id:
        return "espaco"
    if antes.professor_id != depois.professor_id:
        return "professor"
    return "igual"


def comparar(primeira: GradeState, segunda: GradeState) -> list[Diferenca]:
    """Diferenças entre as duas versões, as mudanças primeiro.

    Os rótulos saem do catálogo da **primeira** quando o bloco existe nela; as
    duas grades são da mesma unidade, então o catálogo é o mesmo.
    """
    a, b = _posicoes(primeira), _posicoes(segunda)

    diferencas = []
    for chave in sorted(a.keys() | b.keys()):
        oferta_id, bloco_idx = chave
        antes, depois = a.get(chave), b.get(chave)
        estado = primeira if oferta_id in primeira.ofertas else segunda
        oferta = estado.ofertas.get(oferta_id)
        rotulo = estado.rotulo_oferta(oferta) if oferta else f"oferta {oferta_id}"
        if bloco_idx:
            rotulo = f"{rotulo} · bloco {bloco_idx + 1}"

        if antes is None or depois is None:
            tipo: TipoDiferenca = "removida" if depois is None else "adicionada"
        else:
            tipo = _classificar(antes, depois)

        diferencas.append(
            Diferenca(
                tipo=tipo,
                oferta_id=oferta_id,
                bloco_idx=bloco_idx,
                rotulo=rotulo,
                antes=antes.rotulo(primeira) if antes else None,
                depois=depois.rotulo(segunda) if depois else None,
            )
        )

    # As iguais vão para o fim: quem abre a comparação quer ver o que mudou.
    return sorted(diferencas, key=lambda d: (d.tipo == "igual", d.rotulo))


def resumo(diferencas: list[Diferenca]) -> dict[str, int]:
    contagem = dict.fromkeys(ROTULO, 0)
    for diferenca in diferencas:
        contagem[diferenca.tipo] += 1
    return contagem
