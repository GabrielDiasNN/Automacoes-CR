"""
Fixtures de teste do Orchestrator Hub Soberano v5.0.

Usa banco SQLite in-memory com StaticPool para isolamento.
Sobrescreve tanto get_db quanto o engine global para que o lifespan funcione.
Patch do PROJECT_ROOT para validacao de script_path (Pilar V) funcionar em testes.
"""

import os
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Setar API KEY antes de importar o app
os.environ["ORCHESTRATOR_API_KEY"] = "hub-secret-token"

from app.database import Base, get_db
from app import models

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Diretorio raiz de testes para validacao de script_path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

AUTH_HEADERS = {"X-API-Key": "hub-secret-token"}


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    # Patch do SessionLocal no main e nos routers para usar o test engine
    import app.database as db_module
    import app.main as main_module
    import app.routers.automations as auto_router

    original_session_local = db_module.SessionLocal
    original_project_root = auto_router.PROJECT_ROOT

    db_module.SessionLocal = TestingSessionLocal
    main_module.SessionLocal = TestingSessionLocal
    # Redirecionar PROJECT_ROOT para o diretorio de testes (contém /test/*.ps1)
    auto_router.PROJECT_ROOT = TESTS_DIR

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    db_module.SessionLocal = original_session_local
    main_module.SessionLocal = original_session_local
    auto_router.PROJECT_ROOT = original_project_root
