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
from typing import Any, Protocol

from app.subprocess_env import build_subprocess_env
from app.timezone import get_now_local


class AlertAutomation(Protocol):  # pylint: disable=too-few-public-methods
    """Contrato mínimo de automação consumido por dispatch_alerts.

    Protocol em vez do models.Automation concreto (#36): tipa exatamente os três
    atributos usados, é satisfeito tanto pela entidade ORM — cujos atributos o
    mypy enxerga como Column[...] no nível de classe — quanto pelos dublês dos
    testes, sem exigir cast. Mesmo padrão de log_broadcast.BroadcastManager.
    """

    id: Any
    name: Any
    notification_channels: Any


class AlertExecution(Protocol):  # pylint: disable=too-few-public-methods
    """Contrato mínimo de execução consumido por dispatch_alerts."""

    id: Any


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


def shutdown_notification_executor() -> None:
    """Encerra o pool de notificações com prazo, no shutdown do worker.

    As threads de `ThreadPoolExecutor` não são daemon, e o pool nunca era
    desligado: o handler `atexit` do `concurrent.futures` fazia join delas
    DEPOIS de `main_loop` retornar. Com fila de alertas pendentes (cada um até
    60 s de WhatsApp + 30 s de e-mail), o processo ficava preso muito além dos
    `SHUTDOWN_GRACE_SECONDS = 30` planejados — e o `Start-Orchestrator.ps1`
    seguinte acabava matando-o à força.

    Os alertas já submetidos têm o prazo para terminar; o que não couber é
    abandonado. Preferir isso a pendurar o encerramento: perder um alerta é
    menos grave que um worker que não morre e é morto com `-Force` no meio de
    uma escrita.
    """
    _notification_executor.shutdown(wait=True, cancel_futures=True)


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
            env=build_subprocess_env(),
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

    # Allowlist, nunca os.environ.copy(): o corpo do alerta vai por variável de
    # ambiente justamente para não ser interpolado no -Command, mas a cópia
    # integral do ambiente levava junto ORCHESTRATOR_API_KEY e as credenciais
    # Oracle para dentro do PowerShell de notificação (corrigido em 31/07/2026).
    env = build_subprocess_env(
        {
            "ALERT_TO": alert_email,
            "ALERT_SUBJECT": subject,
            "ALERT_HTML_BODY": html_body,
        }
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


# ---------------------------------------------------------------------------
# Alertas de incidente de infraestrutura (fora do ciclo de falha de automação)
# ---------------------------------------------------------------------------

# Cooldown fixo (não escalonado) por componente: incidentes de infra tendem a
# persistir por minutos/horas, então um alerta a cada 30 min é suficiente para
# não deixar o operador sem sinal, sem virar spam continuo do mesmo problema.
INFRA_ALERT_COOLDOWN_SECONDS = 1800

_infra_alert_state: dict[str, float] = {}
_infra_state_lock = threading.Lock()


def _is_infra_throttled(component: str) -> bool:
    """Verifica se o alerta de infraestrutura esta em cooldown. Thread-safe."""
    with _infra_state_lock:
        last_sent = _infra_alert_state.get(component, 0.0)
        return (time.time() - last_sent) < INFRA_ALERT_COOLDOWN_SECONDS


def _mark_infra_sent(component: str) -> None:
    """Registra o envio do alerta de infraestrutura. Thread-safe."""
    with _infra_state_lock:
        _infra_alert_state[component] = time.time()


def reset_infra_alert_state(component: str) -> None:
    """Reseta o cooldown de um componente (uso principal: testes)."""
    with _infra_state_lock:
        _infra_alert_state.pop(component, None)


def send_infra_alert(component: str, message: str) -> None:
    """Dispara alerta de incidente de infraestrutura (worker/WAL/fila) fora do
    ciclo de falha de automação — hoje esses incidentes só apareciam no
    dashboard, exigindo que alguém estivesse olhando para percebê-los.
    """
    if _is_infra_throttled(component):
        logger.info("Alerta de infraestrutura suprimido por throttle: %s", component)
        return

    full_message = (
        f"*Hub de Automacoes: INCIDENTE DE INFRAESTRUTURA*\n\n"
        f"*Componente:* {component}\n"
        f"*Detalhe:* {message}"
    )

    wa_script = os.path.join(PROJECT_ROOT, "lib", "Send-WhatsApp.ps1")
    whatsapp_sent = False
    if os.path.exists(wa_script):
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
                    full_message,
                ],
                env=build_subprocess_env(),
                capture_output=True,
                timeout=60,
                check=False,
            )
            whatsapp_sent = result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error(
                "Timeout ao enviar alerta de infraestrutura via WhatsApp: %s",
                component,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Erro ao enviar alerta de infraestrutura via WhatsApp: %s", e)
    else:
        logger.error("Script de WhatsApp nao encontrado na pasta lib.")

    alert_email = os.environ.get("AUTOMACAO_ALERT_EMAIL", "")
    lib_email = os.path.join(PROJECT_ROOT, "lib", "Lib-Email.psm1")
    email_sent = False
    if alert_email and os.path.exists(lib_email):
        agora = get_now_local().strftime("%d/%m/%Y %H:%M:%S")
        subject = f"[INCIDENTE INFRA] {component} - {agora}"
        html_body = (
            f"<p><b>Componente:</b> {component}<br>"
            f"<b>Horário:</b> {agora}<br>"
            f"<b>Detalhe:</b> {message}</p>"
        )
        ps_command = (
            f"Import-Module '{lib_email}' -Force; "
            f"Send-OutlookEmail -To $env:ALERT_TO "
            f"-Subject $env:ALERT_SUBJECT "
            f"-HtmlBody $env:ALERT_HTML_BODY "
            f"-ExecId 'INFRA' -LogPath 'ALERT'"
        )
        env = build_subprocess_env(
            {
                "ALERT_TO": alert_email,
                "ALERT_SUBJECT": subject,
                "ALERT_HTML_BODY": html_body,
            }
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
                env=env,
                capture_output=True,
                timeout=30,
                check=False,
            )
            email_sent = result.returncode == 0
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Erro ao enviar alerta de infraestrutura via e-mail: %s", e)

    if whatsapp_sent or email_sent:
        logger.info("Alerta de infraestrutura enviado: %s", component)
        _mark_infra_sent(component)


def dispatch_alerts(automation: AlertAutomation, execution: AlertExecution) -> None:
    """Analisa os canais configurados e dispara os alertas necessarios (com throttling)."""
    if not automation.notification_channels:
        return

    automation_id = int(automation.id)
    if _is_throttled(automation_id):
        return

    # Conversões explícitas: com os modelos reais no lugar de Any (#36), o mypy
    # enxerga os atributos como Column[...] no nível de classe — mesmo padrão
    # str(auto.script_path) já usado nos routers.
    channels = [
        c.strip().lower() for c in str(automation.notification_channels).split(",")
    ]
    automation_name = str(automation.name)
    exec_id = str(execution.id)

    if "whatsapp" in channels:
        send_whatsapp_alert(automation_name, exec_id)

    if "email" in channels:
        send_email_alert(automation_name, exec_id)

    _mark_sent(automation_id)


def _log_dispatch_failure(future: "concurrent.futures.Future[None]") -> None:
    """Loga exceção do dispatch — `concurrent.futures` a guarda em silêncio.

    Sem `.result()` nem `add_done_callback`, qualquer exceção dentro de
    `dispatch_alerts` ficava presa no Future e NUNCA chegava ao logger: o alerta
    de falha de uma automação crítica sumia sem rastro, exatamente quando é mais
    necessário. Vale em especial para `DetachedInstanceError`, se as entidades
    ORM passadas para a outra thread tiverem sido expiradas pelo fechamento da
    sessão do chamador.
    """
    exc = future.exception()
    if exc is not None:
        logger.error("Falha no dispatch assíncrono de alertas: %s", exc, exc_info=exc)


def dispatch_alerts_async(
    automation: AlertAutomation, execution: AlertExecution
) -> None:
    """Submete dispatch para thread pool dedicada, liberando a thread do worker imediatamente (HF-4/C1)."""
    future = _notification_executor.submit(dispatch_alerts, automation, execution)
    future.add_done_callback(_log_dispatch_failure)
