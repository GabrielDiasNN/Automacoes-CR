# pylint: disable=all
# mypy: ignore-errors
"""
Hub de Notificacoes do Orchestrator v4.0.

Canais disponiveis:
  - WhatsApp (via script PS1 nativo)
  - Dashboard (via AuditLog para feed de eventos)

Protecoes:
  - Throttling: max 1 alerta por automacao a cada 10 minutos
"""

import logging
import os
import subprocess
import time
from datetime import datetime

from app.timezone import get_now_local

logger = logging.getLogger("orchestrator.notifications")

# Throttle: {automation_id: last_alert_timestamp}
_alert_cooldown = {}
COOLDOWN_SECONDS = 600  # 10 minutos

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _is_throttled(automation_id: int) -> bool:
    """Verifica se o alerta esta em cooldown."""
    last = _alert_cooldown.get(automation_id)
    if last and (time.time() - last) < COOLDOWN_SECONDS:
        logger.info(
            f"Alerta suprimido por throttle (cooldown {COOLDOWN_SECONDS}s): automation_id={automation_id}"
        )
        return True
    return False


def _mark_sent(automation_id: int):
    """Marca o timestamp do ultimo alerta enviado."""
    _alert_cooldown[automation_id] = time.time()


def send_whatsapp_alert(task_name: str, exec_id: str, error_msg: str = ""):
    """Dispara alerta via script nativo de WhatsApp do projeto."""
    logger.info(f"Enviando alerta WhatsApp para {task_name}")

    wa_script = os.path.join(PROJECT_ROOT, "lib", "Send-WhatsApp.ps1")
    if not os.path.exists(wa_script):
        logger.error("Script de WhatsApp nao encontrado na pasta lib.")
        return False

    message = (
        f"*Hub de Automacoes: FALHA*\n\n"
        f"*Robo:* {task_name}\n"
        f"*Exec:* {exec_id}\n"
        f"*Erro:* Verifique os logs no Dashboard."
    )

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                wa_script,
                "-Message",
                message,
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info(f"Alerta WhatsApp enviado: {task_name}")
            return True
        else:
            logger.warning(f"WhatsApp retornou code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout ao enviar alerta WhatsApp para {task_name}")
        return False
    except Exception as e:
        logger.error(f"Erro ao enviar alerta WhatsApp: {e}")
        return False


def send_email_alert(task_name: str, exec_id: str, error_msg: str = ""):
    """Dispara alerta via Outlook COM (reusa Lib-Email.psm1)."""
    logger.info(f"Enviando alerta E-mail para {task_name}")

    alert_email = os.environ.get("AUTOMACAO_ALERT_EMAIL", "")
    if not alert_email:
        logger.warning(
            "AUTOMACAO_ALERT_EMAIL nao configurado. Alerta de e-mail suprimido."
        )
        return False

    lib_email = os.path.join(PROJECT_ROOT, "lib", "Lib-Email.psm1")
    if not os.path.exists(lib_email):
        logger.warning("Lib-Email.psm1 nao encontrada. Alerta de e-mail suprimido.")
        return False

    agora = get_now_local().strftime("%d/%m/%Y %H:%M:%S")
    subject = f"[FALHA] Automacao '{task_name}' - {agora}"

    ps_command = (
        f"Import-Module '{lib_email}' -Force; "
        f"Send-OutlookEmail -To '{alert_email}' "
        f"-Subject '{subject}' "
        f"-HtmlBody '<p><b>Automacao:</b> {task_name}<br>"
        f"<b>ExecId:</b> {exec_id}<br>"
        f"<b>Horario:</b> {agora}<br>"
        f"<b>Erro:</b> Verifique os logs no Dashboard.</p>' "
        f"-ExecId '{exec_id}' -LogPath 'ALERT'"
    )

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_command,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"Alerta e-mail enviado para {alert_email}")
            return True
        else:
            logger.warning(f"E-mail retornou code {result.returncode}")
            return False
    except Exception as e:
        logger.error(f"Erro ao enviar alerta e-mail: {e}")
        return False


def dispatch_alerts(automation, execution):
    """Analisa os canais configurados e dispara os alertas necessarios (com throttling)."""
    if not automation.notification_channels:
        return

    # Throttle global por automacao
    if _is_throttled(automation.id):
        return

    channels = [c.strip().lower() for c in automation.notification_channels.split(",")]
    sent_any = False

    if "whatsapp" in channels:
        if send_whatsapp_alert(automation.name, execution.id):
            sent_any = True

    if "email" in channels:
        if send_email_alert(automation.name, execution.id):
            sent_any = True

    if sent_any:
        _mark_sent(automation.id)
