"""Onde a configuracao e' lida — e de onde os testes nao podem ler."""

from pathlib import Path

from app.config import ARQUIVOS_ENV, get_settings

RAIZ = Path(__file__).resolve().parents[2]


def test_env_da_raiz_do_projeto_e_lido_de_qualquer_pasta():
    """O README manda criar o `.env` na raiz, e o Compose le dali. A API roda de
    dentro de `backend/`: com caminho relativo ela procurava `backend/.env`,
    nao achava nada e o chat ficava "desativado" com a chave configurada."""
    assert all(caminho.is_absolute() for caminho in ARQUIVOS_ENV)
    assert ARQUIVOS_ENV[0] == RAIZ / ".env"
    # O de `backend/` vem depois: pydantic-settings deixa o ultimo prevalecer.
    assert ARQUIVOS_ENV[-1] == RAIZ / "backend" / ".env"


def test_os_testes_nao_enxergam_a_chave_do_desenvolvedor():
    """Com uma chave de verdade no `.env`, um teste do chat chamaria a OpenAI
    e gastaria o credito de quem rodou a suite. `tests/__init__.py` zera as
    duas variaveis antes de a aplicacao ser importada."""
    assert get_settings().chat_enabled is False
