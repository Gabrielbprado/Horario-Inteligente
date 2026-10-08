"""Leitura de CSV e XLSX para uma lista de dicionários.

Um coordenador exporta a planilha do Excel em português: separador `;`, número
com vírgula decimal e, dependendo da versão, um BOM no começo do arquivo. Nada
disso é exótico o bastante para virar erro de importação.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from typing import Any


class ErroDeArquivo(Exception):
    """O arquivo não dá nem para começar a ler."""


def normalizar_cabecalho(texto: str) -> str:
    """ "Aulas Semanais", "aulas semanais" e "AULAS_SEMANAIS" são a mesma coluna."""
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "_".join(plano.lower().split()).replace("-", "_").strip("_")


def _detectar_separador(amostra: str) -> str:
    """O `;` primeiro: é o que o Excel em português escreve."""
    try:
        return csv.Sniffer().sniff(amostra, delimiters=";,\t").delimiter
    except csv.Error:
        return ";" if amostra.count(";") >= amostra.count(",") else ","


def _ler_csv(conteudo: bytes) -> list[dict[str, Any]]:
    try:
        # utf-8-sig remove o BOM que o Excel escreve; latin-1 é a rede de segurança.
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")

    if not texto.strip():
        raise ErroDeArquivo("O arquivo está vazio.")

    leitor = csv.DictReader(io.StringIO(texto), delimiter=_detectar_separador(texto[:4096]))
    if not leitor.fieldnames:
        raise ErroDeArquivo("O arquivo não tem linha de cabeçalho.")

    colunas = [normalizar_cabecalho(c or "") for c in leitor.fieldnames]

    def registro(linha: dict) -> dict[str, Any]:
        pares = zip(colunas, linha.values(), strict=False)
        return {coluna: (valor or "").strip() for coluna, valor in pares}

    return [registro(linha) for linha in leitor]


def _ler_xlsx(conteudo: bytes) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as erro:  # openpyxl levanta vários tipos para arquivo corrompido
        raise ErroDeArquivo(f"Não foi possível abrir a planilha: {erro}") from erro

    planilha = livro[livro.sheetnames[0]]
    linhas = planilha.iter_rows(values_only=True)
    cabecalho = next(linhas, None)
    if cabecalho is None:
        raise ErroDeArquivo("A primeira aba está vazia.")

    colunas = [normalizar_cabecalho(str(c)) if c is not None else "" for c in cabecalho]
    resultado = []
    for linha in linhas:
        registro = {
            coluna: ("" if valor is None else str(valor).strip())
            for coluna, valor in zip(colunas, linha, strict=False)
            if coluna
        }
        if any(registro.values()):  # a planilha costuma trazer linhas em branco no fim
            resultado.append(registro)
    return resultado


def ler_tabela(nome_arquivo: str, conteudo: bytes) -> list[dict[str, Any]]:
    """Lê CSV ou XLSX; a extensão decide."""
    if nome_arquivo.lower().endswith((".xlsx", ".xlsm")):
        return _ler_xlsx(conteudo)
    if nome_arquivo.lower().endswith((".csv", ".txt")):
        return _ler_csv(conteudo)
    raise ErroDeArquivo(
        f"Formato não suportado em '{nome_arquivo}'. Envie um arquivo .csv ou .xlsx."
    )
