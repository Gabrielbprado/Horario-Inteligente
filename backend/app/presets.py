"""Presets de regras e modelos de turno por tipo de unidade.

Tudo aqui e' **padrao editavel**, nunca constante de negocio (item 0.2 da spec).
Aplicar um preset grava os valores em `Unidade.config_regras` e cria `ModeloTurno`
com seus `Slot`; a partir dai o usuario edita livremente.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import time

from app.models import ModeloTurno, Slot, TipoUnidade

# ------------------------------------------------------------------- config_regras

CONFIG_REGRAS_BASE: dict = {
    "carga_max_semanal": 29,
    "limite_diario": {
        # CLT art. 318 na redacao antiga. A Lei 13.415/2017 removeu a regra,
        # entao nasce desligado (ver PLANO.md secao 4).
        "ativo": False,
        "max_consecutivas": 4,
        "max_intercaladas": 6,
    },
    "interjornada": {"modo": "aviso", "horas": 11},  # off | aviso | rigida
    "deslocamento_entre_unidades_min": 0,
    "usa_sabado": False,
    "atribuicao": {
        "regra": "FATEC",
        "desempates": ["assiduidade", "titulacao", "tempo_exercicio", "filhos"],
    },
    "pesos": {
        "nao_concentradas": 100_000,
        "janela_turma": 1000,
        "janela_professor": 100,
        "preferencia": 40,
        "dias_professor": 25,
        "estabilidade": 10,
        "dia_curto_no_fim": 5,
    },
    "modo_objetivo": "ponderado",  # ponderado | lexicografico
}

CONFIG_REGRAS_FATEC: dict = {
    "carga_max_semanal": 29,
    "atribuicao": {
        "regra": "FATEC",
        "desempates": ["assiduidade", "titulacao", "tempo_exercicio", "filhos"],
    },
}

CONFIG_REGRAS_ETEC: dict = {
    "carga_max_semanal": 34,
    "atribuicao": {
        "regra": "ETEC",
        "desempates": ["assiduidade", "titulacao", "tempo_exercicio", "filhos"],
    },
}


def config_regras_para(tipo: TipoUnidade) -> dict:
    """Merge raso de um nivel (basta: so `atribuicao` e aninhado e e' substituido inteiro)."""
    cfg = copy.deepcopy(CONFIG_REGRAS_BASE)
    extra = CONFIG_REGRAS_FATEC if tipo == TipoUnidade.FATEC else CONFIG_REGRAS_ETEC
    cfg.update(copy.deepcopy(extra))
    return cfg


# ------------------------------------------------------------------ modelos de turno

Faixa = tuple[str, str]
"""(inicio, fim) em "HH:MM"."""


@dataclass(frozen=True)
class PresetTurno:
    """Um modelo de turno. `dias` mapeia dia_semana -> lista de blocos,
    e cada bloco e' a lista de horas-aula contiguas (sem intervalo) que o compoem."""

    chave: str
    nome: str
    dias: dict[int, list[list[Faixa]]] = field(default_factory=dict)


def _mesmo_em(dias: range | list[int], blocos: list[list[Faixa]]) -> dict[int, list[list[Faixa]]]:
    return {d: blocos for d in dias}


SEG_A_SEX = range(0, 5)

# Fatec noturno: 4 aulas de 50 min em 2 blocos, intervalo 20:40-20:50.
_FATEC_NOITE: list[list[Faixa]] = [
    [("19:00", "19:50"), ("19:50", "20:40")],
    [("20:50", "21:40"), ("21:40", "22:30")],
]

# Sabado de manha em algumas Fatecs (08:00-13:10, intervalo 10:30-10:40).
_FATEC_SABADO: list[list[Faixa]] = [
    [("08:00", "08:50"), ("08:50", "09:40"), ("09:40", "10:30")],
    [("10:40", "11:30"), ("11:30", "12:20"), ("12:20", "13:10")],
]

# Fatec manha: 6 aulas de 50 min, 07:30-12:55, intervalo 10:00-10:25.
_FATEC_MANHA: list[list[Faixa]] = [
    [("07:30", "08:20"), ("08:20", "09:10"), ("09:10", "10:00")],
    [("10:25", "11:15"), ("11:15", "12:05"), ("12:05", "12:55")],
]

# Etec tecnico noturno: 19:00-23:00, intervalo 20:50-21:10 (padrao Etec Sales Gomes).
# 4 aulas de 55 min e' o que fecha exatamente esses horarios publicados.
_ETEC_NOITE: list[list[Faixa]] = [
    [("19:00", "19:55"), ("19:55", "20:50")],
    [("21:10", "22:05"), ("22:05", "23:00")],
]

# Variante usada por outras Etecs: 18:50-22:50.
_ETEC_NOITE_1850: list[list[Faixa]] = [
    [("18:50", "19:45"), ("19:45", "20:40")],
    [("21:00", "21:55"), ("21:55", "22:50")],
]

# ETIM / M-Tec diurno: 6 aulas de 50 min, 07:00-12:20, intervalo 09:30-09:50.
_ETEC_ETIM: list[list[Faixa]] = [
    [("07:00", "07:50"), ("07:50", "08:40"), ("08:40", "09:30")],
    [("09:50", "10:40"), ("10:40", "11:30"), ("11:30", "12:20")],
]


PRESETS_TURNO: dict[str, PresetTurno] = {
    p.chave: p
    for p in [
        PresetTurno(
            "fatec_noturno",
            "Fatec - Noturno (4 aulas em 2 blocos)",
            _mesmo_em(SEG_A_SEX, _FATEC_NOITE),
        ),
        PresetTurno(
            "fatec_noturno_sabado",
            "Fatec - Noturno + Sabado",
            {**_mesmo_em(SEG_A_SEX, _FATEC_NOITE), 5: _FATEC_SABADO},
        ),
        PresetTurno("fatec_manha", "Fatec - Manha", _mesmo_em(SEG_A_SEX, _FATEC_MANHA)),
        PresetTurno(
            "etec_tecnico_noturno",
            "Etec - Tecnico modular noturno",
            _mesmo_em(SEG_A_SEX, _ETEC_NOITE),
        ),
        PresetTurno(
            "etec_tecnico_noturno_1850",
            "Etec - Tecnico modular noturno (18h50)",
            _mesmo_em(SEG_A_SEX, _ETEC_NOITE_1850),
        ),
        PresetTurno("etec_etim", "Etec - ETIM / M-Tec diurno", _mesmo_em(SEG_A_SEX, _ETEC_ETIM)),
    ]
}

PRESETS_POR_TIPO: dict[TipoUnidade, list[str]] = {
    TipoUnidade.FATEC: ["fatec_noturno", "fatec_noturno_sabado", "fatec_manha"],
    TipoUnidade.ETEC: ["etec_tecnico_noturno", "etec_tecnico_noturno_1850", "etec_etim"],
}


def _hhmm(valor: str) -> time:
    h, m = valor.split(":")
    return time(int(h), int(m))


def construir_modelo_turno(preset: PresetTurno, unidade_id: int) -> ModeloTurno:
    """Materializa um preset em `ModeloTurno` + `Slot` (ainda nao persistido)."""
    modelo = ModeloTurno(
        unidade_id=unidade_id,
        nome=preset.nome,
        dias_semana=sorted(preset.dias),
        preset_origem=preset.chave,
    )
    for dia in sorted(preset.dias):
        ordem = 1
        for bloco_id, bloco in enumerate(preset.dias[dia], start=1):
            for inicio, fim in bloco:
                modelo.slots.append(
                    Slot(
                        dia_semana=dia,
                        ordem=ordem,
                        inicio=_hhmm(inicio),
                        fim=_hhmm(fim),
                        bloco_id=bloco_id,
                    )
                )
                ordem += 1
    return modelo


def aplicar_preset_unidade(
    unidade, *, tipo: TipoUnidade | None = None, turnos: list[str] | None = None
) -> None:
    """Aplica em `unidade` (objeto `Unidade` ainda na sessao) as regras e os
    modelos de turno padrao de um tipo (por padrao, o tipo da propria unidade)."""
    tipo = tipo or unidade.tipo
    unidade.config_regras = config_regras_para(tipo)
    unidade.carga_max_semanal_padrao = unidade.config_regras["carga_max_semanal"]
    chaves = turnos if turnos is not None else PRESETS_POR_TIPO[tipo]
    existentes = {m.preset_origem for m in unidade.modelos_turno}
    for chave in chaves:
        if chave in existentes:
            continue
        unidade.modelos_turno.append(construir_modelo_turno(PRESETS_TURNO[chave], unidade.id))
