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
        portfolio: payload?.portfolio || {},
        diagnostics: normalizeDiagnosticsPayload(payload?.diagnostics || {}),
    };
}

export function normalizePortfolioHealthPayload(payload) {
    return {
        generated_at: payload?.generated_at || null,
        summary: payload?.summary || {},
        items: Array.isArray(payload?.items) ? payload.items : [],
    };
}

export function normalizeBeneficiamentoPayload(payload) {
    const periods = payload?.periods || {};
    const normalizedPeriods = {};

    for (const key of ["diario", "mensal"]) {
        const period = periods?.[key] || {};
        normalizedPeriods[key] = {
            key,
            label: period?.label || key,
            available: Boolean(period?.available),
            status: period?.status || period?.quality?.status || "missing",
            updated_at: period?.updated_at || null,
            age_seconds: Number.isFinite(Number(period?.age_seconds)) ? Number(period.age_seconds) : null,
            stale: Boolean(period?.stale),
            source: period?.source || "snapshot_local",
            snapshot_state: period?.snapshot_state || "missing",
            reason_code: period?.reason_code || "snapshot_missing",
            reason_message: period?.reason_message || null,
            recommended_action: period?.recommended_action || null,
            refresh_status: period?.refresh_status || null,
            historico_write_status: period?.historico_write_status || null,
            quality_status: period?.quality_status || null,
            issues: Array.isArray(period?.issues) ? period.issues : [],
            source_files: period?.source_files || {},
            metrics: period?.metrics || {},
            quality: period?.quality || {},
            profile: period?.profile || {},
            rankings: period?.rankings || {},
            highlights: period?.highlights || {},
            oracle: period?.oracle || {},
            snapshot: period?.snapshot || {},
        };
    }

    return {
        generated_at: payload?.generated_at || null,
        default_period: payload?.default_period || "mensal",
        overall: payload?.overall || {},
        comparison: Array.isArray(payload?.comparison) ? payload.comparison : [],
        periods: normalizedPeriods,
        health: {
            generated_at: payload?.health?.generated_at || null,
            snapshot_root: payload?.health?.snapshot_root || null,
            source: payload?.health?.source || "snapshot_local",
            status: payload?.health?.status || "missing",
            reason_code: payload?.health?.reason_code || "snapshot_missing",
            recommended_action: payload?.health?.recommended_action || null,
            periods_total: Number(payload?.health?.periods_total || 0),
            periods_loaded: Number(payload?.health?.periods_loaded || 0),
            findings: Array.isArray(payload?.health?.findings) ? payload.health.findings : [],
            issues: Array.isArray(payload?.health?.issues) ? payload.health.issues : [],
            summary: payload?.health?.summary || {},
            latest_period: payload?.health?.latest_period || null,
            snapshot_files: payload?.health?.snapshot_files || {},
            periods: Array.isArray(payload?.health?.periods) ? payload.health.periods : [],
        },
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
        performance: payload?.performance || { timings_ms: {} },
        trace: payload?.trace || {},
        slo: payload?.slo || { thresholds: {}, breaches: {} },
        operational_baseline: payload?.operational_baseline || {
            status: "healthy",
            attention_count: 0,
            incident_count: 0,
            recommended_action: null,
            metrics: [],
        },
    };
}

export function normalizeSystemHistoryPayload(payload) {
    return {
        generated_at: payload?.generated_at || null,
        hours: Number(payload?.hours || 0),
        points: Number(payload?.points || 0),
        trend_summary: payload?.trend_summary || {},
        items: Array.isArray(payload?.items) ? payload.items : [],
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
