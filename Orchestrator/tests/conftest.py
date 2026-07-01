"""
Fixtures de teste do Orchestrator Central de Automacoes v5.0.

Usa banco SQLite in-memory com StaticPool para isolamento.
Sobrescreve tanto get_db quanto o engine global para que o lifespan funcione.
Patch do PROJECT_ROOT para validacao de script_path (Pilar V) funcionar em testes.
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

os.environ["ORCHESTRATOR_DB_PATH"] = ":memory:"
os.environ["RATE_LIMIT_RPM"] = "10000"

# Historico de beneficiamento isolado em arquivo temporario da sessao.
# O banco default (snapshots/beneficiamento_historico.db) nao e versionado,
# entao os contratos precisam de um seed deterministico para rodar no CI.
_BENEF_DB_DIR = tempfile.mkdtemp(prefix="benef-historico-")
os.environ["BENEFICIAMENTO_HISTORICO_DB"] = os.path.join(
    _BENEF_DB_DIR, "beneficiamento_historico.db"
)

import pytest
from app import models  # pylint: disable=unused-import  # registra tabelas no Base.metadata
from app.database import Base, get_db
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
TEST_AUTH_VALUE = "fixture-qa-001"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Diretorio raiz de testes para validacao de script_path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

AUTH_HEADERS = {"X-API-Key": TEST_AUTH_VALUE}


@pytest.fixture(scope="session", autouse=True)
def beneficiamento_historico_seed() -> Generator[None, None, None]:
    """Semeia o historico de beneficiamento em banco temporario da sessao.

    Garante dados deterministas (turnos, alternativo 03212, payload bruto)
    para os contratos overview/detail e para o fluxo E2E do dashboard.
    """
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento.historico_db import (  # pylint: disable=import-outside-toplevel
        salvar_historico,
    )

    agora = datetime.now()

    def _row(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        ob: str,
        seq: int,
        dt: datetime,
        turno: str,
        fase: str,
        maquina: str,
        alternativo: str,
        kg: float,
        mt: float,
    ) -> dict[str, Any]:
        return {
            "NUMERO_OB": ob,
            "SEQ": seq,
            "DATA_FIM": dt.isoformat(),
            "NOME_MAQUINA": maquina,
            "CD_DS_FASE": fase,
            "CODIGO_ALTERNATIVO": alternativo,
            "REDUZ": alternativo,
            "DESCR_ITEM": f"Produto {alternativo}",
            "ARTIGO": "ART-FIXTURE",
            "DESCR_ARTIGO": "Artigo fixture",
            "COR": "AZUL",
            "DESCR_COR": "Azul",
            "QT_KG": kg,
            "QT_MT": mt,
            "MIN_REAL": 12.0,
            "MIN_PREV": 10.0,
            "TURNO_PROD": turno,
            "TURNO_DESC": f"TURNO {turno}",
            "OPERADOR_FINAL": "QA FIXTURE",
            "REPROCESSO": 0,
        }

    registros = [
        _row(
            "900001",
            1,
            agora - timedelta(hours=2),
            "1",
            "03 - TINGIMENTO",
            "JET 01",
            "03212",
            120.5,
            300.0,
        ),
        _row(
            "900001",
            2,
            agora - timedelta(hours=1),
            "2",
            "05 - ACABAMENTO",
            "RAMA 02",
            "03212",
            118.0,
            295.0,
        ),
        _row(
            "900002",
            1,
            agora - timedelta(days=1, hours=3),
            "3",
            "01 - PREPARACAO",
            "PREPARADORA 01",
            "04500",
            80.0,
            200.0,
        ),
        _row(
            "900003",
            1,
            agora - timedelta(days=2, hours=5),
            "1",
            "03 - TINGIMENTO",
            "JET 02",
            "05100",
            95.0,
            240.0,
        ),
        # Alternativo 02414: usado pelo fluxo E2E do dashboard (filtro de produto).
        _row(
            "900004",
            1,
            agora - timedelta(hours=4),
            "1",
            "03 - TINGIMENTO",
            "JET 03",
            "02414",
            150.0,
            360.0,
        ),
        _row(
            "900004",
            2,
            agora - timedelta(hours=3),
            "2",
            "05 - ACABAMENTO",
            "RAMA 01",
            "02414",
            148.0,
            355.0,
        ),
    ]
    salvar_historico(registros, db_path=os.environ["BENEFICIAMENTO_HISTORICO_DB"])
    yield


@pytest.fixture(autouse=True)
def force_env_vars() -> None:
    """Garante que as variaveis de ambiente de teste prevalecam sobre qualquer override de imports."""
    os.environ["ORCHESTRATOR_API_KEY"] = TEST_AUTH_VALUE
    os.environ["ORCHESTRATOR_DB_PATH"] = ":memory:"
    os.environ["RATE_LIMIT_RPM"] = "10000"


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=test_engine)
    session = testing_session_local()
    yield session
    session.close()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
# pylint: disable=too-many-locals,redefined-outer-name
# (db_session e o nome exigido pelo pytest para injetar a fixture homonima)
def client(db_session: Session) -> Generator[TestClient, None, None]:
    # Patch do SessionLocal no main e nos routers para usar o test engine
    import app.database as db_module  # pylint: disable=import-outside-toplevel
    import app.main as main_module  # pylint: disable=import-outside-toplevel
    import app.routers.automations as auto_router  # pylint: disable=import-outside-toplevel
    import app.routers.websocket as websocket_router  # pylint: disable=import-outside-toplevel
    from app.services import (  # pylint: disable=import-outside-toplevel
        scheduler_runtime,
    )

    original_session_local = db_module.SessionLocal
    original_engine = db_module.engine
    original_db_path = db_module.DB_PATH
    original_project_root = auto_router.PROJECT_ROOT
    original_scheduler_session = getattr(scheduler_runtime, "SessionLocal")
    original_websocket_session = getattr(websocket_router, "SessionLocal")

    db_module.SessionLocal = testing_session_local
    db_module.engine = test_engine
    db_module.DB_PATH = os.path.join(TESTS_DIR, "test-automacoes.db")
    setattr(main_module, "SessionLocal", testing_session_local)
    setattr(scheduler_runtime, "SessionLocal", testing_session_local)
    setattr(websocket_router, "SessionLocal", testing_session_local)
    # Redirecionar PROJECT_ROOT para o diretorio de testes (contem /test/*.ps1)
    auto_router.PROJECT_ROOT = TESTS_DIR

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    from app.main import app  # pylint: disable=import-outside-toplevel

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
    setattr(main_module, "SessionLocal", original_session_local)
    auto_router.PROJECT_ROOT = original_project_root
    setattr(scheduler_runtime, "SessionLocal", original_scheduler_session)
    setattr(websocket_router, "SessionLocal", original_websocket_session)
