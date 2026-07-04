# pylint: disable=protected-access
"""
Testes unitários focados na resiliência sintática e throttling do Hub de Notificações (notifications.py).
"""

import os
import subprocess
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app import notifications


@pytest.fixture(autouse=True)
def clean_cooldown() -> None:
    """Limpa o estado de throttle antes de cada teste."""
    notifications._alert_state.clear()


def test_is_throttled_behavior() -> None:
    """Garante que o throttle bloqueia múltiplos disparos num intervalo de cooldown."""
    automation_id = 42

    # Primeiro envio: não deve estar em cooldown
    assert notifications._is_throttled(automation_id) is False

    # Envia e marca
    notifications._mark_sent(automation_id)

    # Segundo envio imediato: deve estar sob throttling
    assert notifications._is_throttled(automation_id) is True


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
def test_send_whatsapp_alert_success(mock_exists: Any, mock_run: Any) -> None:
    """Garante que send_whatsapp_alert invoca o script PowerShell corretamente."""
    mock_exists.return_value = True

    # Simula subprocesso terminando com código 0 (sucesso)
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    success = notifications.send_whatsapp_alert(
        task_name="Robo WhatsApp", exec_id="EXEC-WA-123", error_msg="Falha no Oracle"
    )

    assert success is True
    assert any("Send-WhatsApp.ps1" in call[0][0] for call in mock_exists.call_args_list)
    mock_run.assert_called_once()

    args, _kwargs = mock_run.call_args
    cmd = args[0]
    assert "powershell.exe" in cmd
    assert "-File" in cmd
    # Verifica se a mensagem foi construída corretamente
    assert "*Robo:* Robo WhatsApp" in cmd[-1]


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@costaricamalhas.com"})
def test_send_email_alert_success(mock_exists: Any, mock_run: Any) -> None:
    """Garante que send_email_alert passa as variáveis de ambiente corretas e blinda contra aspas."""
    mock_exists.return_value = True

    # Simula subprocesso terminando com código 0 (sucesso)
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    success = notifications.send_email_alert(
        task_name="Montagem de Terceirizados",
        exec_id="EXEC-EMAIL-456",
        error_msg="Erro de IO",
    )

    assert success is True
    assert any("Lib-Email.psm1" in call[0][0] for call in mock_exists.call_args_list)
    mock_run.assert_called_once()

    args, kwargs = mock_run.call_args
    # O comando powershell usa $env:ALERT_TO, $env:ALERT_SUBJECT e $env:ALERT_HTML_BODY
    cmd = args[0]
    assert "powershell.exe" in cmd
    assert "-Command" in cmd
    assert "$env:ALERT_TO" in cmd[-1]
    assert "$env:ALERT_SUBJECT" in cmd[-1]
    assert "$env:ALERT_HTML_BODY" in cmd[-1]

    # As variáveis reais devem estar seguras no kwargs['env']
    env = kwargs.get("env")
    assert env is not None
    assert env["ALERT_TO"] == "alertas@costaricamalhas.com"
    assert "Montagem de Terceirizados" in env["ALERT_SUBJECT"]
    assert "EXEC-EMAIL-456" in env["ALERT_HTML_BODY"]


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@costaricamalhas.com"})
def test_dispatch_alerts_respects_throttle(mock_exists: Any, mock_run: Any) -> None:
    """Garante que dispatch_alerts respeita o throttling de forma ponta a ponta."""
    mock_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    # Mock dos modelos de automação e execução
    class MockAutomation:  # pylint: disable=too-few-public-methods
        id = 1
        name = "Robo Throttled"
        notification_channels = "email,whatsapp"

    class MockExecution:  # pylint: disable=too-few-public-methods
        id = "EXEC-111"

    auto = MockAutomation()
    exec_ = MockExecution()

    # Primeiro disparo: envia alertas de WhatsApp e e-mail
    notifications.dispatch_alerts(auto, exec_)
    assert mock_run.call_count == 2  # 1 para WA e 1 para E-mail

    # Segundo disparo imediato: deve ser filtrado pelo throttle
    notifications.dispatch_alerts(auto, exec_)
    assert mock_run.call_count == 2  # Não deve ter aumentado


def test_get_cooldown_escalation_tiers() -> None:
    """Garante a escalada progressiva de cooldown por contagem de falhas consecutivas."""
    assert notifications._get_cooldown(0) == 600
    assert notifications._get_cooldown(2) == 600
    assert notifications._get_cooldown(3) == 300
    assert notifications._get_cooldown(4) == 300
    assert notifications._get_cooldown(5) == 60
    assert notifications._get_cooldown(100) == 60


def test_mark_sent_evita_estouro_max_tracked(monkeypatch: Any) -> None:
    """Ao atingir o limite de automações rastreadas, a mais antiga é descartada (LRU)."""
    monkeypatch.setattr(notifications, "_MAX_TRACKED", 2)

    notifications._mark_sent(1)
    time.sleep(0.01)
    notifications._mark_sent(2)
    time.sleep(0.01)
    notifications._mark_sent(3)

    assert 1 not in notifications._alert_state
    assert 2 in notifications._alert_state
    assert 3 in notifications._alert_state


def test_reset_alert_state_limpa_contador() -> None:
    notifications._mark_sent(7)
    assert 7 in notifications._alert_state

    notifications.reset_alert_state(7)

    assert 7 not in notifications._alert_state


@patch("app.notifications.os.path.exists")
def test_send_whatsapp_alert_script_ausente_retorna_false(mock_exists: Any) -> None:
    mock_exists.return_value = False
    assert notifications.send_whatsapp_alert("Robo", "EXEC-1") is False


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
def test_send_whatsapp_alert_timeout_retorna_false(
    mock_exists: Any, mock_run: Any
) -> None:
    mock_exists.return_value = True
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="powershell", timeout=60)
    assert notifications.send_whatsapp_alert("Robo", "EXEC-1") is False


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
def test_send_whatsapp_alert_exit_code_nao_zero_retorna_false(
    mock_exists: Any, mock_run: Any
) -> None:
    mock_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_run.return_value = mock_proc
    assert notifications.send_whatsapp_alert("Robo", "EXEC-1") is False


def test_send_email_alert_sem_env_configurado_retorna_false(monkeypatch: Any) -> None:
    monkeypatch.delenv("AUTOMACAO_ALERT_EMAIL", raising=False)
    assert notifications.send_email_alert("Robo", "EXEC-1") is False


@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@costaricamalhas.com"})
def test_send_email_alert_lib_ausente_retorna_false(mock_exists: Any) -> None:
    mock_exists.return_value = False
    assert notifications.send_email_alert("Robo", "EXEC-1") is False


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@costaricamalhas.com"})
def test_send_email_alert_exit_code_nao_zero_retorna_false(
    mock_exists: Any, mock_run: Any
) -> None:
    mock_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = b"falha no outlook"
    mock_run.return_value = mock_proc
    assert notifications.send_email_alert("Robo", "EXEC-1") is False


def test_dispatch_alerts_sem_canais_configurados_nao_envia() -> None:
    class MockAutomation:  # pylint: disable=too-few-public-methods
        id = 501
        notification_channels = None

    class MockExecution:  # pylint: disable=too-few-public-methods
        id = "EXEC-NOCHAN"

    with (
        patch("app.notifications.send_whatsapp_alert") as mock_wa,
        patch("app.notifications.send_email_alert") as mock_email,
    ):
        notifications.dispatch_alerts(MockAutomation(), MockExecution())

    mock_wa.assert_not_called()
    mock_email.assert_not_called()


def test_dispatch_alerts_apenas_whatsapp() -> None:
    class MockAutomation:  # pylint: disable=too-few-public-methods
        id = 502
        name = "Robo WA"
        notification_channels = "whatsapp"

    class MockExecution:  # pylint: disable=too-few-public-methods
        id = "EXEC-WA-ONLY"

    with (
        patch("app.notifications.send_whatsapp_alert") as mock_wa,
        patch("app.notifications.send_email_alert") as mock_email,
    ):
        notifications.dispatch_alerts(MockAutomation(), MockExecution())

    mock_wa.assert_called_once()
    mock_email.assert_not_called()


def test_dispatch_alerts_apenas_email() -> None:
    class MockAutomation:  # pylint: disable=too-few-public-methods
        id = 503
        name = "Robo Email"
        notification_channels = "email"

    class MockExecution:  # pylint: disable=too-few-public-methods
        id = "EXEC-EMAIL-ONLY"

    with (
        patch("app.notifications.send_whatsapp_alert") as mock_wa,
        patch("app.notifications.send_email_alert") as mock_email,
    ):
        notifications.dispatch_alerts(MockAutomation(), MockExecution())

    mock_email.assert_called_once()
    mock_wa.assert_not_called()


def test_dispatch_alerts_async_submete_ao_executor() -> None:
    class MockAutomation:  # pylint: disable=too-few-public-methods
        id = 504

    class MockExecution:  # pylint: disable=too-few-public-methods
        id = "EXEC-ASYNC"

    auto = MockAutomation()
    exec_ = MockExecution()

    with patch.object(notifications._notification_executor, "submit") as mock_submit:
        notifications.dispatch_alerts_async(auto, exec_)

    mock_submit.assert_called_once_with(notifications.dispatch_alerts, auto, exec_)
