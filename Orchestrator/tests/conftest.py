"""
Fixtures de teste do Orchestrator Central de Automacoes v5.0.

Usa banco SQLite in-memory com StaticPool para isolamento.
Sobrescreve tanto get_db quanto o engine global para que o lifespan funcione.
Patch do PROJECT_ROOT para validacao de script_path (Pilar V) funcionar em testes.
"""

import atexit
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

os.environ["ORCHESTRATOR_DB_PATH"] = ":memory:"
os.environ["RATE_LIMIT_RPM"] = "10000"
# `/docs` e `/openapi.json` ficam OFF por padrão em produção (achado de baixa
# severidade); a suíte precisa do schema OpenAPI para os testes de contrato.
os.environ["ORCHESTRATOR_EXPOSE_API_DOCS"] = "1"

# Historico de beneficiamento isolado em arquivo temporario da sessao.
# O banco default (snapshots/beneficiamento_historico.db) nao e versionado,
# entao os contratos precisam de um seed deterministico para rodar no CI.
_BENEF_DB_DIR = tempfile.mkdtemp(prefix="benef-historico-")
os.environ["BENEFICIAMENTO_HISTORICO_DB"] = os.path.join(
    _BENEF_DB_DIR, "beneficiamento_historico.db"
)


@atexit.register
def _remover_temp_beneficiamento() -> None:
    """Remove o temporário da sessão. Sem isto, cada execução da suíte deixava
    um diretório com um SQLite em `%TEMP%` (133 haviam se acumulado).

    Registrado em `atexit`, e não como finalizer de fixture, de propósito: roda
    no ponto mais tardio possível, quando nada mais segura o arquivo, e fora do
    teardown do pytest. `ignore_errors` fecha a última porta — uma falha de
    remoção aqui não pode virar erro de teardown, que é exatamente o problema
    corrigido em [1.3.6] (fixture de sessão estourando no último teste).
    """
    shutil.rmtree(_BENEF_DB_DIR, ignore_errors=True)


# Bootstrap único do pacote `beneficiamento` no sys.path (achado A4 da revisão
# arquitetural). O pytest sempre carrega este conftest antes de coletar qualquer
# teste do diretório, então nenhum módulo de teste precisa repetir o insert.
BENEFICIAMENTO_SRC = (
    Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
)
if BENEFICIAMENTO_SRC.is_dir() and str(BENEFICIAMENTO_SRC) not in sys.path:
    sys.path.insert(0, str(BENEFICIAMENTO_SRC))

import pytest
from _pytest.config import Config
from _pytest.nodes import Item

# Import necessario para registrar as tabelas no Base.metadata.
from app import models  # pylint: disable=unused-import
from app.database import Base, get_db
from app.path_safety import is_contained
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_INTEGRATION_FIXTURES = {"client", "db_session"}


def pytest_collection_modifyitems(config: Config, items: list[Item]) -> None:
    """Marca automaticamente unitario/integracao conforme as fixtures usadas.

    Testes que dependem de client/db_session tocam o SQLite em memoria via
    TestClient (integracao, por definicao em pytest.ini); os demais sao
    unitarios. e2e permanece explicito via @pytest.mark.e2e no proprio teste.
    """
    del config
    for item in items:
        if "e2e" in item.keywords:
            continue
        fixture_names = getattr(item, "fixturenames", [])
        if _INTEGRATION_FIXTURES.intersection(fixture_names):
            item.add_marker(pytest.mark.integracao)
        else:
            item.add_marker(pytest.mark.unitario)


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


testing_session_local = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)

AUTH_HEADERS = {"X-API-Key": TEST_AUTH_VALUE}


@pytest.fixture(scope="session", autouse=True)
def beneficiamento_historico_seed() -> Generator[None, None, None]:
    """Semeia o historico de beneficiamento em banco temporario da sessao.

    Garante dados deterministas (turnos, alternativo 03212, payload bruto)
    para os contratos overview/detail e para o fluxo E2E do dashboard.
    """
    from beneficiamento.historico_db import (  # pylint: disable=import-outside-toplevel
        salvar_historico,
    )

    agora = datetime.now()

    # Codigos de fase reais (Oracle FASES_FLUXO) usados nas fixtures de teste.
    fase_meta = {
        "03 - TINGIMENTO": (40, "TINGIMENTO", "SETOR TINGIMENTO"),
        "05 - ACABAMENTO": (60, "SECADOR", "SETOR ACABAMENTO"),
        "01 - PREPARACAO": (20, "REVISAO MALHA CRUA", "SETOR PREPARACAO"),
    }

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
        confirmada: bool = True,
    ) -> dict[str, Any]:
        codigo_fase, descr_grupo_fase, descr_setor = fase_meta[fase]
        return {
            "NUMERO_OB": ob,
            "SEQ": seq,
            "DATA_FIM": dt.isoformat(),
            "NOME_MAQUINA": maquina,
            "CODIGO_FASE": codigo_fase,
            "DESCR_FASE": fase,
            "DESCR_GRUPO_FASE": descr_grupo_fase,
            "DESCR_SETOR_INDUST": descr_setor,
            "TIPO_MAQUINA": 22,
            "DESCR_TIPO_MAQ": "HIDROEXTRATORA",
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
            "STATUS_FASE": 4 if confirmada else 0,
            "DS_STATUS_FASE": "CONFIRMADA" if confirmada else "PROGRAMADA",
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
        # OB agendada/nao concluida (STATUS_FASE=PROGRAMADA) para cobrir o
        # filtro de status e o indicador planejado_pct.
        _row(
            "900005",
            1,
            agora + timedelta(days=3),
            "1",
            "03 - TINGIMENTO",
            "JET 01",
            "03212",
            0.0,
            0.0,
            confirmada=False,
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
    import app.routers.automation_config as config_router  # pylint: disable=import-outside-toplevel
    import app.routers.automation_ide as ide_router  # pylint: disable=import-outside-toplevel
    import app.routers.automations as auto_router  # pylint: disable=import-outside-toplevel
    import app.routers.websocket as websocket_router  # pylint: disable=import-outside-toplevel
    from app.services import (  # pylint: disable=import-outside-toplevel
        scheduler_runtime,
    )

    original_session_local = db_module.SessionLocal
    original_engine = db_module.engine
    original_db_path = db_module.DB_PATH
    # Os routers de config/IDE têm PROJECT_ROOT próprio desde a extração de
    # services/managed_file_access.py — todos precisam apontar para TESTS_DIR.
    original_project_root = auto_router.PROJECT_ROOT
    original_config_root = config_router.PROJECT_ROOT
    original_ide_root = ide_router.PROJECT_ROOT
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
    config_router.PROJECT_ROOT = TESTS_DIR
    ide_router.PROJECT_ROOT = TESTS_DIR

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    from app.main import app  # pylint: disable=import-outside-toplevel

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        _governar_cadastros(c)
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
    config_router.PROJECT_ROOT = original_config_root
    ide_router.PROJECT_ROOT = original_ide_root
    setattr(scheduler_runtime, "SessionLocal", original_scheduler_session)
    setattr(websocket_router, "SessionLocal", original_websocket_session)


@pytest.fixture
def mock_popen() -> Generator[MagicMock, None, None]:
    """Mock padronizado de subprocess.Popen para testes do worker."""
    with patch("worker.subprocess.Popen") as mock:
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = None
        proc.returncode = 0
        proc.stdout = iter([])
        mock.return_value = proc
        yield mock


@pytest.fixture
def reset_worker_globals() -> Generator[None, None, None]:
    """Reseta o estado global do worker entre testes para evitar vazamento."""
    import worker as _worker_module  # pylint: disable=import-outside-toplevel

    _worker_module.shutdown_event.clear()
    _worker_module.wakeup_event.clear()
    _worker_module.log_buffer.clear()
    _worker_module.stats["tasks_completed"] = 0
    _worker_module.stats["tasks_failed"] = 0
    _worker_module.stats["active_tasks"] = 0
    _worker_module.stats["pool_saturated_seconds"] = 0.0
    _worker_module.stats["active_processes"].clear()
    yield
    _worker_module.shutdown_event.clear()
    _worker_module.wakeup_event.clear()


@pytest.fixture
def mock_requests_worker() -> Generator[dict[str, MagicMock], None, None]:
    """Mock padronizado de requests para o wakeup listener e log flusher."""
    with (
        patch("worker.requests.get") as mock_get,
        patch("worker.requests.post") as mock_post,
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "idle"}
        mock_post.return_value.status_code = 200
        yield {"get": mock_get, "post": mock_post}


@pytest.fixture
def mock_oracle_connection() -> Generator[MagicMock, None, None]:
    """Mock padronizado para oracledb.connect. Retorna cursor vazio por padrão."""
    with patch("oracledb.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.description = []
        mock_cursor.fetchmany.return_value = []
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value.cursor.return_value = mock_cursor
        yield mock_conn


# ---------------------------------------------------------------------------
# Manifesto canônico exigido pelo preflight
# ---------------------------------------------------------------------------
# Desde 31/07/2026 a ausência de `automation.manifest.json` é BLOQUEANTE em
# `create`/`update`. As fixtures que cadastram automações sintéticas precisam,
# portanto, de um manifesto coerente com o payload — os campos são comparados
# um a um por `_manifest_field_mismatches`.

# Caminhos escritos pelo helper, registrados para o teardown. A pasta é
# derivada do `script_path` do payload contra o `PROJECT_ROOT` vigente no
# router — que alguns testes monkeypatcham para um `tmp_path` próprio.
_ARQUIVOS_DE_GOVERNANCA_ESCRITOS: list[str] = []

# Interruptor do wrapper. Testes que verificam o BLOQUEIO por manifesto ausente
# precisam do `client` cru — ver a fixture `sem_governanca_automatica`.
_GOVERNANCA_AUTOMATICA = [True]


def com_manifesto(payload: dict[str, Any]) -> dict[str, Any]:
    """Escreve o manifesto que torna `payload` governado e devolve o payload.

    Uso: `client.post("/api/automations", json=com_manifesto({...}))`.

    O arquivo vive em `tests/test/` (o `PROJECT_ROOT` dos testes) e é removido
    ao fim de cada teste pela fixture autouse `_limpar_manifesto_de_teste`.
    """
    import app.routers.automations as auto_router  # pylint: disable=import-outside-toplevel

    script_path = str(payload.get("script_path") or "./test/run.ps1")
    pasta = os.path.join(
        auto_router.PROJECT_ROOT, os.path.dirname(script_path.lstrip("./\\"))
    )
    manifesto_path = os.path.join(pasta, "automation.manifest.json")
    whatsapp_path = os.path.join(pasta, "whatsapp-config.json")
    doc_path = script_path.lstrip("./\\").replace("\\", "/")

    # Payload de escape de path é cenário legítimo de teste; o helper não pode
    # tentar escrever fora da raiz por causa dele.
    if not is_contained(auto_router.PROJECT_ROOT, pasta):
        return payload
    canais = [
        canal.strip()
        for canal in str(payload.get("notification_channels") or "").split(",")
        if canal.strip()
    ]
    manifesto = {
        "id": "TST-99",
        "name": str(payload.get("name") or "").strip(),
        "slug": "fixture-de-teste",
        "criticality": "low",
        "owner_area": "QA",
        "entrypoint": os.path.basename(script_path),
        "runtime": "powershell",
        "channels": sorted(set(canais)),
        "queue_group": payload.get("queue_group") or None,
        "sla_minutes": payload.get("sla_minutes") or None,
        # O preflight compara contra o payload já validado pelo schema, com os
        # defaults aplicados (`max_runtime_minutes = 30`) — não contra o corpo
        # cru da requisição.
        "max_runtime_minutes": int(payload.get("max_runtime_minutes") or 30),
        "max_retries": int(payload.get("max_retries") or 0),
        "schedule_summary": "Manual",
        # Os três caminhos de documentação apontam para o próprio entrypoint.
        # `_manifest_docs_issues` só checa existência, e o entrypoint sabidamente
        # existe em qualquer raiz — inclusive nos `tmp_path` que alguns testes
        # montam. Assim o helper não cria nem sobrescreve arquivo nenhum na
        # pasta de fixtures. Quem cobre docs ausentes é o teste de governança
        # dedicado, que monta o cenário à mão.
        "runbook_path": doc_path,
        "context_path": doc_path,
        "readme_path": doc_path,
        "orchestrator": {"script_path": script_path},
        "dependencies": {"oracle": False, "outlook": False, "whatsapp": False},
        "smoke_tests": [],
    }
    if not os.path.isdir(pasta):
        return payload
    # Um manifesto que o wrapper não escreveu é cenário deliberado do teste
    # (drift de campo, whatsapp-config inválido) e não pode ser desfeito. Os
    # que ele mesmo escreveu são reescritos a cada cadastro, porque um teste
    # pode registrar várias automações na mesma pasta com payloads diferentes.
    if (
        os.path.isfile(manifesto_path)
        and manifesto_path not in _ARQUIVOS_DE_GOVERNANCA_ESCRITOS
    ):
        return payload
    if manifesto_path not in _ARQUIVOS_DE_GOVERNANCA_ESCRITOS:
        _ARQUIVOS_DE_GOVERNANCA_ESCRITOS.append(manifesto_path)
    with open(manifesto_path, "w", encoding="utf-8") as arquivo:
        json.dump(manifesto, arquivo, ensure_ascii=False, indent=2)

    # Declarar o canal whatsapp obriga a existência de `whatsapp-config.json`
    # na pasta da automação, com clientId e destinatário válidos.
    if "whatsapp" in canais:
        if whatsapp_path not in _ARQUIVOS_DE_GOVERNANCA_ESCRITOS:
            _ARQUIVOS_DE_GOVERNANCA_ESCRITOS.append(whatsapp_path)
        with open(whatsapp_path, "w", encoding="utf-8") as arquivo:
            json.dump(
                {
                    "auth": {"clientId": "fixture-qa"},
                    # Destinatário sintético: número inexistente, nunca um
                    # contato real. O arquivo é gitignored e removido no
                    # teardown de cada teste.
                    "target": {"type": "contact", "contactId": "000000000000@c.us"},
                },
                arquivo,
            )
    return payload


def _governar_cadastros(cliente: TestClient) -> None:
    """Faz o `client` de teste cadastrar automações governadas.

    O preflight passou a EXIGIR `automation.manifest.json` (31/07/2026). As
    dezoito fixtures que registram automações sintéticas não existem para
    exercitar governança — existem para exercitar CRUD, execuções e filtros —
    e enchê-las de bookkeeping de manifesto só afastaria cada teste do que ele
    de fato verifica.

    Este wrapper escreve, antes de cada `POST`/`PATCH` em `/api/automations`, o
    manifesto coerente com o payload. Quem verifica o bloqueio em si é
    `test_manifesto_obrigatorio.py`, com requisição direta e sem o wrapper.

    `PATCH /api/automations/{id}` (achado #19: verbo corrigido de PUT, que
    tinha semântica de update parcial) é o único consumidor real do ramo de
    update deste wrapper — mantido também em `put` por segurança, caso algum
    outro endpoint em `/api/automations` volte a usar PUT no futuro.
    """
    original_post = cliente.post
    original_put = cliente.put
    original_patch = cliente.patch

    def _preparar(url: str, kwargs: dict[str, Any], *, atual: Any = None) -> None:
        if not _GOVERNANCA_AUTOMATICA[0] or not url.startswith("/api/automations"):
            return
        payload = kwargs.get("json")
        if not isinstance(payload, dict):
            return
        # `PATCH` é parcial: o preflight avalia o registro já persistido com o
        # patch aplicado por cima, então o manifesto precisa espelhar a fusão,
        # não só os campos enviados.
        efetivo = {**atual, **payload} if isinstance(atual, dict) else payload
        if efetivo.get("script_path"):
            com_manifesto(efetivo)

    def post(url: str, **kwargs: Any) -> Any:
        _preparar(url, kwargs)
        return original_post(url, **kwargs)

    def _buscar_atual(url: str, kwargs: dict[str, Any]) -> Any:
        if not url.startswith("/api/automations/"):
            return None
        resposta = cliente.get(url, headers=kwargs.get("headers"))
        return resposta.json() if resposta.status_code == 200 else None

    def put(url: str, **kwargs: Any) -> Any:
        _preparar(url, kwargs, atual=_buscar_atual(url, kwargs))
        return original_put(url, **kwargs)

    def patch_request(url: str, **kwargs: Any) -> Any:
        _preparar(url, kwargs, atual=_buscar_atual(url, kwargs))
        return original_patch(url, **kwargs)

    setattr(cliente, "post", post)
    setattr(cliente, "put", put)
    setattr(cliente, "patch", patch_request)


@pytest.fixture(autouse=True)
def _limpar_manifesto_de_teste() -> Generator[None, None, None]:
    """Impede que o manifesto de um teste vaze para o seguinte."""
    yield
    for caminho in _ARQUIVOS_DE_GOVERNANCA_ESCRITOS:
        if os.path.isfile(caminho):
            os.remove(caminho)
    _ARQUIVOS_DE_GOVERNANCA_ESCRITOS.clear()


@pytest.fixture
def sem_governanca_automatica() -> Generator[None, None, None]:
    """Desliga o wrapper de manifesto para este teste.

    Necessário para verificar o próprio bloqueio: com o wrapper ativo, o
    cadastro sem manifesto nunca chega ao preflight sem um.
    """
    _GOVERNANCA_AUTOMATICA[0] = False
    yield
    _GOVERNANCA_AUTOMATICA[0] = True
