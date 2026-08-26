"""Constantes compartilhadas do Orchestrator."""

ORCHESTRATOR_VERSION = "1.0.0"
WORKER_VERSION = "1.0.0"
ORCHESTRATOR_SCHEMA_VERSION = "20260731_02"
ORCHESTRATOR_CONTRACT_VERSION = "2026.05.25.1"

EXECUTION_STATUS_PENDING = "PENDING"
EXECUTION_STATUS_RUNNING = "RUNNING"
EXECUTION_STATUS_SUCCESS = "SUCCESS"
# Entregue com degradação de canal secundário (ex.: e-mail OK, WhatsApp falhou).
# Conta como entregue para SLA/disponibilidade, mas não é sucesso pleno e não
# dispara alerta crítico.
EXECUTION_STATUS_PARTIAL = "PARTIAL"
EXECUTION_STATUS_ERROR = "ERROR"
EXECUTION_STATUS_TIMEOUT = "TIMEOUT"
EXECUTION_STATUS_TERMINATED = "TERMINATED"
EXECUTION_STATUS_FAILED_BY_REBOOT = "FAILED_BY_REBOOT"
EXECUTION_STATUS_REQUEUED = "REQUEUED"
# PENDING cujo tempo de fila (`queued_at`) ultrapassou
# DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS antes de o queue_group liberar —
# ver `claim_next_task`. Terminal, mas fora de EXECUTION_QUEUEABLE_SOURCE via
# auto-retry: `auto_retry_transient_failures` só varre ERROR/TIMEOUT, então um
# tick expirado nunca é reenfileirado automaticamente. Requeue manual continua
# possível (EXPIRED entra em EXECUTION_TERMINAL_STATUSES).
EXECUTION_STATUS_EXPIRED = "EXPIRED"

EXECUTION_ACTIVE_STATUSES = {
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
}

EXECUTION_TERMINAL_STATUSES = {
    EXECUTION_STATUS_SUCCESS,
    EXECUTION_STATUS_PARTIAL,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_TIMEOUT,
    EXECUTION_STATUS_TERMINATED,
    EXECUTION_STATUS_FAILED_BY_REBOOT,
    EXECUTION_STATUS_EXPIRED,
}

# Status que representam entrega efetiva do resultado principal (contam como
# disponibilidade/sucesso no SLA). PARTIAL = entregue com canal secundário degradado.
EXECUTION_DELIVERED_STATUSES = {
    EXECUTION_STATUS_SUCCESS,
    EXECUTION_STATUS_PARTIAL,
}

# Status terminais que representam falha (todo terminal que não foi entregue,
# exceto EXPIRED). Fonte única para métricas, scoring e portfólio: listas
# hardcoded divergentes faziam FAILED_BY_REBOOT ser contado em uns lugares e
# ignorado em outros (#17). EXPIRED é excluído deliberadamente: representa um
# tick descartado por congestionamento de queue_group ANTES de qualquer
# tentativa de execução — não uma automação que rodou e falhou. Contá-lo aqui
# faria scoring, métricas diárias e portfólio penalizarem uma automação
# saudável pelo simples fato de compartilhar queue_group com outra mais lenta.
EXECUTION_FAILED_STATUSES = (
    EXECUTION_TERMINAL_STATUSES
    - EXECUTION_DELIVERED_STATUSES
    - {EXECUTION_STATUS_EXPIRED}
)

EXECUTION_QUEUEABLE_SOURCE_STATUSES = EXECUTION_TERMINAL_STATUSES | {
    EXECUTION_STATUS_REQUEUED,
}

EXECUTION_ALLOWED_STATUSES = (
    EXECUTION_ACTIVE_STATUSES
    | EXECUTION_TERMINAL_STATUSES
    | {EXECUTION_STATUS_REQUEUED}
)

PRIORITY_HIGH = "HIGH"
PRIORITY_NORMAL = "NORMAL"
PRIORITY_LOW = "LOW"
EXECUTION_ALLOWED_PRIORITIES = {PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW}

SEVERITY_INFO = "INFO"
SEVERITY_WARN = "WARN"
SEVERITY_ERROR = "ERROR"
DIAGNOSTIC_SEVERITIES = {SEVERITY_INFO, SEVERITY_WARN, SEVERITY_ERROR}
BASELINE_STATUS_HEALTHY = "healthy"
BASELINE_STATUS_ATTENTION = "attention"
BASELINE_STATUS_INCIDENT = "incident"
OPERATIONAL_BASELINE_STATUSES = {
    BASELINE_STATUS_HEALTHY,
    BASELINE_STATUS_ATTENTION,
    BASELINE_STATUS_INCIDENT,
}

DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS = 900
# Mesmo teto usado por `operational_baseline` para escalar a fila pendente de
# ATTENTION para INCIDENT. Reusado por `claim_next_task` (H2) como janela de
# validade de uma PENDING presa atrás de queue_group: quando o dashboard já
# marcaria a fila como INCIDENT, o tick correspondente é descartado como
# EXPIRED em vez de rodar horas depois como se fosse um disparo novo.
DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS = (
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS * 2
)
DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS = 3600
DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS = 300
DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS = 120
DIAGNOSTIC_WAL_ELEVATED_MB = 64
DIAGNOSTIC_WAL_CRITICAL_MB = 256
DIAGNOSTIC_FAILURE_HOTSPOT_THRESHOLD = 3
DIAGNOSTIC_DEFAULT_MAX_RUNTIME_MINUTES = 30
DIAGNOSTIC_WORKER_SATURATION_WARN_SECONDS = 300


ACTION_CODE_BACKUP = "backup"
ACTION_CODE_CHECKPOINT = "checkpoint"
ACTION_CODE_PURGE = "purge"
ACTION_CODE_SCHEDULER_RELOAD = "scheduler_reload"
ACTION_CODE_WORKER_WAKEUP = "worker_wakeup"
ACTION_CODE_WORKER_RECOVER = "worker_recover"
ACTION_CODE_PAUSE_ALL = "pause_all"
ACTION_CODE_RESUME_ALL = "resume_all"

RECOVERY_ACTION_NONE = "NONE"
RECOVERY_ACTION_REQUEUE_MANUAL = "REQUEUE_MANUAL"
RECOVERY_ACTION_REQUEUED_TO_NEW_EXECUTION = "REQUEUED_TO_NEW_EXECUTION"
RECOVERY_ACTION_REQUEUE_IF_SAFE = "REQUEUE_IF_SAFE"
RECOVERY_ACTION_REAUTHENTICATE_WHATSAPP_SESSION = "REAUTHENTICATE_WHATSAPP_SESSION"
RECOVERY_ACTION_REVIEW_AUTOMATION_REGISTRY = "REVIEW_AUTOMATION_REGISTRY"
RECOVERY_ACTION_REVIEW_CHANNEL_STATE_BEFORE_REQUEUE = (
    "REVIEW_CHANNEL_STATE_BEFORE_REQUEUE"
)
RECOVERY_ACTION_REVIEW_LOGS_AND_OPTIONALLY_REQUEUE = (
    "REVIEW_LOGS_AND_OPTIONALLY_REQUEUE"
)
RECOVERY_ACTION_REVIEW_LOGS_BEFORE_REQUEUE = "REVIEW_LOGS_BEFORE_REQUEUE"
RECOVERY_ACTION_REVIEW_TIMEOUT_AND_REQUEUE = "REVIEW_TIMEOUT_AND_REQUEUE"
RECOVERY_ACTION_REVIEW_WORKER_LOGS = "REVIEW_WORKER_LOGS"

FAILURE_REASON_AUTOMATION_NOT_FOUND = "AUTOMATION_NOT_FOUND"
FAILURE_REASON_AUTOMATION_SCRIPT_FAILED = "AUTOMATION_SCRIPT_FAILED"
FAILURE_REASON_CHANNEL_DELIVERY_FAILED = "CHANNEL_DELIVERY_FAILED"
FAILURE_REASON_DATA_EXTRACTION_FAILED = "DATA_EXTRACTION_FAILED"
FAILURE_REASON_INTERNAL_WORKER_ERROR = "INTERNAL_WORKER_ERROR"
FAILURE_REASON_MAX_RUNTIME_EXCEEDED = "MAX_RUNTIME_EXCEEDED"
FAILURE_REASON_ORCHESTRATOR_REBOOT = "ORCHESTRATOR_REBOOT"
FAILURE_REASON_PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
FAILURE_REASON_QUEUE_GROUP_WINDOW_EXPIRED = "QUEUE_GROUP_WINDOW_EXPIRED"
FAILURE_REASON_TELEMETRY_ABANDONED = "TELEMETRY_ABANDONED"
FAILURE_REASON_USER_TERMINATED = "USER_TERMINATED"
FAILURE_REASON_WHATSAPP_SESSION_EXPIRED = "WHATSAPP_SESSION_EXPIRED"

# Mapeamento semântico de exit codes das automações:
# exit_code -> (status, failure_reason, recovery_action)
#
# CONTRATO: todo código emitido por um `run.ps1` precisa constar aqui. Códigos
# ausentes caem no default ERROR/EXIT_CODE_<n> de `classify_process_result`, o
# que transforma desfecho normal em falso incidente. O teste
# `tests/test_exit_code_contract.py` varre os `run.ps1` e falha se algum código
# emitido não estiver mapeado.
EXIT_CODE_MAP = {
    0: (EXECUTION_STATUS_SUCCESS, None, RECOVERY_ACTION_NONE),
    # Erro fatal genérico do script (bloco catch da automação) e propagação do
    # exit 1 de lib/Send-WhatsApp.ps1 por parâmetro de destino ausente.
    1: (
        EXECUTION_STATUS_ERROR,
        FAILURE_REASON_AUTOMATION_SCRIPT_FAILED,
        RECOVERY_ACTION_REVIEW_LOGS_AND_OPTIONALLY_REQUEUE,
    ),
    # Idempotência: nada mudou desde o último envio, nada a notificar.
    2: (EXECUTION_STATUS_SUCCESS, None, RECOVERY_ACTION_NONE),
    # Falha DEFINITIVA na obtenção dos dados (extração Oracle após 3 tentativas
    # ou script Python de extração). Nenhum entregável foi produzido: é falha,
    # não sucesso. Como o state não é commitado nesse caminho, o requeue é
    # seguro e não duplica entrega.
    3: (
        EXECUTION_STATUS_ERROR,
        FAILURE_REASON_DATA_EXTRACTION_FAILED,
        RECOVERY_ACTION_REQUEUE_IF_SAFE,
    ),
    # Falha na orquestração, na geração do artefato ou no envio do canal
    # principal. State não commitado — o lote é reavaliado na próxima execução.
    4: (
        EXECUTION_STATUS_ERROR,
        FAILURE_REASON_AUTOMATION_SCRIPT_FAILED,
        RECOVERY_ACTION_REVIEW_LOGS_AND_OPTIONALLY_REQUEUE,
    ),
    # Pre-flight reprovado (Python/Oracle/paths). O ambiente está quebrado:
    # requeue cego repete a falha, então exige revisão antes.
    9: (
        EXECUTION_STATUS_ERROR,
        FAILURE_REASON_PREFLIGHT_FAILED,
        RECOVERY_ACTION_REVIEW_LOGS_BEFORE_REQUEUE,
    ),
    21: (
        EXECUTION_STATUS_ERROR,
        FAILURE_REASON_WHATSAPP_SESSION_EXPIRED,
        RECOVERY_ACTION_REAUTHENTICATE_WHATSAPP_SESSION,
    ),
    # WhatsApp adiado por lock ativo ou cooldown da sessão hub-global
    # compartilhada. É comportamento normal, não falha: o state não é commitado
    # e o mesmo lote é reavaliado no próximo ciclo. Classificar como ERROR
    # geraria alerta e poluiria os hotspots de falha a cada disputa de sessão.
    22: (EXECUTION_STATUS_SUCCESS, None, RECOVERY_ACTION_NONE),
    # Falha apenas no canal secundário (WhatsApp): o entregável principal
    # (e-mail/artefatos) foi concluído. Classificado como PARTIAL para não gerar
    # alerta crítico diário nem penalizar o SLA, preservando o motivo do canal.
    # Em automação de canal ÚNICO esse pressuposto não vale e
    # `classify_process_result_for_channels` rebaixa o desfecho para ERROR.
    24: (
        EXECUTION_STATUS_PARTIAL,
        FAILURE_REASON_CHANNEL_DELIVERY_FAILED,
        RECOVERY_ACTION_REVIEW_CHANNEL_STATE_BEFORE_REQUEUE,
    ),
    # Simétrico ao 24, para o canal e-mail degradado.
    25: (
        EXECUTION_STATUS_PARTIAL,
        FAILURE_REASON_CHANNEL_DELIVERY_FAILED,
        RECOVERY_ACTION_REVIEW_CHANNEL_STATE_BEFORE_REQUEUE,
    ),
}

# Exit codes que sinalizam degradação de UM canal de entrega específico.
#
# O contrato de PARTIAL pressupõe que o OUTRO canal entregou — é o que justifica
# não gerar alerta crítico nem penalizar o SLA. Quando o canal degradado é o
# único que a automação possui, essa premissa é falsa: nada foi entregue, e o
# desfecho correto é ERROR. Ver `classify_process_result_for_channels`.
DEGRADED_CHANNEL_EXIT_CODES = {
    24: "whatsapp",
    25: "email",
}

# Limite máximo de caracteres de logs persistidos no banco de dados para evitar inchaço
MAX_DB_LOGS_CHARS = 200_000
