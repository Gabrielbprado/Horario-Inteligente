"""Roda antes do `conftest` e de qualquer import da aplicacao.

Variavel de ambiente vence o `.env`: zerar as duas aqui garante que a suite
nunca enxerga a chave da OpenAI de quem a esta rodando. Sem isto, com uma chave
de verdade no `.env`, `test_chat` chamaria a API real e gastaria credito.
"""

import os

os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_MODEL"] = ""
