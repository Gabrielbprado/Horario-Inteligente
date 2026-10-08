from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND = Path(__file__).resolve().parents[1]
ARQUIVOS_ENV = (_BACKEND.parent / ".env", _BACKEND / ".env")
"""O `.env` da raiz do projeto (o do README e do Compose) e, por cima dele, um
`backend/.env` opcional. Caminhos absolutos: com `.env` relativo, a API —
que roda de dentro de `backend/` — nunca lia o arquivo da raiz. Arquivo que
nao existe e' ignorado, e variavel de ambiente de verdade vence os dois."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ARQUIVOS_ENV, extra="ignore")

    database_url: str = "sqlite+pysqlite:///./horario.db"
    openai_api_key: str | None = None
    openai_model: str | None = None
    cors_origins: str = "http://localhost:5173"

    @property
    def chat_enabled(self) -> bool:
        return bool(self.openai_api_key and self.openai_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
