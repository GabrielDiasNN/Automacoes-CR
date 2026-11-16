"""
Testes unitários focados na resiliência sintática e throttling do Hub de Notificações (notifications.py).
"""

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app import notifications
from carregadores_modulos import acessar_privado


@pytest.fixture(autouse=True)
def clean_cooldown() -> None:
    """Limpa o estado de throttle antes de cada teste."""
    acessar_privado(notifications, "_alert_state").clear()
    acessar_privado(notifications, "_infra_alert_state").clear()


def test_is_throttled_behavior() -> None:
    """Garante que o throttle bloqueia múltiplos disparos num intervalo de cooldown."""
    automation_id = 42

    # Primeiro envio: não deve estar em cooldown
    assert acessar_privado(notifications, "_is_throttled")(automation_id) is False

    # Envia e marca
    acessar_privado(notifications, "_mark_sent")(automation_id)

    # Segundo envio imediato: deve estar sob throttling
    assert acessar_privado(notifications, "_is_throttled")(automation_id) is True


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
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
    assert "-Phone" in cmd
    assert "554700000000@c.us" in cmd
    # Verifica se a mensagem foi construída corretamente
    assert "*Robo:* Robo WhatsApp" in cmd[-1]


def test_send_whatsapp_alert_sem_env_configurado_retorna_false(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("AUTOMACAO_ALERT_WHATSAPP", raising=False)
    assert notifications.send_whatsapp_alert("Robo", "EXEC-1") is False


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@example.com"})
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
    assert env["ALERT_TO"] == "alertas@example.com"
    assert "Montagem de Terceirizados" in env["ALERT_SUBJECT"]
    assert "EXEC-EMAIL-456" in env["ALERT_HTML_BODY"]


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(
    os.environ,
    {
        "AUTOMACAO_ALERT_EMAIL": "alertas@example.com",
        "AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us",
    },
)
def test_dispatch_alerts_respects_throttle(mock_exists: Any, mock_run: Any) -> None:
    """Garante que dispatch_alerts respeita o throttling de forma ponta a ponta."""
    mock_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    # Mock dos modelos de automação e execução
    @dataclass
    class MockAutomation:
        id: int = 1
        name: str = "Robo Throttled"
        notification_channels: str = "email,whatsapp"

    @dataclass
    class MockExecution:
        id: str = "EXEC-111"

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
    assert acessar_privado(notifications, "_get_cooldown")(0) == 600
    assert acessar_privado(notifications, "_get_cooldown")(2) == 600
    assert acessar_privado(notifications, "_get_cooldown")(3) == 300
    assert acessar_privado(notifications, "_get_cooldown")(4) == 300
    assert acessar_privado(notifications, "_get_cooldown")(5) == 60
    assert acessar_privado(notifications, "_get_cooldown")(100) == 60


def test_mark_sent_evita_estouro_max_tracked(monkeypatch: Any) -> None:
    """Ao atingir o limite de automações rastreadas, a mais antiga é descartada (LRU)."""
    monkeypatch.setattr(notifications, "_MAX_TRACKED", 2)

    acessar_privado(notifications, "_mark_sent")(1)
    time.sleep(0.01)
    acessar_privado(notifications, "_mark_sent")(2)
    time.sleep(0.01)
    acessar_privado(notifications, "_mark_sent")(3)

    assert 1 not in acessar_privado(notifications, "_alert_state")
    assert 2 in acessar_privado(notifications, "_alert_state")
    assert 3 in acessar_privado(notifications, "_alert_state")


def test_reset_alert_state_limpa_contador() -> None:
    acessar_privado(notifications, "_mark_sent")(7)
    assert 7 in acessar_privado(notifications, "_alert_state")

    notifications.reset_alert_state(7)

    assert 7 not in acessar_privado(notifications, "_alert_state")


@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
def test_send_whatsapp_alert_script_ausente_retorna_false(mock_exists: Any) -> None:
    mock_exists.return_value = False
    assert notifications.send_whatsapp_alert("Robo", "EXEC-1") is False


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
def test_send_whatsapp_alert_timeout_retorna_false(
    mock_exists: Any, mock_run: Any
) -> None:
    mock_exists.return_value = True
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="powershell", timeout=60)
    assert notifications.send_whatsapp_alert("Robo", "EXEC-1") is False


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
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
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@example.com"})
def test_send_email_alert_lib_ausente_retorna_false(mock_exists: Any) -> None:
    mock_exists.return_value = False
    assert notifications.send_email_alert("Robo", "EXEC-1") is False


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_EMAIL": "alertas@example.com"})
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
    @dataclass
    class MockAutomation:
        id: int = 501
        name: str = "Robo Sem Canais"
        notification_channels: str | None = None

    @dataclass
    class MockExecution:
        id: str = "EXEC-NOCHAN"

    with (
        patch("app.notifications.send_whatsapp_alert") as mock_wa,
        patch("app.notifications.send_email_alert") as mock_email,
    ):
        notifications.dispatch_alerts(MockAutomation(), MockExecution())

    mock_wa.assert_not_called()
    mock_email.assert_not_called()


def test_dispatch_alerts_apenas_whatsapp() -> None:
    @dataclass
    class MockAutomation:
        id: int = 502
        name: str = "Robo WA"
        notification_channels: str = "whatsapp"

    @dataclass
    class MockExecution:
        id: str = "EXEC-WA-ONLY"

    with (
        patch("app.notifications.send_whatsapp_alert") as mock_wa,
        patch("app.notifications.send_email_alert") as mock_email,
    ):
        notifications.dispatch_alerts(MockAutomation(), MockExecution())

    mock_wa.assert_called_once()
    mock_email.assert_not_called()


def test_dispatch_alerts_apenas_email() -> None:
    @dataclass
    class MockAutomation:
        id: int = 503
        name: str = "Robo Email"
        notification_channels: str = "email"

    @dataclass
    class MockExecution:
        id: str = "EXEC-EMAIL-ONLY"

    with (
        patch("app.notifications.send_whatsapp_alert") as mock_wa,
        patch("app.notifications.send_email_alert") as mock_email,
    ):
        notifications.dispatch_alerts(MockAutomation(), MockExecution())

    mock_email.assert_called_once()
    mock_wa.assert_not_called()


# ---------------------------------------------------------------------------
# _dispatch_infra_whatsapp (isolado de send_infra_alert por conta do limite
# de variáveis locais do pylint)
# ---------------------------------------------------------------------------


@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
def test_dispatch_infra_whatsapp_script_ausente_retorna_false(
    mock_exists: Any,
) -> None:
    mock_exists.return_value = False
    assert (
        acessar_privado(notifications, "_dispatch_infra_whatsapp")(
            "worker_offline", "msg"
        )
        is False
    )


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
def test_dispatch_infra_whatsapp_timeout_retorna_false(
    mock_exists: Any, mock_run: Any
) -> None:
    mock_exists.return_value = True
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="powershell", timeout=60)
    assert (
        acessar_privado(notifications, "_dispatch_infra_whatsapp")(
            "worker_offline", "msg"
        )
        is False
    )


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
def test_dispatch_infra_whatsapp_erro_de_os_retorna_false(
    mock_exists: Any, mock_run: Any
) -> None:
    mock_exists.return_value = True
    mock_run.side_effect = OSError("falha ao iniciar powershell")
    assert (
        acessar_privado(notifications, "_dispatch_infra_whatsapp")(
            "worker_offline", "msg"
        )
        is False
    )


# ---------------------------------------------------------------------------
# send_infra_alert (alertas de incidente de infraestrutura, fora do ciclo de
# falha de automação)
# ---------------------------------------------------------------------------


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
def test_send_infra_alert_envia_whatsapp(
    mock_exists: Any, mock_run: Any, monkeypatch: Any
) -> None:
    monkeypatch.delenv("AUTOMACAO_ALERT_EMAIL", raising=False)
    mock_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    notifications.send_infra_alert("worker_offline", "Worker sem heartbeat recente.")

    mock_run.assert_called_once()
    args, _kwargs = mock_run.call_args
    cmd = args[0]
    assert "-File" in cmd
    assert "-Phone" in cmd
    assert "worker_offline" in cmd[-1]
    assert "worker_offline" in acessar_privado(notifications, "_infra_alert_state")


@patch("app.notifications.subprocess.run")
@patch("app.notifications.os.path.exists")
@patch.dict(os.environ, {"AUTOMACAO_ALERT_WHATSAPP": "554700000000@c.us"})
def test_send_infra_alert_respeita_throttle(
    mock_exists: Any, mock_run: Any, monkeypatch: Any
) -> None:
    monkeypatch.delenv("AUTOMACAO_ALERT_EMAIL", raising=False)
    mock_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    notifications.send_infra_alert("wal_critical", "WAL critico.")
    assert mock_run.call_count == 1

    notifications.send_infra_alert("wal_critical", "WAL critico de novo.")
    assert mock_run.call_count == 1  # segundo disparo suprimido pelo cooldown


@patch("app.notifications.os.path.exists")
def test_send_infra_alert_sem_canais_nao_marca_throttle(
    mock_exists: Any, monkeypatch: Any
) -> None:
    monkeypatch.delenv("AUTOMACAO_ALERT_EMAIL", raising=False)
    monkeypatch.delenv("AUTOMACAO_ALERT_WHATSAPP", raising=False)
    mock_exists.return_value = False
    notifications.send_infra_alert("orphaned_running", "Execucao orfa detectada.")
    assert "orphaned_running" not in acessar_privado(
        notifications, "_infra_alert_state"
    )


def test_reset_infra_alert_state_limpa_componente() -> None:
    acessar_privado(notifications, "_mark_infra_sent")("wal_critical")
    assert "wal_critical" in acessar_privado(notifications, "_infra_alert_state")

    notifications.reset_infra_alert_state("wal_critical")

    assert "wal_critical" not in acessar_privado(notifications, "_infra_alert_state")


def test_dispatch_alerts_async_submete_ao_executor() -> None:
    @dataclass
    class MockAutomation:
        # Satisfaz o Protocol AlertAutomation (#36): mesmo o caminho async, que
        # só repassa ao executor, recebe o contrato completo da automação.
        id: int = 504
        name: str = "Robo Async"
        notification_channels: str = "email"

    @dataclass
    class MockExecution:
        id: str = "EXEC-ASYNC"

    auto = MockAutomation()
    exec_ = MockExecution()

    with patch.object(
        acessar_privado(notifications, "_notification_executor"), "submit"
    ) as mock_submit:
        notifications.dispatch_alerts_async(auto, exec_)

    mock_submit.assert_called_once_with(notifications.dispatch_alerts, auto, exec_)
