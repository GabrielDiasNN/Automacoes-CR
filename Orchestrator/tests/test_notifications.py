# pylint: disable=all
# mypy: ignore-errors
"""
Testes unitários focados na resiliência sintática e throttling do Hub de Notificações (notifications.py).
"""

import os
import subprocess
import pytest
from unittest.mock import MagicMock, patch
from app import notifications
from app.timezone import get_now_local


@pytest.fixture(autouse=True)
def clean_cooldown():
    """Limpa o dicionário de cooldown antes de cada teste."""
    notifications._alert_cooldown.clear()


def test_is_throttled_behavior():
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
def test_send_whatsapp_alert_success(mock_exists, mock_run):
    """Garante que send_whatsapp_alert invoca o script PowerShell corretamente."""
    mock_exists.return_value = True
    
    # Simula subprocesso terminando com código 0 (sucesso)
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc
    
    success = notifications.send_whatsapp_alert(
        task_name="Robo WhatsApp",
        exec_id="EXEC-WA-123",
        error_msg="Falha no Oracle"
    )
    
    assert success is True
    assert any("Send-WhatsApp.ps1" in call[0][0] for call in mock_exists.call_args_list)
    mock_run.assert_called_once()
    
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert "powershell.exe" in cmd
    assert "-File" in cmd
    # Verifica se a mensagem foi construída corretamente
    assert "*Robo:* Robo WhatsApp" in cmd[-1]


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@costaricamalhas.com"})
def test_send_email_alert_success(mock_exists, mock_run):
    """Garante que send_email_alert passa as variáveis de ambiente corretas e blinda contra aspas."""
    mock_exists.return_value = True
    
    # Simula subprocesso terminando com código 0 (sucesso)
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc
    
    success = notifications.send_email_alert(
        task_name="Montagem de Terceirizados",
        exec_id="EXEC-EMAIL-456",
        error_msg="Erro de IO"
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
def test_dispatch_alerts_respects_throttle(mock_exists, mock_run):
    """Garante que dispatch_alerts respeita o throttling de forma ponta a ponta."""
    mock_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc
    
    # Mock dos modelos de automação e execução
    class MockAutomation:
        id = 1
        name = "Robo Throttled"
        notification_channels = "email,whatsapp"
        
    class MockExecution:
        id = "EXEC-111"
        
    auto = MockAutomation()
    exec_ = MockExecution()
    
    # Primeiro disparo: envia alertas de WhatsApp e e-mail
    notifications.dispatch_alerts(auto, exec_)
    assert mock_run.call_count == 2  # 1 para WA e 1 para E-mail
    
    # Segundo disparo imediato: deve ser filtrado pelo throttle
    notifications.dispatch_alerts(auto, exec_)
    assert mock_run.call_count == 2  # Não deve ter aumentado
