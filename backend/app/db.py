from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

_connect_args = {}
if _settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(_settings.database_url, connect_args=_connect_args)


def preparar_sqlite(motor) -> None:
    """Ajustes que o SQLite exige e o PostgreSQL já faz sozinho.

    1. `PRAGMA foreign_keys=ON` — o SQLite ignora chave estrangeira por padrão.
    2. Transação explícita. O pysqlite só emite `BEGIN` quando vê um INSERT,
       UPDATE ou DELETE. Um `SAVEPOINT` emitido **antes** do primeiro DML cai
       fora de qualquer transação, e o `ROLLBACK` seguinte não desfaz nada: a
       conferência da importação (`aplicar=false`) gravava de verdade. A receita
       abaixo é a da documentação do SQLAlchemy para pysqlite.
    """

    @event.listens_for(motor, "connect")
    def _pragmas(dbapi_conn, _record):  # pragma: no cover - fiação do driver
        dbapi_conn.isolation_level = None  # desliga o BEGIN implícito do pysqlite
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    @event.listens_for(motor, "begin")
    def _begin(conn):  # pragma: no cover - fiação do driver
        conn.exec_driver_sql("BEGIN")


if _settings.database_url.startswith("sqlite"):
    preparar_sqlite(engine)


# `expire_on_commit` no padrao (True): depois de um commit a sessao reler do
# banco. Com False, um `Oferta` ja' carregado mantinha `atribuicao=None` mesmo
# depois de a atribuicao ter sido gravada, e a leitura seguinte na mesma sessao
# via dado velho.
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SessaoDb = Annotated[Session, Depends(get_db)]
"""Sessao do banco como dependencia. `Annotated` em vez de `Depends()` no default
para nao deixar uma chamada de funcao no argumento padrao."""
