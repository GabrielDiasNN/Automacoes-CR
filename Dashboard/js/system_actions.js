export const SYSTEM_ACTIONS = {
    resume_all: {
        path: "/api/automations/control/resume-all",
        method: "POST",
        label: "retomar todas as automações",
    },
    pause_all: {
        path: "/api/automations/control/pause-all",
        method: "POST",
        label: "pausar todas as automações",
    },
    scheduler_reload: {
        path: "/api/system/scheduler/reload",
        method: "POST",
        label: "sincronizar agenda do scheduler",
    },
    worker_wakeup: {
        path: "/api/system/worker/wakeup",
        method: "POST",
        label: "acordar worker para validar fila",
    },
    worker_recover: {
        path: "/api/system/worker/recover",
        method: "POST",
        label: "recuperar Orchestrator e worker",
    },
    checkpoint: {
        path: "/api/system/checkpoint",
        method: "POST",
        label: "executar checkpoint WAL",
    },
    backup: {
        path: "/api/system/backup",
        method: "POST",
        label: "executar backup do banco",
    },
};

export function getSystemActionRequest(action) {
    return SYSTEM_ACTIONS[action] || null;
}
