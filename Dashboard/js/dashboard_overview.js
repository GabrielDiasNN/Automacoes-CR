/**
 * dashboard_overview.js — View "Painel operacional".
 * Renderiza KPIs, insights, gráficos, tabela de controle e portfólio governado.
 */

import { normalizeOverviewPayload, normalizePortfolioHealthPayload } from "./contracts.js";
import { bindActionElements } from "./action_registry.js";
import { setText, refreshIcons } from "./dom_utils.js";

export function createOverviewModule(ctx) {
    const {
        api,
        showToast,
        formatDate,
        formatSeconds,
        getBadgeClass,
        translateStatus,
        escapeHtml,
        ui,
        renderOverviewCharts,
        applyContractCompatibility,
        syncGlobalTestToggle,
    } = ctx;

    async function loadOverview() {
        const [rawOverview, rawPortfolio] = await Promise.all([
            api("/api/system/overview"),
            api("/api/portfolio/health"),
        ]);
        if (!rawOverview) {
            ui.updateConnectionStatus(false);
            return;
        }
        const overview = normalizeOverviewPayload(rawOverview);
        const portfolio = normalizePortfolioHealthPayload(rawPortfolio || {});
        applyContractCompatibility(overview.contract_version || "legacy");
        ui.updateConnectionStatus(true);

        applyOverviewKpis(overview);
        renderOverviewInsights(overview, portfolio.summary || overview.portfolio || {});
        renderOverviewCharts(overview);
        await populateControlTable(overview);
        renderPortfolioTable(portfolio);
        syncGlobalTestToggle(overview.automations || []);
        document.body.dataset.contractVersion = overview.contract_version || "legacy";
        refreshIcons();
    }

    function applyOverviewKpis(overview) {
        const kpis = overview.kpis || {};
        const health = overview.health || {};

        setText("val-total", kpis.active_automations ?? 0);

        const success24 = Number(kpis.success_24h || 0);
        const errors24 = Number(kpis.errors_24h || 0);
        const total24 = success24 + errors24;
        const successRate = total24 > 0 ? ((success24 / total24) * 100).toFixed(1) : "100.0";

        setText("val-success-rate", `${successRate}%`);
        setText("val-errors", errors24);
        setText("val-avg-time", formatSeconds(estimateAverageDuration(overview)));
        setText("trend-success", `${success24} sucesso(s) / 24h`);
        setText("trend-errors", `${errors24} falha(s) / 24h`);
        setText("trend-total", `${overview.scheduler?.jobs_loaded ?? 0} agenda(s)`);
        setText("trend-time", `CPU ${Math.round(health.cpu_usage || 0)}% • RAM ${Math.round(health.ram_usage_percent || 0)}%`);
    }

    function estimateAverageDuration(overview) {
        const recent = Array.isArray(overview.recent) ? overview.recent : [];
        const values = recent
            .map((item) => Number(item.duration_seconds || 0))
            .filter((item) => Number.isFinite(item) && item > 0);
        if (!values.length) return 0;
        return values.reduce((acc, item) => acc + item, 0) / values.length;
    }

    function renderOverviewInsights(overview, portfolioSummary) {
        const topFail = (overview.top_failures || [])[0];
        setText("insight-top-fail", describePrimaryOperationalRisk(overview, portfolioSummary, topFail));
        setText("insight-time-saved", `${((overview.kpis?.success_24h || 0) * 0.2).toFixed(1)}h estimadas no dia`);
        setText("insight-next-window", overview.kpis?.next_window || "Sem janela agendada");
        setText("insight-portfolio-health", describePortfolioSummary(portfolioSummary));
    }

    function describePrimaryOperationalRisk(overview, portfolioSummary, topFail) {
        const baseline = overview?.diagnostics?.operational_baseline || {};
        const baselineStatus = String(baseline.status || "healthy").toLowerCase();
        if (baselineStatus === "incident") {
            return `Base operacional em INCIDENTE${baseline.recommended_action ? ` • ${baseline.recommended_action}` : ""}`;
        }
        const portfolioStatus = String(portfolioSummary?.status || "").toLowerCase();
        if (portfolioStatus === "incident") {
            return `Portfólio INCIDENTE${portfolioSummary?.top_issue ? ` • ${portfolioSummary.top_issue}` : ""}`;
        }
        if (topFail) {
            return `${topFail.automation_name} (${topFail.failures})`;
        }
        if (baselineStatus === "attention") {
            return `Base operacional em atenção${baseline.recommended_action ? ` • ${baseline.recommended_action}` : ""}`;
        }
        if (portfolioStatus === "attention") {
            return `Portfólio em atenção${portfolioSummary?.top_issue ? ` • ${portfolioSummary.top_issue}` : ""}`;
        }
        return "Nenhum risco operacional crítico no momento";
    }

    function describePortfolioSummary(portfolioSummary) {
        const status = String(portfolioSummary?.status || "healthy").toUpperCase();
        const incidents = Number(portfolioSummary?.incident_items || 0);
        const attention = Number(portfolioSummary?.attention_items || 0);
        const drift = Number(portfolioSummary?.drift_items || 0);
        const ungoverned = Number(portfolioSummary?.not_registered_items || 0);

        if (status === "INCIDENT") {
            const parts = [];
            if (incidents > 0) parts.push(`${incidents} incidente(s)`);
            if (ungoverned > 0) parts.push(`${ungoverned} fora do catálogo`);
            if (drift > 0) parts.push(`${drift} divergência(s)`);
            return `INCIDENTE • ${parts.join(" • ") || "Ação imediata"}`;
        }
        if (status === "ATTENTION") {
            const parts = [];
            if (attention > 0) parts.push(`${attention} em atenção`);
            if (drift > 0) parts.push(`${drift} divergência(s)`);
            return `ATENÇÃO • ${parts.join(" • ") || "Governança pendente"}`;
        }
        return "SAUDÁVEL • Catálogo reconciliado com o ambiente operacional";
    }

    async function populateControlTable(overview) {
        const tbody = document.getElementById("control-tbody");
        if (!tbody) return;

        const autos = overview.automations || [];
        const recent = overview.recent || [];
        const latestByAutomation = new Map();

        recent.forEach((item) => {
            if (!latestByAutomation.has(item.automation_id)) {
                latestByAutomation.set(item.automation_id, item);
            }
        });

        if (!autos.length) {
            tbody.innerHTML = "<tr><td colspan=\"5\">Nenhuma automação cadastrada.</td></tr>";
            return;
        }

        tbody.innerHTML = autos.map((auto) => {
            const last = latestByAutomation.get(auto.id);
            const lastStatusCode = auto.last_status || last?.status;
            const lastExecLabel = auto.last_execution_started_at || (last ? formatDate(last.started_at) : "-");
            const lastStatus = lastStatusCode
                ? `<span class="badge ${getBadgeClass(lastStatusCode)}">${translateStatus(lastStatusCode)}</span>`
                : "<span class=\"badge badge-muted\">Sem histórico</span>";
            const nextRun = auto.next_run || "-";
            const executionId = auto.last_execution_id || last?.id || "";
            const executionIdAttr = executionId ? `data-execution-id="${escapeHtml(executionId)}"` : "";
            const operationalState = renderOperationalStateBadge(auto.operational_state);
            const scheduleSummary = auto.schedule_summary ? `<span class="cell-meta">${escapeHtml(auto.schedule_summary)}</span>` : "";
            const lastDetails = auto.last_failure_reason
                ? `<span class="cell-meta">Falha: ${escapeHtml(auto.last_failure_reason)}</span>`
                : auto.last_execution_duration_seconds
                    ? `<span class="cell-meta">Duração: ${formatSeconds(auto.last_execution_duration_seconds)}</span>`
                    : "";
            const nextDetails = auto.next_runs_preview?.length
                ? `<span class="cell-meta">${escapeHtml(auto.next_runs_preview.join(" | "))}</span>`
                : "";

            return `
                <tr>
                    <td><strong>${escapeHtml(auto.name)}</strong>${scheduleSummary}</td>
                    <td>${lastStatus}${operationalState}</td>
                    <td>${lastExecLabel}${lastDetails}</td>
                    <td>${nextRun}${nextDetails}</td>
                    <td>
                        <div class="inline-actions">
                            <button class="btn-icon" data-action="run-auto" data-automation-id="${auto.id}" title="Executar agora"><i data-lucide="play"></i></button>
                            <button class="btn-icon" data-action="open-log" ${executionIdAttr} title="Abrir logs"><i data-lucide="terminal"></i></button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
        bindActionElements(tbody);
    }

    function renderPortfolioTable(portfolio) {
        const tbody = document.getElementById("portfolio-tbody");
        if (!tbody) return;

        const items = Array.isArray(portfolio?.items) ? portfolio.items : [];
        if (!items.length) {
            tbody.innerHTML = "<tr><td colspan=\"6\">Nenhuma automação governada encontrada.</td></tr>";
            return;
        }

        tbody.innerHTML = items.map((item) => {
            const successLabel = item.last_success_at || "Sem sucesso recente";
            const successMeta = item.last_success_age_seconds !== null && item.last_success_age_seconds !== undefined
                ? `<span class="cell-meta">Há ${escapeHtml(formatSeconds(item.last_success_age_seconds))}</span>`
                : (item.last_failure_at ? `<span class="cell-meta">Última falha: ${escapeHtml(item.last_failure_at)}</span>` : "<span class=\"cell-meta\">Sem histórico operacional</span>");
            const lagMeta = item.schedule_lag_seconds
                ? `<span class="cell-meta">Atraso de agenda: ${escapeHtml(formatSeconds(item.schedule_lag_seconds))}</span>`
                : "";
            const dependencyMeta = buildDependencySummary(item.dependency_status || {});
            const governanceMeta = [
                item.docs_status === "complete" ? "Docs completos" : "Docs pendentes",
                item.drift_count ? `${item.drift_count} divergência(s)` : "Sem divergência",
                item.review_status === "delete_candidate" ? "Rever exclusão" : null,
            ].filter(Boolean).join(" • ");
            const canOpenRunbook = item.runbook_path && item.docs_status === "complete";

            return `
                <tr>
                    <td>
                        <strong>${escapeHtml(item.name)}</strong>
                        <span class="cell-meta">${escapeHtml(item.owner_area || "Responsável não definido")}</span>
                    </td>
                    <td>
                        ${renderCriticalityBadge(item.criticality)}
                        ${renderSlaStateBadge(item.sla_state, item.sla_minutes)}
                    </td>
                    <td>
                        ${renderPortfolioHealthBadge(item.health_status)}
                        <span class="cell-meta">${escapeHtml(dependencyMeta)}</span>
                    </td>
                    <td>
                        ${escapeHtml(successLabel)}
                        ${successMeta}
                        ${lagMeta}
                    </td>
                    <td>
                        ${renderDocsStatusBadge(item.docs_status)}
                        ${renderDriftStatusBadge(item.drift_count)}
                        <span class="cell-meta">${escapeHtml(governanceMeta)}</span>
                    </td>
                    <td>
                        <div class="inline-actions">
                            <button class="btn-icon" data-action="open-portfolio-runbook" data-catalog-id="${escapeHtml(item.catalog_id)}" title="Abrir runbook" ${canOpenRunbook ? "" : "disabled"}>
                                <i data-lucide="book-open"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
        bindActionElements(tbody);
    }

    function renderOperationalStateBadge(state) {
        const normalized = String(state || "").toLowerCase();
        if (normalized === "in_progress") {
            return `<span class="cell-meta"><span class="badge badge-warning">Em execução</span></span>`;
        }
        if (normalized === "attention") {
            return `<span class="cell-meta"><span class="badge badge-danger">Atenção</span></span>`;
        }
        if (normalized === "healthy") {
            return `<span class="cell-meta"><span class="badge badge-success">Saudável</span></span>`;
        }
        if (normalized === "paused") {
            return `<span class="cell-meta"><span class="badge badge-muted">Pausada</span></span>`;
        }
        return "";
    }

    function renderCriticalityBadge(criticality) {
        const normalized = String(criticality || "unclassified").toLowerCase();
        const labelMap = {
            critical: "Crítica",
            high: "Alta",
            medium: "Média",
            low: "Baixa",
            unclassified: "Sem classe",
        };
        const classMap = {
            critical: "badge-danger",
            high: "badge-warning",
            medium: "badge-info",
            low: "badge-muted",
            unclassified: "badge-muted",
        };
        return `<span class="badge ${classMap[normalized] || "badge-muted"}">${escapeHtml(labelMap[normalized] || "Sem classe")}</span>`;
    }

    function renderSlaStateBadge(state, slaMinutes) {
        const normalized = String(state || "unknown").toLowerCase();
        const labelBase = Number.isFinite(Number(slaMinutes)) ? `SLA ${slaMinutes} min` : "SLA n/d";
        if (normalized === "breached") {
            return `<span class="badge badge-danger">${escapeHtml(labelBase)} estourado</span>`;
        }
        if (normalized === "recovering") {
            return `<span class="badge badge-warning">${escapeHtml(labelBase)} em recuperação</span>`;
        }
        if (normalized === "ok") {
            return `<span class="badge badge-success">${escapeHtml(labelBase)}</span>`;
        }
        return `<span class="badge badge-muted">${escapeHtml(labelBase)}</span>`;
    }

    function renderPortfolioHealthBadge(status) {
        const normalized = String(status || "unknown").toLowerCase();
        const labelMap = {
            healthy: "Saudável",
            attention: "Atenção",
            breached: "SLA estourado",
            in_progress: "Em execução",
            paused: "Pausada",
            idle: "Sem atividade",
            not_registered: "Sem cadastro",
            not_governed: "Sem manifesto",
        };
        const classMap = {
            healthy: "badge-success",
            attention: "badge-warning",
            breached: "badge-danger",
            in_progress: "badge-info",
            paused: "badge-muted",
            idle: "badge-muted",
            not_registered: "badge-danger",
            not_governed: "badge-danger",
        };
        return `<span class="badge ${classMap[normalized] || "badge-muted"}">${escapeHtml(labelMap[normalized] || "Desconhecido")}</span>`;
    }

    function renderDocsStatusBadge(status) {
        return `<span class="badge ${status === "complete" ? "badge-success" : "badge-warning"}">${status === "complete" ? "Documentação OK" : "Docs pendentes"}</span>`;
    }

    function renderDriftStatusBadge(driftCount) {
        const count = Number(driftCount || 0);
        if (count <= 0) {
            return "<span class=\"badge badge-success\">Sem divergência</span>";
        }
        return `<span class="badge badge-warning">${escapeHtml(String(count))} divergência(s)</span>`;
    }

    function buildDependencySummary(status) {
        const labels = [];
        if (status.oracle && status.oracle !== "not_used") labels.push(`Oracle ${translateDependencyStatus(status.oracle)}`);
        if (status.outlook && status.outlook !== "not_used") labels.push(`Outlook ${translateDependencyStatus(status.outlook)}`);
        if (status.whatsapp && status.whatsapp !== "not_used") labels.push(`WhatsApp ${translateDependencyStatus(status.whatsapp)}`);
        return labels.length ? labels.join(" • ") : "Sem dependência mapeada";
    }

    function translateDependencyStatus(status) {
        switch (String(status || "").toLowerCase()) {
            case "healthy": return "OK";
            case "degraded": return "degradado";
            case "unknown": return "indefinido";
            default: return "n/a";
        }
    }

    async function openPortfolioRunbook(catalogId) {
        if (!catalogId) {
            showToast("Runbook indisponível para esta automação.", "warning");
            return;
        }
        const content = await api(`/api/portfolio/runbook/${encodeURIComponent(catalogId)}`, "GET", null, { responseType: "text" });
        if (!content) return;
        const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const child = window.open(url, "_blank", "noopener");
        if (!child) {
            showToast("Não foi possível abrir o runbook em nova janela.", "warning");
        }
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    }

    return { loadOverview, openPortfolioRunbook };
}
