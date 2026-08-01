"""Auditoria do fixture `client`: garante que todo módulo que importa SessionLocal
diretamente está redirecionado para o test_engine, evitando testes de integração
que silenciosamente tocariam o banco real de produção."""

import os

from conftest import TESTS_DIR, testing_session_local as _testing_session_local
from fastapi.testclient import TestClient

# Módulos que importam `SessionLocal` diretamente de app.database (fora de
# session_scope) e por isso PRECISAM ser patchados na fixture `client`.
# `app.database` é a própria fonte da variável, não um "consumidor".
_APP_ROOT = os.path.join(TESTS_DIR, "..", "app")
_KNOWN_PATCHED_MODULES = {
    "app.main",
    "app.services.scheduler_runtime",
    "app.routers.websocket",
}


def _modules_importing_session_local_directly() -> set[str]:
    found: set[str] = set()
    for dirpath, _dirnames, filenames in os.walk(_APP_ROOT):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, filename)
            with open(filepath, encoding="utf-8") as handle:
                source = handle.read()
            if "SessionLocal" not in source:
                continue
            if "SessionLocal = sessionmaker" in source:
                continue  # database.py: definição da variável, não consumo
            rel = os.path.relpath(filepath, os.path.dirname(_APP_ROOT))
            module_name = rel.replace(os.sep, ".").removesuffix(".py")
            found.add(module_name)
    return found


def test_nenhum_modulo_novo_importa_sessionlocal_sem_estar_patchado_no_client() -> None:
    modulos_encontrados = _modules_importing_session_local_directly()

    nao_cobertos = modulos_encontrados - _KNOWN_PATCHED_MODULES
    assert not nao_cobertos, (
        f"Módulo(s) {nao_cobertos} importam SessionLocal diretamente mas não "
        "estão na lista de patches da fixture `client` em conftest.py — "
        "testes de integração usando `client` tocariam o banco real."
    )


def test_todos_os_modulos_conhecidos_usam_test_engine(client: TestClient) -> None:
    del client  # ativa os patches feitos pela fixture `client`
    # pylint: disable=import-outside-toplevel
    import app.database as db
    import app.main as main_module
    import app.routers.websocket as ws
    from app.services import scheduler_runtime as sched

    assert db.SessionLocal is _testing_session_local
    assert getattr(main_module, "SessionLocal") is _testing_session_local
    assert getattr(sched, "SessionLocal") is _testing_session_local
    assert getattr(ws, "SessionLocal") is _testing_session_local
