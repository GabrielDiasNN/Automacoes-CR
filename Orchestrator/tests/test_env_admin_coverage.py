# pylint: disable=protected-access
"""Cobertura do achado nº 11 — `env_admin.sync_global_test_mode_env`.

O corpo do subprocesso (sucesso / `TimeoutExpired` / erro genérico) nunca era
exercitado: a fixture `client` aponta `PROJECT_ROOT` para `tests/test/`, onde
`Tools/ConfigurarEmailTeste.ps1` não existe, então a função retornava cedo
sempre. O `timeout=60s` foi adicionado para impedir que um script travado
prendesse a thread HTTP — removê-lo num refactor não seria detectado.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from app.services import env_admin

_TIMEOUT = env_admin._SYNC_TIMEOUT_SECONDS


def _project_com_script(tmp_path: Path) -> str:
    tools = tmp_path / "Tools"
    tools.mkdir()
    (tools / "ConfigurarEmailTeste.ps1").write_text(
        "param([switch]$Remover)\n", encoding="utf-8"
    )
    return str(tmp_path)


def test_sync_sem_script_retorna_false(tmp_path: Path) -> None:
    assert env_admin.sync_global_test_mode_env(True, str(tmp_path)) is False


def test_sync_sucesso_passa_timeout_e_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capturado: dict[str, Any] = {}

    def fake_run(cmd: Any, **kwargs: Any) -> "subprocess.CompletedProcess[Any]":
        capturado["cmd"] = cmd
        capturado["timeout"] = kwargs.get("timeout")
        capturado["check"] = kwargs.get("check")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("app.services.env_admin.subprocess.run", fake_run)

    assert (
        env_admin.sync_global_test_mode_env(True, _project_com_script(tmp_path)) is True
    )
    assert capturado["timeout"] == _TIMEOUT
    assert capturado["check"] is True
    assert "-Remover" not in capturado["cmd"]


def test_sync_remover_acrescenta_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capturado: dict[str, Any] = {}

    def fake_run(cmd: Any, **_kwargs: Any) -> "subprocess.CompletedProcess[Any]":
        capturado["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("app.services.env_admin.subprocess.run", fake_run)
    env_admin.sync_global_test_mode_env(False, _project_com_script(tmp_path))
    assert "-Remover" in capturado["cmd"]


def test_sync_timeout_retorna_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def estoura(cmd: Any, **_kwargs: Any) -> "subprocess.CompletedProcess[Any]":
        raise subprocess.TimeoutExpired(cmd, _TIMEOUT)

    monkeypatch.setattr("app.services.env_admin.subprocess.run", estoura)
    assert (
        env_admin.sync_global_test_mode_env(True, _project_com_script(tmp_path))
        is False
    )


def test_sync_erro_generico_retorna_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha(cmd: Any, **_kwargs: Any) -> "subprocess.CompletedProcess[Any]":
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("app.services.env_admin.subprocess.run", falha)
    assert (
        env_admin.sync_global_test_mode_env(True, _project_com_script(tmp_path))
        is False
    )
