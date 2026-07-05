"""Testes unitários de app/services/beneficiamento_refresh.py."""

import logging
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock, patch

from app.services import beneficiamento_refresh as br

# ---------------------------------------------------------------------------
# _runner_python
# ---------------------------------------------------------------------------


def test_runner_python_sem_env_var_retorna_sys_executable(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("BENEFICIAMENTO_PYTHON", raising=False)
    assert br._runner_python() == sys.executable  # pylint: disable=protected-access


def test_runner_python_com_env_var_retorna_valor_dela(monkeypatch: Any) -> None:
    monkeypatch.setenv("BENEFICIAMENTO_PYTHON", "C:\\custom\\python.exe")
    assert (
        br._runner_python()  # pylint: disable=protected-access
        == "C:\\custom\\python.exe"
    )


# ---------------------------------------------------------------------------
# _parse_runner_output
# ---------------------------------------------------------------------------


def test_parse_runner_output_texto_none_retorna_none() -> None:
    assert br._parse_runner_output(None) is None  # pylint: disable=protected-access


def test_parse_runner_output_texto_vazio_ou_espacos_retorna_none() -> None:
    assert br._parse_runner_output("") is None  # pylint: disable=protected-access
    resultado = br._parse_runner_output("   \n  ")  # pylint: disable=protected-access
    assert resultado is None


def test_parse_runner_output_pega_ultima_linha_json_valida() -> None:
    raw = "\n".join(
        [
            "log inicial de execucao",
            '{"status": "success", "period": "manha"}',
            "log intermediario qualquer",
            '{"status": "success", "period": "tarde"}',
        ]
    )
    parsed = br._parse_runner_output(raw)  # pylint: disable=protected-access
    assert parsed == {"status": "success", "period": "tarde"}


def test_parse_runner_output_json_malformado_continua_e_retorna_none() -> None:
    raw = "\n".join(
        [
            "linha de log comum",
            "{ isso nao eh json valido",
        ]
    )
    assert br._parse_runner_output(raw) is None  # pylint: disable=protected-access


def test_parse_runner_output_lista_json_valida_mas_nao_dict_retorna_none() -> None:
    resultado = br._parse_runner_output("[1, 2, 3]")  # pylint: disable=protected-access
    assert resultado is None


# ---------------------------------------------------------------------------
# run_beneficiamento_refresh
# ---------------------------------------------------------------------------


@patch(
    "app.services.beneficiamento_refresh.get_project_root", return_value="C:\\FakeRoot"
)
@patch("app.services.beneficiamento_refresh.subprocess.run")
def test_run_beneficiamento_refresh_stdout_valido_retorna_payload(
    mock_run: MagicMock,
    mock_root: MagicMock,
    caplog: Any,
) -> None:
    mock_run.return_value = MagicMock(
        stdout='{"status": "success", "period": "manha"}',
        stderr="",
    )

    with caplog.at_level(logging.INFO, logger="orchestrator"):
        result = br.run_beneficiamento_refresh("manha")

    assert result == {"status": "success", "period": "manha"}
    assert mock_root.called
    assert any("status=success" in record.message for record in caplog.records)


@patch(
    "app.services.beneficiamento_refresh.get_project_root", return_value="C:\\FakeRoot"
)
@patch("app.services.beneficiamento_refresh.subprocess.run")
def test_run_beneficiamento_refresh_timeout_retorna_erro_generico(
    mock_run: MagicMock,
    mock_root: MagicMock,
    caplog: Any,
) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["fake"], timeout=45)

    with caplog.at_level(logging.WARNING, logger="orchestrator"):
        result = br.run_beneficiamento_refresh("tarde")

    assert result == {
        "status": "error",
        "period": "tarde",
        "detail": "Refresh excedeu 45s.",
    }
    assert mock_root.called
    assert any("excedeu" in record.message for record in caplog.records)


@patch(
    "app.services.beneficiamento_refresh.get_project_root", return_value="C:\\FakeRoot"
)
@patch("app.services.beneficiamento_refresh.subprocess.run")
def test_run_beneficiamento_refresh_excecao_generica_retorna_detail_da_excecao(
    mock_run: MagicMock,
    mock_root: MagicMock,
    caplog: Any,
) -> None:
    mock_run.side_effect = OSError("disco cheio")

    with caplog.at_level(logging.ERROR, logger="orchestrator"):
        result = br.run_beneficiamento_refresh("noite")

    assert result == {
        "status": "error",
        "period": "noite",
        "detail": "disco cheio",
    }
    assert mock_root.called
    assert any("Falha ao disparar" in record.message for record in caplog.records)


@patch(
    "app.services.beneficiamento_refresh.get_project_root", return_value="C:\\FakeRoot"
)
@patch("app.services.beneficiamento_refresh.subprocess.run")
def test_run_beneficiamento_refresh_sem_json_valido_retorna_erro_truncado(
    mock_run: MagicMock,
    mock_root: MagicMock,
    caplog: Any,
) -> None:
    mock_run.return_value = MagicMock(
        stdout="", stderr="Traceback (most recent call last): boom"
    )

    with caplog.at_level(logging.ERROR, logger="orchestrator"):
        result = br.run_beneficiamento_refresh("manha")

    assert result == {
        "status": "error",
        "period": "manha",
        "detail": "Traceback (most recent call last): boom",
    }
    assert mock_root.called
    assert any("sem JSON" in record.message for record in caplog.records)


@patch(
    "app.services.beneficiamento_refresh.get_project_root", return_value="C:\\FakeRoot"
)
@patch("app.services.beneficiamento_refresh.subprocess.run")
def test_run_beneficiamento_refresh_stdout_vazio_usa_fallback_stderr(
    mock_run: MagicMock,
    mock_root: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(
        stdout="",
        stderr='{"status": "success", "period": "tarde"}',
    )

    result = br.run_beneficiamento_refresh("tarde")

    assert result == {"status": "success", "period": "tarde"}
    assert mock_root.called


@patch(
    "app.services.beneficiamento_refresh.get_project_root", return_value="C:\\FakeRoot"
)
@patch("app.services.beneficiamento_refresh.subprocess.run")
def test_run_beneficiamento_refresh_monta_comando_com_period(
    mock_run: MagicMock,
    mock_root: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(
        stdout='{"status": "success", "period": "manha"}',
        stderr="",
    )

    br.run_beneficiamento_refresh("manha")

    assert mock_root.called
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert "--period" in cmd
    assert cmd[cmd.index("--period") + 1] == "manha"
    assert kwargs["cwd"] == "C:\\FakeRoot"
    assert kwargs["timeout"] == 45
