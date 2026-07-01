"""
Hub de Notificacoes do Orchestrator v4.1.

Canais disponiveis:
  - WhatsApp (via script PS1 nativo)
  - Dashboard (via AuditLog para feed de eventos)

Protecoes:
  - Throttling thread-safe: max 1 alerta por automacao a cada 10 minutos (fase 1)
  - Escalada progressiva de cooldown por contagem de falhas consecutivas (fase 2)
  - Dispatch assincrono: nao bloqueia a thread do worker (HF-4/C1)
"""

import concurrent.futures
import logging
import os
import subprocess
import threading
import time
from typing import Any

from app.timezone import get_now_local

logger = logging.getLogger("orchestrator.notifications")

# ---------------------------------------------------------------------------
# Throttle thread-safe com escalada progressiva (HF-1/A3 + 2.6/C3)
# ---------------------------------------------------------------------------

# Tiers de cooldown: (falhas_minimas, cooldown_segundos)
COOLDOWN_TIERS = [
    (1, 600),  # 1ª falha: cooldown 10 min
    (3, 300),  # 3ª+ falha: cooldown 5 min (escalada)
    (5, 60),  # 5ª+ falha: cooldown 1 min (crítico)
]
_MAX_TRACKED = 500

# Estado: {automation_id: {"count": int, "last_sent": float}}
_alert_state: dict[int, dict[str, Any]] = {}
_state_lock = threading.Lock()

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Pool dedicado para dispatch de notificações — não bloqueia threads do worker (HF-4/C1)
_notification_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="notif"
)


def _get_cooldown(fail_count: int) -> int:
    """Retorna o cooldown em segundos baseado na contagem de falhas consecutivas."""
    for threshold, cooldown in reversed(COOLDOWN_TIERS):
        if fail_count >= threshold:
            return cooldown
    return COOLDOWN_TIERS[0][1]


def _is_throttled(automation_id: int) -> bool:
    """Verifica se o alerta esta em cooldown. Thread-safe."""
    with _state_lock:
        state = _alert_state.get(automation_id, {"count": 0, "last_sent": 0.0})
        cooldown = _get_cooldown(state["count"])
        elapsed = time.time() - state["last_sent"]
        if elapsed < cooldown:
            logger.info(
                "Alerta suprimido por throttle (cooldown %ds, falhas=%d): automation_id=%d",
                cooldown,
                state["count"],
                automation_id,
            )
            return True
        return False


def _mark_sent(automation_id: int) -> None:
    """Registra envio e incrementa contador de falhas consecutivas. Thread-safe."""
    with _state_lock:
        if len(_alert_state) >= _MAX_TRACKED:
            oldest = min(_alert_state, key=lambda k: _alert_state[k]["last_sent"])
            del _alert_state[oldest]
        state = _alert_state.get(automation_id, {"count": 0, "last_sent": 0.0})
        _alert_state[automation_id] = {
            "count": state["count"] + 1,
            "last_sent": time.time(),
        }


def reset_alert_state(automation_id: int) -> None:
    """Reseta o contador de falhas consecutivas (chamar em execucao bem-sucedida)."""
    with _state_lock:
        _alert_state.pop(automation_id, None)


def send_whatsapp_alert(task_name: str, exec_id: str, error_msg: str = "") -> bool:
    """Dispara alerta via script nativo de WhatsApp do projeto."""
    logger.info("Enviando alerta WhatsApp para %s", task_name)
    if error_msg:
        logger.debug("Detalhe do erro (nao enviado ao WhatsApp): %s", error_msg)

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
            check=False,
        )
        if result.returncode == 0:
            logger.info("Alerta WhatsApp enviado: %s", task_name)
            return True
        logger.warning("WhatsApp retornou code %d", result.returncode)
        return False
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao enviar alerta WhatsApp para %s", task_name)
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Erro ao enviar alerta WhatsApp: %s", e)
        return False


def send_email_alert(task_name: str, exec_id: str, error_msg: str = "") -> bool:
    """Dispara alerta via Outlook COM (reusa Lib-Email.psm1)."""
    logger.info("Enviando alerta E-mail para %s", task_name)
    if error_msg:
        logger.debug("Detalhe do erro (nao enviado ao e-mail): %s", error_msg)

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
    subject = f"[FALHA] Automação '{task_name}' - {agora}"
    html_body = (
        f"<p><b>Automação:</b> {task_name}<br>"
        f"<b>ExecId:</b> {exec_id}<br>"
        f"<b>Horário:</b> {agora}<br>"
        f"<b>Erro:</b> Verifique os logs no Dashboard.</p>"
    )

    ps_command = (
        f"Import-Module '{lib_email}' -Force; "
        f"Send-OutlookEmail -To $env:ALERT_TO "
        f"-Subject $env:ALERT_SUBJECT "
        f"-HtmlBody $env:ALERT_HTML_BODY "
        f"-ExecId '{exec_id}' -LogPath 'ALERT'"
    )

    env = os.environ.copy()
    env["ALERT_TO"] = alert_email
    env["ALERT_SUBJECT"] = subject
    env["ALERT_HTML_BODY"] = html_body

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
            env=env,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            logger.info("Alerta e-mail enviado para %s", alert_email)
            return True
        stderr_decoded = result.stderr.decode("utf-8", errors="replace")
        logger.warning(
            "E-mail retornou code %d. Stderr: %s", result.returncode, stderr_decoded
        )
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Erro ao enviar alerta e-mail: %s", e)
        return False


def dispatch_alerts(automation: Any, execution: Any) -> None:
    """Analisa os canais configurados e dispara os alertas necessarios (com throttling)."""
    if not automation.notification_channels:
        return

    if _is_throttled(automation.id):
        return

    channels = [c.strip().lower() for c in automation.notification_channels.split(",")]

    if "whatsapp" in channels:
        send_whatsapp_alert(automation.name, execution.id)

    if "email" in channels:
        send_email_alert(automation.name, execution.id)

    _mark_sent(automation.id)


def dispatch_alerts_async(automation: Any, execution: Any) -> None:
    """Submete dispatch para thread pool dedicada, liberando a thread do worker imediatamente (HF-4/C1)."""
    _notification_executor.submit(dispatch_alerts, automation, execution)
