"""Conversão de célula de planilha para valor do domínio.

Cada erro aqui vira uma linha do relatório em vez de um 500: quem importa 300
professores precisa saber **qual** linha está errada e por quê, não que "a
importação falhou".
"""

from __future__ import annotations

import enum
import unicodedata

SIM = {"sim", "s", "1", "true", "verdadeiro", "x", "v"}
NAO = {"nao", "n", "0", "false", "falso", ""}


class ValorInvalido(Exception):
    """Mensagem já pronta para o relatório."""


def _sem_acento(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return plano.strip().lower()


def texto(valor: str, coluna: str, *, obrigatorio: bool = True, maximo: int = 200) -> str:
    limpo = (valor or "").strip()
    if not limpo and obrigatorio:
        raise ValorInvalido(f"A coluna '{coluna}' é obrigatória.")
    if len(limpo) > maximo:
        raise ValorInvalido(f"'{coluna}' passa de {maximo} caracteres.")
    return limpo


def inteiro(valor: str, coluna: str, *, padrao: int | None = None, minimo: int = 0) -> int | None:
    limpo = (valor or "").strip()
    if not limpo:
        return padrao
    try:
        numero = int(float(limpo.replace(",", ".")))
    except ValueError as erro:
        raise ValorInvalido(f"'{coluna}' deveria ser um número inteiro, veio '{valor}'.") from erro
    if numero < minimo:
        raise ValorInvalido(f"'{coluna}' não pode ser menor que {minimo}.")
    return numero


def decimal(valor: str, coluna: str, *, padrao: float = 0.0) -> float:
    """Aceita a vírgula decimal: 87,5 é como a pontuação é publicada."""
    limpo = (valor or "").strip().replace(".", "").replace(",", ".") if "," in valor else valor
    if not (limpo or "").strip():
        return padrao
    try:
        return float(limpo)
    except ValueError as erro:
        raise ValorInvalido(f"'{coluna}' deveria ser um número, veio '{valor}'.") from erro


def booleano(valor: str, coluna: str, *, padrao: bool = False) -> bool:
    limpo = _sem_acento(valor or "")
    if not limpo:
        return padrao
    if limpo in SIM:
        return True
    if limpo in NAO:
        return False
    raise ValorInvalido(f"'{coluna}' aceita sim ou não, veio '{valor}'.")


def opcao[E: enum.StrEnum](valor: str, coluna: str, tipo: type[E], *, padrao: E | None = None) -> E:
    """Aceita o nome do enum sem se importar com acento, caixa ou espaço."""
    limpo = _sem_acento(valor or "").replace(" ", "_").replace("-", "_")
    if not limpo:
        if padrao is None:
            raise ValorInvalido(f"A coluna '{coluna}' é obrigatória.")
        return padrao
    for membro in tipo:
        if _sem_acento(membro.value).replace(" ", "_") == limpo:
            return membro
    aceitos = ", ".join(m.value for m in tipo)
    raise ValorInvalido(f"'{coluna}' veio '{valor}'; os valores aceitos são: {aceitos}.")
