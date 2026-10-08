"""Exportação em PDF: uma página por turma (ou professor, ou sala).

ReportLab em vez de WeasyPrint (a spec aceita os dois): é uma dependência Python
pura, sem GTK/Pango para instalar na imagem, e aqui o documento é uma tabela —
não há HTML complexo a aproveitar.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app import schemas as s
from app.export.grade import Quadro, faixa_texto, montar_quadros, rotulo_dia

MARGEM = 12 * mm
CINZA = colors.HexColor("#6B7280")
LINHA = colors.HexColor("#D4D4D8")

_TITULO = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=13, leading=16)
_SUB = ParagraphStyle("sub", fontName="Helvetica", fontSize=9, leading=12, textColor=CINZA)
_RODAPE = ParagraphStyle("rodape", fontName="Helvetica", fontSize=7.5, textColor=CINZA)
_HORARIO = ParagraphStyle("horario", fontName="Helvetica", fontSize=7.5, textColor=CINZA, leading=9)
_DIA = ParagraphStyle("dia", fontName="Helvetica-Bold", fontSize=9, alignment=1)


def _estilo_aula(cor_texto: str) -> tuple[ParagraphStyle, ParagraphStyle]:
    cor = colors.HexColor(cor_texto)
    return (
        ParagraphStyle("sigla", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=cor),
        ParagraphStyle("detalhe", fontName="Helvetica", fontSize=7, leading=8.5, textColor=cor),
    )


def _celula(quadro: Quadro, linha: int, dia: int) -> list:
    aula = quadro.aula(linha, dia)
    if aula is None:
        return []
    sigla, detalhe = _estilo_aula(aula.texto)
    marcas = "".join(m for m, ativo in ((" *", aula.fixada), (" @", aula.remota)) if ativo)
    return [
        Paragraph(f"{aula.sigla}{marcas}", sigla),
        *[Paragraph(texto, detalhe) for texto in aula.linhas],
    ]


def _tabela(quadro: Quadro, largura: float) -> Table:
    topo = [Paragraph("Horário", _HORARIO), *[Paragraph(rotulo_dia(d), _DIA) for d in quadro.dias]]
    dados = [topo]
    for i, (inicio, fim) in enumerate(quadro.faixas):
        dados.append(
            [
                Paragraph(faixa_texto(inicio, fim), _HORARIO),
                *[_celula(quadro, i, d) for d in quadro.dias],
            ]
        )

    coluna_horario = 22 * mm
    largura_dia = (largura - coluna_horario) / len(quadro.dias)
    tabela = Table(
        dados,
        colWidths=[coluna_horario, *[largura_dia] * len(quadro.dias)],
        repeatRows=1,
        hAlign="LEFT",
    )

    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINHA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(len(quadro.faixas)):
        for j, dia in enumerate(quadro.dias, start=1):
            aula = quadro.aula(i, dia)
            if aula is not None:
                estilo.append(("BACKGROUND", (j, i + 1), (j, i + 1), colors.HexColor(aula.fundo)))
    tabela.setStyle(TableStyle(estilo))
    return tabela


def gerar(visao: s.VisaoGrade, cabecalho: str, rodape: str = "") -> bytes:
    """Devolve o PDF pronto, uma página por coluna, em paisagem."""
    buffer = BytesIO()
    largura, altura = landscape(A4)
    documento = BaseDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=MARGEM,
        bottomMargin=MARGEM,
        title=cabecalho,
    )
    quadro_util = Frame(
        MARGEM, MARGEM, largura - 2 * MARGEM, altura - 2 * MARGEM, id="corpo", showBoundary=0
    )

    def numerar(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(CINZA)
        if rodape:
            canvas.drawString(MARGEM, MARGEM / 2, rodape)
        canvas.drawRightString(largura - MARGEM, MARGEM / 2, str(doc.page))
        canvas.restoreState()

    documento.addPageTemplates([PageTemplate(id="padrao", frames=[quadro_util], onPage=numerar)])

    quadros = [q for q in montar_quadros(visao) if not q.vazio]
    historia: list = []
    if not quadros:
        historia = [
            Paragraph(cabecalho, _TITULO),
            Spacer(1, 4),
            Paragraph("Esta grade ainda não tem nenhuma aula alocada.", _SUB),
        ]
    for i, quadro in enumerate(quadros):
        if i:
            historia.append(PageBreak())
        historia.append(Paragraph(quadro.titulo, _TITULO))
        legenda = " · ".join(x for x in (cabecalho, quadro.subtitulo) if x)
        historia.extend([Paragraph(legenda, _SUB), Spacer(1, 6)])
        historia.append(_tabela(quadro, largura - 2 * MARGEM))
        historia.extend([Spacer(1, 5), Paragraph("* aula fixada   @ aula remota", _RODAPE)])

    documento.build(historia)
    return buffer.getvalue()
