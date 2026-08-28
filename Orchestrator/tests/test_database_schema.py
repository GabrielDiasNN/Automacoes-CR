"""Regressoes de integridade de schema do Orchestrator."""

from typing import Any

from app import models as _models  # pylint: disable=unused-import
from app.database import Base, validate_database_schema
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

assert _models  # registra tabelas no Base.metadata antes da validacao de schema

_RUNNING_UNIQUE_INDEX = "ix_execucao_running_unica_por_automacao"


def test_validate_database_schema_passes_for_current_models(
    client: TestClient,  # pylint: disable=unused-argument
) -> None:
    result = validate_database_schema()

    assert result["valid"] is True
    assert not result["missing_tables"]
    assert not result["missing_columns"]
    # Achado nº 1: a validação passou a olhar índices também. Num schema saudável
    # (create_all) nada pode faltar — se este assert quebrar, o comparador está
    # com falso-positivo (nome de índice divergente entre ORM e banco).
    assert not result["missing_indexes"]


def test_validate_database_schema_detecta_indice_ausente(
    client: TestClient,  # pylint: disable=unused-argument
) -> None:
    # Achado nº 1: `validate_database_schema` só comparava colunas, então o
    # índice único parcial da migration 20260731_01 era invisível.
    import app.database as db  # pylint: disable=import-outside-toplevel

    with db.engine.begin() as conn:
        conn.execute(text(f"DROP INDEX IF EXISTS {_RUNNING_UNIQUE_INDEX}"))
    try:
        result = validate_database_schema()
        assert result["valid"] is True  # colunas intactas — não é hard-fail
        assert _RUNNING_UNIQUE_INDEX in result["missing_indexes"]["executions"]
    finally:
        # Recria para não vazar para outros testes (StaticPool + :memory:).
        Base.metadata.create_all(bind=db.engine, checkfirst=True)


def test_run_alembic_migrations_cria_indice_ausente_antes_do_stamp(
    tmp_path: Any, monkeypatch: Any
) -> None:
    # Achado nº 1: um banco legado com todas as colunas mas sem o índice único
    # parcial e sem `alembic_version` era carimbado direto como head — a
    # migration que cria o índice nunca rodava e a invariante "uma RUNNING por
    # automação" sumia do banco em silêncio.
    import app.database as db  # pylint: disable=import-outside-toplevel

    db_file = tmp_path / "legacy.db"
    url = f"sqlite:///{db_file}"
    legacy_engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=legacy_engine)
    with legacy_engine.begin() as conn:
        conn.execute(text(f"DROP INDEX IF EXISTS {_RUNNING_UNIQUE_INDEX}"))
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )

    monkeypatch.setattr(db, "engine", legacy_engine)
    monkeypatch.setattr(db, "SQLALCHEMY_DATABASE_URL", url)

    status = validate_database_schema()
    assert status["valid"] is True
    assert _RUNNING_UNIQUE_INDEX in status["missing_indexes"]["executions"]

    result = db.run_alembic_migrations()

    assert "create_missing_indexes" in result["applied"]
    indices = {ix["name"] for ix in inspect(legacy_engine).get_indexes("executions")}
    assert _RUNNING_UNIQUE_INDEX in indices
    assert not validate_database_schema()["missing_indexes"]
    assert db.get_schema_version() == result["schema_version"]
    legacy_engine.dispose()


def test_run_alembic_migrations_stamp_simples_quando_indices_ok(
    tmp_path: Any, monkeypatch: Any
) -> None:
    # Contraparte: schema legado íntegro (índices inclusos) segue no caminho de
    # stamp puro, sem o passo extra de criação de índices.
    import app.database as db  # pylint: disable=import-outside-toplevel

    db_file = tmp_path / "legacy_ok.db"
    url = f"sqlite:///{db_file}"
    legacy_engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=legacy_engine)
    with legacy_engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )

    monkeypatch.setattr(db, "engine", legacy_engine)
    monkeypatch.setattr(db, "SQLALCHEMY_DATABASE_URL", url)

    result = db.run_alembic_migrations()
    assert result["applied"] == ["alembic_stamp"]
    legacy_engine.dispose()


def test_orm_schema_covers_execution_queue_contract() -> None:
    # Deriva o schema do ORM (mesma fonte que validate_database_schema)
    schema = {
        t_name: {col.name for col in table.columns}
        for t_name, table in Base.metadata.tables.items()
        if t_name != "alembic_version"
    }
    assert {"status", "priority", "started_at"}.issubset(schema["executions"])
    assert {"enabled", "schedule", "script_path"}.issubset(schema["automations"])
    assert {"retry_count", "max_retries", "failure_reason", "recovery_action"}.issubset(
        schema["executions"]
    )
    assert {"queue_group", "cooldown_minutes", "max_retries"}.issubset(
        schema["automations"]
    )


def test_orm_declares_indexes_created_by_migrations() -> None:
    # Regressão do achado #2: índices criados na migration 20260620_01 precisam
    # existir no ORM para o --autogenerate do Alembic não emitir DROP INDEX.
    execution_indexes = {
        index.name for index in Base.metadata.tables["executions"].indexes
    }
    assert {"ix_exec_finished_at", "ix_exec_status_finished"}.issubset(
        execution_indexes
    )
