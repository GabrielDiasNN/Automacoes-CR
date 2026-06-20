/**
 * Utilitários puros do módulo de automações.
 * Funções sem estado: convertem dados brutos em rótulos/badges para a UI.
 */

export function describeSchedule(rawSchedule) {
    if (!rawSchedule) return "MANUAL";
    try {
        const parsed = typeof rawSchedule === "string" ? JSON.parse(rawSchedule.replace(/'/g, "\"")) : rawSchedule;
        if (parsed.schedule_type === "cron") {
            return `Cron: ${parsed.cron_expression || ""}`;
        }
        if (parsed.schedule_type === "interval") {
            const hasRestriction = Boolean(parsed.start_time || parsed.end_time || (Array.isArray(parsed.days_of_week) && parsed.days_of_week.length > 0));
            return hasRestriction ? `A cada ${parsed.interval_minutes || 0} min (Janela operacional)` : `A cada ${parsed.interval_minutes || 0} min`;
        }
        if (parsed.schedule_type === "once") return "Execução única";
        if (parsed.schedule_type === "daily") return `Diária (${(parsed.times || []).length} horário(s))`;
        if (parsed.schedule_type === "weekly") return `Semanal (${(parsed.times || []).length} horário(s))`;
        if (parsed.schedule_type === "monthly") return `Mensal (${(parsed.days_of_month || []).length} dia(s))`;
        const times = Array.isArray(parsed.times) ? parsed.times : [];
        if (!times.length) return "CONFIGURADA";
        return `${times.length} horário(s)`;
    } catch {
        return "CONFIGURADA";
    }
}

export function inferLegacyType(schedule) {
    if (!schedule) return "manual";
    if (schedule.interval_minutes) return "interval";
    if (schedule.run_at) return "once";
    if (Array.isArray(schedule.days_of_month)) return "monthly";
    if (Array.isArray(schedule.days_of_week) || Array.isArray(schedule.daysOfWeek)) return "weekly";
    if (Array.isArray(schedule.times)) return "daily";
    return "manual";
}

export function buildRiskLabel(auto, governance, escapeHtml) {
    const flags = [];
    if (Number(auto.cooldown_minutes || 0) > 0) flags.push(`CD ${auto.cooldown_minutes}m`);
    if (Number(auto.max_retries || 0) > 0) flags.push(`RT ${auto.max_retries}`);
    if (auto.queue_group) flags.push("GRP");
    const governanceStatus = String(governance?.health_status || "").toLowerCase();
    const governanceDrift = Number(governance?.drift_count || 0);
    const docsStatus = String(governance?.docs_status || "").toLowerCase();
    const reviewStatus = String(governance?.review_status || "").toLowerCase();
    if (governanceStatus === "not_governed" || governanceStatus === "not_registered") flags.push("CAT");
    if (governanceDrift > 0) flags.push(`DRIFT ${governanceDrift}`);
    if (docsStatus && docsStatus !== "complete") flags.push("DOCS");
    if (reviewStatus === "delete_candidate") flags.push("DEL");
    const failures24h = Number(auto.failures_24h || 0);
    const timeouts24h = Number(auto.timeouts_24h || 0);
    const success24h = Number(auto.success_24h || 0);
    if (timeouts24h > 0) flags.push(`TO ${timeouts24h}/24h`);
    if (failures24h > 0) flags.push(`ER ${failures24h}/24h`);
    if (success24h > 0 && failures24h === 0 && timeouts24h === 0) flags.push(`OK ${success24h}/24h`);

    if (!flags.length) return "<span class=\"badge badge-success badge-wrap fleet-risk-badge\">OK</span>";
    const hasFailure = failures24h > 0 || timeouts24h > 0 || governanceDrift > 0 || governanceStatus === "not_governed" || governanceStatus === "not_registered";
    return `<span class="badge ${hasFailure ? "badge-danger" : "badge-warning"} badge-wrap fleet-risk-badge">${flags.join(" • ")}</span>`;
}

export function renderReviewStatusBadge(governance, escapeHtml) {
    const status = String(governance?.review_status || "active").toLowerCase();
    const reasons = Array.isArray(governance?.review_reasons) ? governance.review_reasons : [];
    if (status === "delete_candidate") {
        return `<span class="cell-meta"><span class="badge badge-danger" title="${escapeHtml(reasons[0] || "Candidata à exclusão do cadastro.")}">Revisar exclusão</span></span>`;
    }
    if (status === "attention") {
        return `<span class="cell-meta"><span class="badge badge-warning" title="${escapeHtml(reasons[0] || "Cadastro em atenção operacional.")}">Em revisão</span></span>`;
    }
    return "";
}

export function buildPortfolioLookup(portfolio) {
    const lookup = new Map();
    const items = Array.isArray(portfolio?.items) ? portfolio.items : [];
    items.forEach((item) => {
        if (item?.automation_id) {
            lookup.set(Number(item.automation_id), item);
        }
    });
    return lookup;
}
