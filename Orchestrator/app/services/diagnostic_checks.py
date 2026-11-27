"""Analisadores de diagnóstico: funções puras que avaliam estado e geram findings.

Extraído de ``system_diagnostics`` para separar a lógica de análise (check_*)
dos coletores de dados (``diagnostic_collectors``) e da montagem de payload.
"""

from __future__ import annotations

from typing import Any

from ..constants import (
    ACTION_CODE_BACKUP,
    ACTION_CODE_CHECKPOINT,
    ACTION_CODE_SCHEDULER_RELOAD,
    ACTION_CODE_WORKER_RECOVER,
    DIAGNOSTIC_FAILURE_HOTSPOT_THRESHOLD,
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_WAL_CRITICAL_MB,
    DIAGNOSTIC_WAL_ELEVATED_MB,
    DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
    DIAGNOSTIC_WORKER_SATURATION_WARN_SECONDS,
    ORCHESTRATOR_SCHEMA_VERSION,
    SEVERITY_ERROR,
    SEVERITY_WARN,
)
from .diagnostic_collectors import add_finding


def check_schema_integrity(
    schema_status: dict[str, Any], schema_version: str
) -> list[dict[str, Any]]:
    """Gera findings se o schema SQLite divergir do contrato esperado."""
    findings: list[dict[str, Any]] = []
    if not schema_status["valid"]:
        add_finding(
            findings,
            "ERROR",
            "database",
            "Schema SQLite diverge do contrato esperado.",
            {
                "action_hint": "Executar diagnóstico de schema e revisar migração/backup antes de operar.",
                "action_code": ACTION_CODE_BACKUP,
                "action_label": "Gerar backup antes de corrigir schema",
                "impact": "Risco de erro em leitura/escrita e de decisões operacionais baseadas em estrutura divergente.",
                "priority": 1,
            },
        )

    if schema_version != ORCHESTRATOR_SCHEMA_VERSION:
        add_finding(
            findings,
            SEVERITY_WARN,
            "database",
            f"Schema version divergente: banco={schema_version}, app={ORCHESTRATOR_SCHEMA_VERSION}.",
            {
                "action_hint": "Reiniciar o Orchestrator para reaplicar migracoes leves e validar o banco.",
                "action_code": ACTION_CODE_WORKER_RECOVER,
                "action_label": "Reiniciar Orchestrator",
                "impact": "Pode indicar migração leve pendente ou instância desatualizada servindo a operação.",
                "priority": 2,
            },
        )
    return findings


def check_wal_health(wal_size_mb: float) -> tuple[list[dict[str, Any]], str]:
    """Avalia o tamanho do WAL e retorna (findings, wal_risk)."""
    findings: list[dict[str, Any]] = []
    wal_risk = "normal"
    if wal_size_mb >= DIAGNOSTIC_WAL_CRITICAL_MB:
        wal_risk = "critical"
        add_finding(
            findings,
            SEVERITY_ERROR,
            "database",
            f"WAL elevado ({wal_size_mb} MB).",
            {
                "action_hint": "Executar checkpoint e verificar contenção de escrita no SQLite.",
                "action_code": ACTION_CODE_CHECKPOINT,
                "action_label": "Executar checkpoint",
                "impact": "Risco de degradação de I/O, crescimento de disco e lentidão no dashboard.",
                "priority": 1,
            },
        )
    elif wal_size_mb >= DIAGNOSTIC_WAL_ELEVATED_MB:
        wal_risk = "elevated"
        add_finding(
            findings,
            SEVERITY_WARN,
            "database",
            f"WAL acima do normal ({wal_size_mb} MB).",
            {
                "action_hint": "Agendar checkpoint operacional se o valor continuar crescendo.",
                "action_code": ACTION_CODE_CHECKPOINT,
                "action_label": "Executar checkpoint",
                "impact": "Indica acúmulo de escrita; se crescer, pode virar incidente de banco.",
                "priority": 2,
            },
        )
    return findings, wal_risk


def check_scheduler_health(
    scheduler: Any, inconsistencies: list[str]
) -> list[dict[str, Any]]:
    """Gera findings para scheduler parado, sem jobs ou inconsistente com o banco."""
    findings: list[dict[str, Any]] = []
    if not scheduler.running:
        add_finding(
            findings,
            SEVERITY_ERROR,
            "scheduler",
            "Scheduler está parado.",
            {
                "action_hint": "Reiniciar Orchestrator e confirmar carregamento dos jobs.",
                "action_code": ACTION_CODE_WORKER_RECOVER,
                "action_label": "Recuperar Orchestrator",
                "impact": "Automações agendadas podem deixar de disparar.",
                "priority": 1,
            },
        )
    elif len(scheduler.get_jobs()) == 0:
        add_finding(
            findings,
            SEVERITY_WARN,
            "scheduler",
            "Scheduler está ativo, mas sem jobs carregados.",
            {
                "action_hint": "Verificar automações habilitadas com agenda configurada.",
                "action_code": ACTION_CODE_SCHEDULER_RELOAD,
                "action_label": "Sincronizar agenda",
                "impact": "Agenda vazia pode ser legítima, mas também pode indicar sincronismo quebrado.",
                "priority": 3,
            },
        )

    for item in inconsistencies:
        add_finding(
            findings,
            SEVERITY_WARN,
            "scheduler",
            item,
            {
                "action_hint": "Sincronizar scheduler com o banco e revisar automações habilitadas.",
                "action_code": ACTION_CODE_SCHEDULER_RELOAD,
                "action_label": "Sincronizar agenda",
                "impact": "Banco e memória divergem; disparos podem ser omitidos ou ficar órfãos.",
                "priority": 2,
            },
        )
    return findings


def check_worker_health(
    worker_status: Any,
    active_count: int,
    last_ping_age_seconds: float | None,
) -> list[dict[str, Any]]:
    """Gera finding se o worker estiver sem heartbeat recente."""
    findings: list[dict[str, Any]] = []
    if not worker_status.is_alive:
        add_finding(
            findings,
            (
                SEVERITY_ERROR
                if active_count
                or (last_ping_age_seconds or 0)
                >= DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS
                else SEVERITY_WARN
            ),
            "worker",
            "Worker sem heartbeat recente.",
            {
                "action_hint": "Recuperar o Orchestrator para reativar o worker e retomar a fila.",
                "action_code": "worker_recover" if active_count else "worker_wakeup",
                "action_label": (
                    "Recuperar worker" if active_count else "Acordar worker"
                ),
                "impact": "Execuções pendentes ou em andamento podem ficar sem processamento.",
                "priority": 1 if active_count else 2,
            },
        )
    return findings


def check_queue_health(
    pending_age_seconds: float, running_age_seconds: float
) -> list[dict[str, Any]]:
    """Gera findings para execuções envelhecidas em PENDING ou RUNNING."""
    findings: list[dict[str, Any]] = []
    if pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS:
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            f"Execução pendente há {round(pending_age_seconds, 1)} segundos.",
            {
                "action_hint": "Verificar worker, concorrência e bloqueios antes de reenfileirar.",
                "action_code": "worker_wakeup",
                "action_label": "Acordar worker",
                "impact": "Fila parada aumenta atraso operacional e pode esconder automação bloqueada.",
                "priority": 2,
            },
        )

    if running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS:
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            f"Execução em RUNNING há {round(running_age_seconds, 1)} segundos.",
            {
                "action_hint": "Consultar logs da execução e avaliar parada controlada se houver hang.",
                "action_code": "show_running",
                "action_label": "Ver execuções em andamento",
                "impact": "Pode representar processamento longo legítimo ou automação travada segurando recursos.",
                "priority": 2,
            },
        )
    return findings


def check_running_over_runtime(
    running_over_runtime: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Gera finding se houver execução RUNNING acima do max_runtime cadastrado."""
    findings: list[dict[str, Any]] = []
    if running_over_runtime:
        first_stale = running_over_runtime[0]
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            (
                f"{first_stale['automation_name'] or first_stale['exec_id']} excedeu "
                f"o max_runtime cadastrado ({first_stale['max_runtime_minutes']} min)."
            ),
            {
                "action_hint": "Abrir logs da execução, confirmar se há progresso real e avaliar parada controlada.",
                "action_code": "show_running",
                "action_label": "Ver execuções em andamento",
                "impact": "Execução acima do limite pode indicar subprocesso travado, timeout não aplicado ou automação sem heartbeat operacional.",
                "priority": 1,
            },
        )
    return findings


def check_failure_hotspots(
    failure_hotspots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Gera findings para automações com muitas falhas nas últimas 24h."""
    findings: list[dict[str, Any]] = []
    for hotspot in failure_hotspots:
        if hotspot["failures_24h"] < DIAGNOSTIC_FAILURE_HOTSPOT_THRESHOLD:
            continue
        channels = str(hotspot.get("notification_channels") or "").lower()
        channel_hint = (
            " e canais de notificação"
            if ("whatsapp" in channels or "email" in channels)
            else ""
        )
        add_finding(
            findings,
            SEVERITY_WARN,
            "automation",
            f"{hotspot['automation_name']} falhou {hotspot['failures_24h']} vez(es) nas últimas 24h.",
            {
                "action_hint": f"Abrir histórico da automação e revisar logs{channel_hint} antes de nova tentativa.",
                "action_code": "show_errors",
                "action_label": "Ver falhas recentes",
                "impact": "Falha recorrente tende a virar ruído operacional e pode exigir correção de causa raiz.",
                "priority": 2,
            },
        )
    return findings


def check_worker_saturation(
    pool_saturated_seconds: float | None,
    max_workers: int,
) -> list[dict[str, Any]]:
    """Gera finding se o pool de workers estiver continuamente saturado."""
    findings: list[dict[str, Any]] = []
    saturated = pool_saturated_seconds or 0.0
    if saturated >= DIAGNOSTIC_WORKER_SATURATION_WARN_SECONDS:
        add_finding(
            findings,
            SEVERITY_WARN,
            "worker",
            (
                f"Pool de workers ({max_workers}) saturado continuamente há "
                f"{round(saturated / 60, 1)} min."
            ),
            {
                "action_hint": "Avaliar aumento de WORKER_MAX_CONCURRENCY ou investigar automações lentas segurando o pool.",
                "action_code": "show_running",
                "action_label": "Ver execuções em andamento",
                "impact": "Concorrência insuficiente atrasa toda a fila, não só a automação lenta que está segurando o pool.",
                "priority": 2,
            },
        )
    return findings


def check_sla_breaches(
    sla_breaches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Gera finding se alguma execução recente estourou o sla_minutes cadastrado."""
    findings: list[dict[str, Any]] = []
    if sla_breaches:
        top = sla_breaches[0]
        add_finding(
            findings,
            SEVERITY_WARN,
            "automation",
            (
                f"{top['automation_name'] or top['exec_id']} excedeu o SLA de "
                f"recuperação cadastrado ({top['sla_minutes']} min)."
            ),
            {
                "action_hint": "Revisar a duração real da execução frente ao SLA cadastrado e investigar degradação de tempo de resposta.",
                "action_code": "show_errors",
                "action_label": "Ver execuções recentes",
                "impact": "SLA estourado pode não ser percebido pela área de negócio antes de virar reclamação.",
                "priority": 2,
            },
        )
    return findings


def check_orphaned_running(
    orphaned_running: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Gera finding para execução RUNNING sem ownership válido do worker atual."""
    findings: list[dict[str, Any]] = []
    if not orphaned_running:
        return findings
    top = orphaned_running[0]
    add_finding(
        findings,
        SEVERITY_ERROR,
        "queue",
        (
            "Execução RUNNING sem ownership válido detectada: "
            f"{top['exec_id']} ({top.get('automation_name') or 'automação desconhecida'})."
        ),
        {
            "action_hint": "Executar recovery do worker e revisar logs antes de novo requeue.",
            "action_code": ACTION_CODE_WORKER_RECOVER,
            "action_label": "Recuperar worker",
            "impact": "Execução pode ter ficado órfã após falha de worker ou troca de instância.",
            "priority": 1,
        },
    )
    return findings


def check_oracle_queue_worker_health(
    oracle_q: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Gera findings se o worker Oracle (TSplus SMB) estiver offline ou sem conexão com o banco."""
    findings: list[dict[str, Any]] = []
    if not oracle_q or not oracle_q.get("enabled"):
        return findings

    machine = str(oracle_q.get("machine") or "").strip()
    target_host = f"servidor TSplus ({machine})" if machine else "servidor TSplus"

    if not oracle_q.get("reachable"):
        add_finding(
            findings,
            SEVERITY_ERROR,
            "oracle_queue",
            "Pasta da fila Oracle (SMB) está inacessível.",
            {
                "action_hint": "Verificar conectividade SMB com o servidor da fila e conferir ORACLE_QUEUE_DIR.",
                "impact": "Todas as automações Oracle em modo queue falharão no pré-flight ou extração.",
                "priority": 1,
            },
        )
        return findings

    if not oracle_q.get("alive"):
        age = oracle_q.get("age_seconds")
        age_txt = f" (heartbeat parado há {age}s)" if age is not None else ""
        add_finding(
            findings,
            SEVERITY_ERROR,
            "oracle_queue",
            f"Worker Oracle do TSplus está offline{age_txt}.",
            {
                "action_hint": (
                    f"Iniciar ou reiniciar INICIAR_WORKER.bat no {target_host} "
                    "e conferir ORACLE_QUEUE_DIR."
                ),
                "impact": "Extrações Oracle não serão atendidas até o retorno do worker; falhas ficarão elegíveis para auto-recuperação.",
                "priority": 1,
            },
        )
        return findings

    if oracle_q.get("oracle_ok") is False:
        add_finding(
            findings,
            SEVERITY_WARN,
            "oracle_queue",
            "Worker Oracle no TSplus reportou perda de conexão com o banco Oracle PRD.",
            {
                "action_hint": (
                    f"Verificar conectividade TCP entre o {target_host} e o banco "
                    "Oracle PRD (ORACLE_CONNECT_STRING / ORACLE_QUEUE_DIR)."
                ),
                "impact": "Consultas na fila podem falhar até a reconexão do worker.",
                "priority": 2,
            },
        )
    return findings
