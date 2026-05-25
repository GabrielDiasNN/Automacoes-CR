# pylint: disable=all
# mypy: ignore-errors
"""
Fixtures de teste do Orchestrator Central de Automacoes v5.0.

Usa banco SQLite in-memory com StaticPool para isolamento.
Sobrescreve tanto get_db quanto o engine global para que o lifespan funcione.
Patch do PROJECT_ROOT para validacao de script_path (Pilar V) funcionar em testes.
"""

import os

os.environ["ORCHESTRATOR_DB_PATH"] = ":memory:"
os.environ["ORCHESTRATOR_API_KEY"] = "hub-secret-token"
os.environ["RATE_LIMIT_RPM"] = "10000"

import pytest
from app import models
from app.database import Base, get_db
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


@pytest.fixture(autouse=True)
def force_env_vars():
    """Garante que as variaveis de ambiente de teste prevalecam sobre qualquer override de imports."""
    os.environ["ORCHESTRATOR_API_KEY"] = "hub-secret-token"
    os.environ["ORCHESTRATOR_DB_PATH"] = ":memory:"
    os.environ["RATE_LIMIT_RPM"] = "10000"


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
    import app.routers.websocket as websocket_router
    import app.services.scheduler_runtime as scheduler_runtime

    original_session_local = db_module.SessionLocal
    original_engine = db_module.engine
    original_db_path = db_module.DB_PATH
    original_project_root = auto_router.PROJECT_ROOT
    original_scheduler_session = scheduler_runtime.SessionLocal
    original_websocket_session = websocket_router.SessionLocal

    db_module.SessionLocal = TestingSessionLocal
    db_module.engine = test_engine
    db_module.DB_PATH = os.path.join(TESTS_DIR, "test-automacoes.db")
    main_module.SessionLocal = TestingSessionLocal
    scheduler_runtime.SessionLocal = TestingSessionLocal
    websocket_router.SessionLocal = TestingSessionLocal
    # Redirecionar PROJECT_ROOT para o diretorio de testes (contem /test/*.ps1)
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
    db_module.engine = original_engine

    # Excluir fisicamente os arquivos de banco de teste temporarios criados
    for suffix in ["", "-shm", "-wal"]:
        fp = os.path.join(TESTS_DIR, "test-automacoes.db" + suffix)
        if os.path.exists(fp):
            try:
                os.unlink(fp)
            except OSError:
                pass

    db_module.DB_PATH = original_db_path
    main_module.SessionLocal = original_session_local
    auto_router.PROJECT_ROOT = original_project_root
    scheduler_runtime.SessionLocal = original_scheduler_session
    websocket_router.SessionLocal = original_websocket_session
