"""Importação de cadastros por CSV ou Excel."""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app import models as m
from app import schemas as s
from app.api.exportar import XLSX, _sem_acento
from app.crud import HTTP_422, buscar_ou_404
from app.db import SessaoDb
from app.importacao import ErroDeArquivo, ler_tabela
from app.importacao.modelos import MODELOS, Modelo, processar

router = APIRouter(tags=["importar"])

LIMITE_BYTES = 5 * 1024 * 1024
"""Uma planilha de cadastro não passa disso; acima é engano ou ataque."""

HTTP_413 = 413


def _modelo(tipo: str) -> Modelo:
    modelo = MODELOS.get(tipo)
    if modelo is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Não há modelo de importação '{tipo}'. Disponíveis: {', '.join(MODELOS)}.",
        )
    return modelo


@router.get("/importar/modelos", response_model=list[s.ModeloImportacao])
def listar_modelos():
    """O que dá para importar e quais colunas cada planilha tem."""
    return [
        s.ModeloImportacao(
            tipo=modelo.tipo,
            titulo=modelo.titulo,
            descricao=modelo.descricao,
            colunas=[
                s.ColunaModelo(
                    nome=c.nome, ajuda=c.ajuda, exemplo=c.exemplo, obrigatoria=c.obrigatoria
                )
                for c in modelo.colunas
            ],
        )
        for modelo in MODELOS.values()
    ]


@router.get("/importar/modelos/{tipo}/arquivo", summary="Baixar a planilha de exemplo")
def baixar_modelo(tipo: str, formato: str = Query("csv", pattern="^(csv|xlsx)$")):
    """Cabeçalho mais uma linha de exemplo — é o que o usuário preenche."""
    modelo = _modelo(tipo)
    nome = f"modelo-{_sem_acento(modelo.tipo)}.{formato}"

    if formato == "csv":
        buffer = io.StringIO()
        # `;` e BOM: é assim que o Excel em português abre o arquivo com as
        # colunas separadas e os acentos certos, sem passar pelo assistente.
        escritor = csv.writer(buffer, delimiter=";")
        escritor.writerow(modelo.cabecalho())
        escritor.writerow(modelo.exemplo_linha())
        corpo = buffer.getvalue().encode("utf-8-sig")
        tipo_mime = "text/csv; charset=utf-8"
    else:
        from openpyxl import Workbook
        from openpyxl.comments import Comment
        from openpyxl.styles import Font

        livro = Workbook()
        planilha = livro.active
        planilha.title = modelo.titulo[:31]
        planilha.append(modelo.cabecalho())
        planilha.append(modelo.exemplo_linha())
        for i, coluna in enumerate(modelo.colunas, start=1):
            celula = planilha.cell(1, i)
            celula.font = Font(bold=True)
            # A ajuda vira comentário: a planilha se explica sem documentação junto.
            obrigatoria = " (obrigatória)" if coluna.obrigatoria else ""
            celula.comment = Comment(f"{coluna.ajuda}{obrigatoria}", "Horário Inteligente")
            planilha.column_dimensions[celula.column_letter].width = max(14, len(coluna.nome) + 4)
        planilha.freeze_panes = "A2"

        buffer_bin = io.BytesIO()
        livro.save(buffer_bin)
        corpo = buffer_bin.getvalue()
        tipo_mime = XLSX

    return Response(
        corpo,
        media_type=tipo_mime,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post(
    "/importar/csv",
    response_model=s.RelatorioImportacao,
    summary="Importar cadastros de um CSV ou XLSX",
)
async def importar(
    db: SessaoDb,
    unidade_id: int,
    tipo: str,
    arquivo: Annotated[UploadFile, File(description="Arquivo .csv ou .xlsx")],
    aplicar: Annotated[bool, Query(description="Falso apenas confere e não grava nada.")] = False,
):
    """Confere primeiro, grava depois.

    Com `aplicar=false` (o padrão) a importação roda inteira e é desfeita: o
    usuário vê linha por linha o que seria criado, atualizado ou recusado antes
    de mexer no cadastro. Com `aplicar=true` só grava se **nenhuma** linha tiver
    erro — meio cadastro importado é pior que nenhum.
    """
    unidade = buscar_ou_404(db, m.Unidade, unidade_id, "Unidade")
    modelo = _modelo(tipo)

    conteudo = await arquivo.read()
    if len(conteudo) > LIMITE_BYTES:
        raise HTTPException(
            HTTP_413,
            f"O arquivo passa de {LIMITE_BYTES // (1024 * 1024)} MB.",
        )

    try:
        linhas = ler_tabela(arquivo.filename or "", conteudo)
    except ErroDeArquivo as erro:
        raise HTTPException(HTTP_422, str(erro)) from erro

    if not linhas:
        raise HTTPException(
            HTTP_422,
            "O arquivo só tem o cabeçalho; não há nada para importar.",
        )

    faltando = [
        c.nome for c in modelo.colunas if c.obrigatoria and c.nome not in (linhas[0].keys())
    ]
    if faltando:
        raise HTTPException(
            HTTP_422,
            f"Faltam colunas obrigatórias: {', '.join(faltando)}.",
        )

    relatorio = processar(db, unidade, modelo, linhas, aplicar=aplicar)

    if aplicar and not relatorio.tem_erro:
        db.commit()
    else:
        db.rollback()
        relatorio.aplicado = False

    return s.RelatorioImportacao(
        tipo=relatorio.tipo,
        aplicado=relatorio.aplicado,
        total=len(relatorio.linhas),
        resumo=relatorio.resumo,
        linhas=[
            s.LinhaImportacao(
                numero=linha.numero, acao=linha.acao, descricao=linha.descricao, erro=linha.erro
            )
            for linha in relatorio.linhas
        ],
    )
