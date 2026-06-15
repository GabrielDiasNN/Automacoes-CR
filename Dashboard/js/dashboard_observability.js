/**
 * dashboard_observability.js — View "Observabilidade".
 * Renderiza pulso operacional, achados, hotspots e histórico do ambiente.
 */

import {
    normalizeOverviewPayload,
    normalizePortfolioHealthPayload,
    normalizeSystemHistoryPayload,
} from "./contracts.js";
import { setText, refreshIcons } from "./dom_utils.js";

export function createObservabilityModule(ctx) {
    const {
        api,
        ui,
        escapeHtml,
        formatSeconds,
        renderOverviewCharts,
        applyContractCompatibility,
    } = ctx;

    async function loadObservability() {
        const [rawOverview, rawPortfolio, rawHistory] = await Promise.all([
            api("/api/system/overview"),
            api("/api/portfolio/health"),
            api("/api/system/history?hours=6"),
        ]);
        if (!rawOverview) {
            ui.updateConnectionStatus(false);
            return;
        }

        const overview = normalizeOverviewPayload(rawOverview);
        const portfolio = normalizePortfolioHealthPayload(rawPortfolio || {});
        const history = normalizeSystemHistoryPayload(rawHistory || {});
        ui.updateConnectionStatus(true);

        applyContractCompatibility(overview.contract_version || "legacy");
        renderOverviewCharts(overview);
        renderObservabilityPulse(overview, portfolio.summary || {});
        renderObservabilityFindings(overview.diagnostics || {});
        renderObservabilityHotspots(overview, portfolio);
        renderObservabilityHistory(history);
        refreshIcons();
    }

    function renderObservabilityPulse(overview, portfolioSummary) {
        const diagnostics = overview?.diagnostics || {};
        const heartbeatAge = diagnostics?.heartbeat?.last_ping_age_seconds;
        const oldestPending = diagnostics?.queue?.oldest_pending || {};
        const oldestRunning = diagnostics?.queue?.oldest_running || {};

        setText("obs-heartbeat-age", heartbeatAge == null ? "-" : formatSeconds(heartbeatAge));
        setText("obs-heartbeat-state", diagnostics?.worker?.is_alive ? "Processador online" : "Processador sem heartbeat");
        setText("obs-pending-age", oldestPending?.exec_id ? formatSeconds(oldestPending.age_seconds || 0) : "-");
        setText("obs-pending-state", oldestPending?.automation_name ? `${oldestPending.automation_name}` : "Sem pendências envelhecidas");
        setText("obs-running-age", oldestRunning?.exec_id ? formatSeconds(oldestRunning.age_seconds || 0) : "-");
        setText("obs-running-state", oldestRunning?.automation_name ? `${oldestRunning.automation_name}` : "Sem execução longa");
        setText("obs-review-count", Number(portfolioSummary?.delete_candidate_items || 0));
        setText("obs-review-state", `${Number(portfolioSummary?.attention_items || 0)} item(ns) em atenção`);
    }

    function renderObservabilityFindings(diagnostics) {
        const container = document.getElementById("obs-findings");
        if (!container) return;
        const findings = Array.isArray(diagnostics?.findings) ? diagnostics.findings : [];
        if (!findings.length) {
            container.innerHTML = `<div class="finding-card info"><span class="badge badge-success">OK</span><div><strong>Sem achados críticos</strong><p>O ambiente operacional está sem alertas ativos relevantes.</p></div></div>`;
            return;
        }

        container.innerHTML = findings.slice(0, 6).map((item) => `
            <article class="finding-card ${escapeHtml(String(item.severity || "info").toLowerCase())}">
                <span class="badge ${String(item.severity || "").toUpperCase() === "ERROR" ? "badge-danger" : "badge-warning"}">${escapeHtml(item.severity || "WARN")}</span>
                <div>
                    <strong>${escapeHtml(item.component || "sistema")}</strong>
                    <p>${escapeHtml(item.message || "-")}</p>
                    <small>${escapeHtml(item.action_hint || "Revisar investigação operacional.")}</small>
                </div>
            </article>
        `).join("");
    }

    function renderObservabilityHotspots(overview, portfolio) {
        const container = document.getElementById("obs-hotspots");
        if (!container) return;
        const hotspots = Array.isArray(overview?.diagnostics?.failure_hotspots) ? overview.diagnostics.failure_hotspots : [];
        const queueGroups = overview?.diagnostics?.queue?.active_by_group || {};
        const reviewItems = (Array.isArray(portfolio?.items) ? portfolio.items : []).filter((item) => item.review_status === "delete_candidate").slice(0, 3);

        const hotspotHtml = hotspots.length
            ? hotspots.slice(0, 4).map((item) => `<small>${escapeHtml(item.automation_name || "Automação")} · ${escapeHtml(String(item.failures_24h || 0))} falha(s)/24h</small>`).join("")
            : "<small>Sem foco de falha no período recente.</small>";
        const groupEntries = Object.entries(queueGroups).slice(0, 4);
        const groupHtml = groupEntries.length
            ? groupEntries.map(([group, count]) => `<small>${escapeHtml(group)} · ${escapeHtml(String(count))} ativa(s)</small>`).join("")
            : "<small>Sem grupos operacionais sob pressão.</small>";
        const reviewHtml = reviewItems.length
            ? reviewItems.map((item) => `<small>${escapeHtml(item.name)} · ${escapeHtml((item.review_reasons || [])[0] || "Revisar cadastro.")}</small>`).join("")
            : "<small>Sem candidatas imediatas à exclusão.</small>";

        container.innerHTML = `
            <article class="contract-card">
                <h4>Focos de falha</h4>
                ${hotspotHtml}
            </article>
            <article class="contract-card">
                <h4>Grupos ativos</h4>
                ${groupHtml}
            </article>
            <article class="contract-card">
                <h4>Revisão de cadastro</h4>
                ${reviewHtml}
            </article>
        `;
    }

    function renderObservabilityHistory(history) {
        const tbody = document.getElementById("obs-history-tbody");
        if (!tbody) return;
        const items = Array.isArray(history?.items) ? history.items : [];
        if (!items.length) {
            tbody.innerHTML = "<tr><td colspan=\"6\">Sem histórico operacional disponível.</td></tr>";
            return;
        }

        tbody.innerHTML = items.slice(0, 8).map((item) => `
            <tr>
                <td>${escapeHtml(item.timestamp || "-")}</td>
                <td>P ${escapeHtml(formatSeconds(item.oldest_pending_age_seconds || 0))} · R ${escapeHtml(formatSeconds(item.oldest_running_age_seconds || 0))}</td>
                <td>${item.worker_last_ping_age_seconds == null ? "-" : escapeHtml(formatSeconds(item.worker_last_ping_age_seconds))}</td>
                <td>${escapeHtml(String(item.wal_size_mb || 0))} MB</td>
                <td><span class="badge ${item.baseline_status === "incident" ? "badge-danger" : item.baseline_status === "attention" ? "badge-warning" : "badge-success"}">${escapeHtml(translateOperationalSummaryStatus(item.baseline_status || "healthy"))}</span></td>
                <td>${Array.isArray(item.failure_hotspots) && item.failure_hotspots.length ? escapeHtml(item.failure_hotspots.join(" | ")) : "-"}</td>
            </tr>
        `).join("");
    }

    function translateOperationalSummaryStatus(status) {
        switch (String(status || "").toLowerCase()) {
            case "incident": return "INCIDENTE";
            case "attention": return "ATENÇÃO";
            case "healthy": return "SAUDÁVEL";
            default: return String(status || "DESCONHECIDO").toUpperCase();
        }
    }

    return { loadObservability };
}
