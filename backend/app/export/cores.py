"""A mesma cor de disciplina que a tela usa, em hexadecimal.

A tela calcula o matiz em `frontend/src/lib/cores.ts` e deixa luminosidade e
croma fixos no CSS (`.disciplina`). O PDF e a planilha repetem as duas contas em
Python: uma aula exportada precisa ter a cor que o coordenador viu na tela, e
qualquer aproximação ("um azul parecido") quebra isso de um jeito que ninguém
percebe até comparar os dois papéis lado a lado.

Duas implementações da mesma regra é o preço; `tests/test_export.py` fixa os
valores para as duas não andarem separadas.
"""

from __future__ import annotations

import math

MATIZES = 16
PASSO = 360 / MATIZES
OFFSET = 18
"""Desloca a roda para não começar no vermelho puro, reservado a erros."""

# Tema claro: exportado é papel. Os três valores vêm de `.disciplina` no index.css.
FUNDO = (0.94, 0.055)
BORDA = (0.84, 0.09)
TEXTO = (0.4, 0.13)


def _int32(n: int) -> int:
    """JavaScript faz operação de bit em inteiro de 32 bits com sinal."""
    n &= 0xFFFFFFFF
    return n - 0x100000000 if n >= 0x80000000 else n


def hash_fnv(texto: str) -> int:
    """FNV-1a como o `Math.imul` do JS faz — inclusive o estouro de 32 bits."""
    h = _int32(2166136261)
    for caractere in texto:
        h = _int32(h ^ ord(caractere))
        h = _int32(h * 16777619)
    return abs(h)


def matiz(chave: str | int) -> float:
    """Matiz quantizado: duas disciplinas ou têm a mesma cor, ou distam 22,5°."""
    return (OFFSET + (hash_fnv(str(chave)) % MATIZES) * PASSO) % 360


def oklch_hex(luminosidade: float, croma: float, matiz_graus: float) -> str:
    """OKLCH -> sRGB, a mesma conversão que o navegador faz para `oklch()`."""
    rad = math.radians(matiz_graus)
    a = croma * math.cos(rad)
    b = croma * math.sin(rad)

    l_ = luminosidade + 0.3963377774 * a + 0.2158037573 * b
    m_ = luminosidade - 0.1055613458 * a - 0.0638541728 * b
    s_ = luminosidade - 0.0894841775 * a - 1.2914855480 * b
    ll, mm, ss = l_**3, m_**3, s_**3

    linear = (
        +4.0767416621 * ll - 3.3077115913 * mm + 0.2309699292 * ss,
        -1.2684380046 * ll + 2.6097574011 * mm - 0.3413193965 * ss,
        -0.0041960863 * ll - 0.7034186147 * mm + 1.7076147010 * ss,
    )
    return "#" + "".join(f"{round(_gama(c) * 255):02X}" for c in linear)


def _gama(canal: float) -> float:
    canal = min(1.0, max(0.0, canal))
    if canal <= 0.0031308:
        return 12.92 * canal
    return 1.055 * canal ** (1 / 2.4) - 0.055


def cores_disciplina(sigla: str) -> tuple[str, str, str]:
    """Fundo, borda e texto de uma disciplina, em hexadecimal."""
    h = matiz(sigla)
    return (
        oklch_hex(*FUNDO, h),
        oklch_hex(*BORDA, h),
        oklch_hex(*TEXTO, h),
    )
