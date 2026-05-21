export function normalizeOverviewPayload(payload) {
    return {
        contract_version: payload?.contract_version || "legacy",
        generated_at: payload?.generated_at || null,
        version: payload?.version || null,
        schema_version: payload?.schema_version || null,
        kpis: payload?.kpis || {},
        health: payload?.health || {},
        status_breakdown: payload?.status_breakdown || {},
        jobs: Array.isArray(payload?.jobs) ? payload.jobs : [],
        recent: Array.isArray(payload?.recent) ? payload.recent : [],
        automations: Array.isArray(payload?.automations) ? payload.automations : [],
        top_failures: Array.isArray(payload?.top_failures) ? payload.top_failures : [],
        scheduler: payload?.scheduler || {},
        queue: payload?.queue || {},
        diagnostics: normalizeDiagnosticsPayload(payload?.diagnostics || {}),
    };
}

export function normalizeDiagnosticsPayload(payload) {
    return {
        contract_version: payload?.contract_version || "legacy",
        overall_status: payload?.overall_status || "unknown",
        findings: Array.isArray(payload?.findings) ? payload.findings : [],
        operator_actions: Array.isArray(payload?.operator_actions) ? payload.operator_actions : [],
        checks: Array.isArray(payload?.checks) ? payload.checks : [],
        recovery: payload?.recovery || { light_actions: [], strong_actions: [], recommended_action: null },
        database: payload?.database || {},
        scheduler: payload?.scheduler || {},
        worker: payload?.worker || {},
        queue: payload?.queue || {},
        heartbeat: payload?.heartbeat || {},
        failure_hotspots: Array.isArray(payload?.failure_hotspots) ? payload.failure_hotspots : [],
        trace: payload?.trace || {},
        slo: payload?.slo || { thresholds: {}, breaches: {} },
    };
}

export function normalizeExecutionsPayload(payload) {
    return {
        items: Array.isArray(payload?.items) ? payload.items : [],
        total: Number(payload?.total || 0),
        page: Number(payload?.page || 1),
        per_page: Number(payload?.per_page || 20),
        pages: Number(payload?.pages || 1),
    };
}
