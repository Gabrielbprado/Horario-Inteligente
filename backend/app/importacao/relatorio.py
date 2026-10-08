"""O que a importação faria, linha por linha."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Acao = Literal["criar", "atualizar", "ignorar", "erro"]


@dataclass(slots=True)
class LinhaRelatorio:
    numero: int
    """Linha da planilha como o usuário a vê — 1 é o cabeçalho."""
    acao: Acao
    descricao: str
    erro: str | None = None


@dataclass(slots=True)
class Relatorio:
    tipo: str
    aplicado: bool
    linhas: list[LinhaRelatorio] = field(default_factory=list)

    def registrar(self, numero: int, acao: Acao, descricao: str, erro: str | None = None) -> None:
        self.linhas.append(LinhaRelatorio(numero, acao, descricao, erro))

    def contar(self, acao: Acao) -> int:
        return sum(1 for linha in self.linhas if linha.acao == acao)

    @property
    def tem_erro(self) -> bool:
        return any(linha.acao == "erro" for linha in self.linhas)

    @property
    def resumo(self) -> dict[str, int]:
        return {acao: self.contar(acao) for acao in ("criar", "atualizar", "ignorar", "erro")}
