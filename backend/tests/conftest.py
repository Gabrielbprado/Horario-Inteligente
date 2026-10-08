import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db, preparar_sqlite
from app.main import create_app
from app.models import Base


@pytest.fixture
def engine():
    # StaticPool: o TestClient roda a aplicacao em outra thread, e sem uma unica
    # conexao compartilhada cada thread abriria um banco em memoria vazio.
    motor = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # O mesmo tratamento do motor de verdade: sem ele o SAVEPOINT nao isola e o
    # teste passa por um motivo que a aplicacao nao tem.
    preparar_sqlite(motor)
    Base.metadata.create_all(motor)
    try:
        yield motor
    finally:
        motor.dispose()


@pytest.fixture
def db(engine) -> Session:
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def escopo_seed(db):
    """Banco com o seed completo da secao 9 da spec."""
    from scripts.seed import seed

    return seed(db)


@pytest.fixture
def cliente(db, engine, monkeypatch) -> TestClient:
    """API ligada ao mesmo banco em memoria do fixture `db`.

    A sessao nao e' fechada pela dependencia: o teste continua usando `db` depois
    da requisicao para conferir o que foi gravado.
    """
    # O job do solver roda fora da requisicao e abre a propria sessao; sem esta
    # troca ele iria para o banco de desenvolvimento em vez do de teste.
    from app.scheduling import jobs

    monkeypatch.setattr(jobs, "fabrica_de_sessao", sessionmaker(bind=engine, autoflush=False))
    # O registro de jobs e' global e vive no processo; cada teste tem o seu
    # banco, e ids de grade se repetem entre eles.
    monkeypatch.setattr(jobs, "REGISTRO", jobs._Registro())

    from app.chat import propostas

    monkeypatch.setattr(propostas, "REGISTRO", propostas._Registro())

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
