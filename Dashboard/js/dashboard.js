/**
 * dashboard.js - Central de Automações v6.3.0
 * SPA operacional do orquestrador.
 */

import {
    api,
    showToast,
    formatDate,
    parseDateValue,
    getBadgeClass,
    translateStatus,
    getLastCorrelationId,
    setContractCompatibility,
    safePrompt,
} from "./api.js?v=20260524a";
import { bindActionElements, registerAction } from "./action_registry.js";
import {
    normalizeOverviewPayload,
    normalizePortfolioHealthPayload,
    normalizeSystemHistoryPayload,
} from "./contracts.js";
import * as ui from "./ui_manager.js?v=20260521c";
import * as ide from "./ide_service.js?v=20260521c";
import * as engine from "./execution_engine.js?v=20260521c";
import { createExecutionsModule } from "./dashboard_executions.js";
import { createSystemModule } from "./dashboard_system.js";
import { createAutomationsModule } from "./dashboard_automations.js?v=20260522a";
import { createBeneficiamentoModule } from "./dashboard_beneficiamento.js?v=20260531a";

const EXEC_PER_PAGE = 15;
const EXPECTED_CONTRACT_PREFIX = "2026.05.";
let execPage = 1;
let charts = { performance: null, status: null };
let latestSystemDiagnostics = null;
let contractLockNotified = false;

window.automations = [];

const executionsModule = createExecutionsModule({
    api,
    ui,
    formatDate,
    getBadgeClass,
    translateStatus,
    escapeHtml,
    getValue,
    setExecPage: (value) => { execPage = value; },
    getExecPage: () => execPage,
    execPerPage: EXEC_PER_PAGE,
    stopExec: window.stopExec,
    openLogModal: engine.openLogModal,
    showToast,
    loadOverview,
    bindActionElements,
    safePrompt,
    getLatestSystemDiagnostics: () => latestSystemDiagnostics,
});

const systemModule = createSystemModule({
    api,
    showToast,
    formatDate,
    escapeHtml,
    loadOverview,
    loadExecutions: (page) => executionsModule.loadExecutions(page),
    safePrompt,
    getExecPage: () => execPage,
    setLatestSystemDiagnostics: (value) => { latestSystemDiagnostics = value; },
    getLatestSystemDiagnostics: () => latestSystemDiagnostics,
    getLastCorrelationId,
});

const automationsModule = createAutomationsModule({
    api,
    showToast,
    formatDate,
    parseDateValue,
    getBadgeClass,
    translateStatus,
    escapeHtml,
    getValue,
    setValue,
    setText,
    loadOverview,
    loadExecutions: (page) => executionsModule.loadExecutions(page),
    syncGlobalTestToggle,
    bindActionElements,
});

const beneficiamentoModule = createBeneficiamentoModule({
    api,
    showToast,
    escapeHtml,
    bindActionElements,
});

document.addEventListener("DOMContentLoaded", () => {
    registerStaticActions();
    bindActionElements();
    ui.initNavigation();
    bindStaticEvents();
    Promise.all([loadOverview(), loadConfig()]);

    window.addEventListener("view-changed", (e) => {
        const target = e.detail.target;
        if (target === "dashboard") loadOverview();
        if (target === "executions") loadExecutions(1);
        if (target === "beneficiamento") beneficiamentoModule.loadBeneficiamento();
        if (target === "automations") loadConfig();
        if (target === "observability") loadObservability();
        if (target === "system") loadSystem();
        if (target === "env") ide.loadEnv();
    });
});

window.runAuto = async (id) => {
    const execId = await engine.runAuto(id);
    if (execId) {
        await Promise.all([loadOverview(), loadExecutions(execPage)]);
        engine.openLogModal(execId);
    }
};
window.stopExec = async (id) => {
    if (await engine.stopExec(id)) {
        await Promise.all([loadOverview(), loadExecutions(execPage)]);
    }
};
window.openLogModal = engine.openLogModal;
window.closeLogModal = engine.closeLogModal;
window.openJsonModal = ide.openJsonModal;
window.loadSelectedJsonFile = ide.loadSelectedJsonFile;
window.saveJsonFile = ide.saveJsonFile;
window.openIdeModal = ide.openIdeModal;
window.loadSelectedIdeFile = ide.loadSelectedIdeFile;
window.saveIdeFile = ide.saveIdeFile;
window.saveEnv = ide.saveEnv;
window.openCreateModal = () => openAutomationModal();
window.saveAuto = (event) => saveAutomation(event);
window.addScheduleTime = () => addScheduleTimeFromInput();
window.toggleGlobalTestMode = (enabled) => toggleGlobalTestMode(enabled);
window.callSystemAction = (action) => callSystemAction(action);
window.handleSearch = () => handleSearch();
window.openEditAuto = (id) => openAutomationModal(id);
window.removeScheduleTime = (hhmm) => removeScheduleTime(hhmm);
window.pauseAuto = (id) => pauseAuto(id);
window.resumeAuto = (id) => resumeAuto(id);
window.cloneAuto = (id) => cloneAuto(id);
window.deleteAuto = (id) => deleteAuto(id);
window.openAutomationHistory = (id) => openAutomationHistory(id);
window.loadExecutions = () => loadExecutions(1);
window.requeueExec = (id) => requeueExec(id);
window.goAutoStepNext = () => goAutoStepNext();
window.goAutoStepPrev = () => goAutoStepPrev();
window.applyExecutionPreset = (preset) => applyExecutionPreset(preset);
window.applyExecutionQueueGroup = (group) => applyExecutionQueueGroup(group);
window.applyExecutionPriority = (priority) => applyExecutionPriority(priority);
window.openExecutionHotspot = (automationId) => openExecutionHotspot(automationId);

function bindStaticEvents() {
    const globalTestToggle = document.getElementById("global-test-toggle");
    if (globalTestToggle) {
        globalTestToggle.addEventListener("change", (event) => {
            toggleGlobalTestMode(Boolean(event.target?.checked));
        });
    }

    const autoSearch = document.getElementById("auto-search");
    if (autoSearch) {
        autoSearch.addEventListener("input", () => handleSearch());
    }

    ["filter-automation", "filter-queue-group", "filter-status", "filter-priority", "filter-requested-by", "filter-date-from", "filter-date-to", "auto-review-filter"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("change", () => {
                if (id === "auto-review-filter") {
                    handleSearch();
                    return;
                }
                loadExecutions(1);
            });
        }
    });

    const automationForm = document.getElementById("form-auto");
    if (automationForm) {
        automationForm.addEventListener("submit", (event) => saveAutomation(event));
    }

    document.querySelectorAll(".day-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            automationsModule.toggleScheduleDay(Number(btn.dataset.day));
        });
    });

    const modal = document.getElementById("modal-auto");
    if (modal) {
        modal.addEventListener("close", () => automationsModule.resetScheduleBuilder());
    }

    const scheduleTypeSelect = document.getElementById("f-schedule-type");
    if (scheduleTypeSelect) {
        scheduleTypeSelect.addEventListener("change", () => {
            automationsModule.onScheduleTypeChanged(scheduleTypeSelect.value || "manual");
        });
    }

    ["f-days-of-month", "f-interval-minutes", "f-once-run-at"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("input", () => automationsModule.renderScheduleSummary());
    });
}

function registerStaticActions() {
    registerAction("refresh-page", () => location.reload());
    registerAction("refresh-beneficiamento", () => beneficiamentoModule.loadBeneficiamento());
    registerAction("open-create-modal", () => openAutomationModal());
    registerAction("refresh-executions", () => loadExecutions(1));
    registerAction("benef-period", (_event, element) => beneficiamentoModule.selectPeriod(element?.dataset?.benefPeriod || ""));
    registerAction("execution-preset", (_event, element) => applyExecutionPreset(element?.dataset?.executionPreset || "all"));
    registerAction("execution-filter-group", (_event, element) => applyExecutionQueueGroup(element?.dataset?.queueGroup || ""));
    registerAction("execution-filter-priority", (_event, element) => applyExecutionPriority(element?.dataset?.priority || ""));
    registerAction("execution-open-hotspot", (_event, element) => openExecutionHotspot(Number(element?.dataset?.automationId || 0)));
    registerAction("execution-apply-pressure", (_event, element) => executionsModule.applyPressure(element?.dataset?.queueGroup || "", element?.dataset?.priority || ""));
    registerAction("execution-batch-stop", () => executionsModule.stopVisibleExecutions());
    registerAction("execution-batch-requeue", () => executionsModule.requeueVisibleExecutions());
    registerAction("system-action", (_event, element) => callSystemAction(element?.dataset?.systemAction || ""));
    registerAction("save-env", () => ide.saveEnv());
    registerAction("run-auto", async (_event, element) => {
        const execId = await runAuto(Number(element?.dataset?.automationId || 0));
        if (execId) {
            await Promise.all([loadOverview(), loadConfig(), loadExecutions(execPage)]);
        }
    });
    registerAction("open-log", (_event, element) => {
        const executionId = element?.dataset?.executionId;
        if (!executionId) {
            showToast("Sem execução para exibir logs.", "warning");
            return;
        }
        openLogModal(executionId);
    });
    registerAction("pause-auto", (_event, element) => pauseAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("resume-auto", (_event, element) => resumeAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("open-edit-auto", (_event, element) => openAutomationModal(Number(element?.dataset?.automationId || 0)));
    registerAction("clone-auto", (_event, element) => cloneAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("delete-auto", (_event, element) => deleteAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("open-automation-history", (_event, element) => openAutomationHistory(Number(element?.dataset?.automationId || 0)));
    registerAction("open-portfolio-runbook", (_event, element) => openPortfolioRunbook(element?.dataset?.catalogId || ""));
    registerAction("open-json-modal", (_event, element) => ide.openJsonModal(Number(element?.dataset?.automationId || 0), element?.dataset?.automationName || ""));
    registerAction("open-ide-modal", (_event, element) => ide.openIdeModal(Number(element?.dataset?.automationId || 0), element?.dataset?.automationName || ""));
    registerAction("remove-schedule-time", (_event, element) => removeScheduleTime(element?.dataset?.hhmm || ""));
    registerAction("open-log-row", (_event, element) => {
        const executionId = element?.dataset?.executionId;
        if (executionId) {
            openLogModal(executionId);
        }
    });
    registerAction("stop-exec", async (event, element) => {
        event.stopPropagation();
        const stopped = await stopExec(element?.dataset?.executionId || "");
        if (stopped) {
            await Promise.all([loadOverview(), loadExecutions(execPage), loadSystem()]);
        }
    });
    registerAction("requeue-exec", async (event, element) => {
        event.stopPropagation();
        await requeueExec(element?.dataset?.executionId || "");
    });
    registerAction("close-log-modal", () => closeLogModal());
    registerAction("close-dialog", (_event, element) => {
        const dialogId = element?.dataset?.dialogId;
        if (!dialogId) return;
        document.getElementById(dialogId)?.close();
    });
    registerAction("add-schedule-time", () => addScheduleTimeFromInput());
    registerAction("load-selected-json-file", () => ide.loadSelectedJsonFile());
    registerAction("save-json-file", () => ide.saveJsonFile());
    registerAction("load-selected-ide-file", () => ide.loadSelectedIdeFile());
    registerAction("save-ide-file", () => ide.saveIdeFile());
    registerAction("auto-step-next", () => goAutoStepNext());
    registerAction("auto-step-prev", () => goAutoStepPrev());
}

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
    if (typeof lucide !== "undefined") lucide.createIcons();
}

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
    if (typeof lucide !== "undefined") lucide.createIcons();
}

function applyContractCompatibility(contractVersion) {
    const compatible = String(contractVersion || "").startsWith(EXPECTED_CONTRACT_PREFIX);
    const reason = compatible
        ? ""
        : `Contrato incompatível (API=${contractVersion || "desconhecido"}, esperado=${EXPECTED_CONTRACT_PREFIX}x).`;
    setContractCompatibility(compatible, reason);
    renderContractGuardBanner(contractVersion, compatible);
    if (!compatible && !contractLockNotified) {
        showToast(`${reason} Ações mutáveis foram bloqueadas por segurança.`, "warning");
        contractLockNotified = true;
    }
}

function renderContractGuardBanner(contractVersion, compatible) {
    const topbar = document.querySelector(".top-bar");
    if (!topbar) return;
    let banner = document.getElementById("contract-guard-banner");
    if (!banner) {
        banner = document.createElement("div");
        banner.id = "contract-guard-banner";
        banner.className = "panel";
        banner.style.padding = "8px 12px";
        banner.style.marginTop = "8px";
        topbar.insertAdjacentElement("afterend", banner);
    }
    if (compatible) {
        banner.style.display = "none";
        return;
    }
    banner.style.display = "block";
    banner.innerHTML = `<strong>Contrato incompatível:</strong> API ${escapeHtml(contractVersion || "desconhecido")} · esperado ${escapeHtml(EXPECTED_CONTRACT_PREFIX)}x. Ações mutáveis bloqueadas.`;
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

function renderOverviewCharts(overview) {
    renderPerformanceChart(overview);
    renderStatusChart(overview);
}

function renderPerformanceChart(overview) {
    const container = document.getElementById("chart-performance");
    if (!container || typeof ApexCharts === "undefined" || !isRenderable(container)) return;

    const recent = Array.isArray(overview.recent) ? overview.recent : [];
    const byAutomation = new Map();
    recent.forEach((item) => {
        if (!item.automation_name || !item.duration_seconds) return;
        const key = item.automation_name;
        if (!byAutomation.has(key)) byAutomation.set(key, []);
        byAutomation.get(key).push(Number(item.duration_seconds));
    });

    const labels = [];
    const values = [];
    Array.from(byAutomation.entries()).slice(0, 8).forEach(([name, durations]) => {
        const avg = durations.reduce((acc, d) => acc + d, 0) / durations.length;
        labels.push(name);
        values.push(Number(avg.toFixed(2)));
    });

    if (!labels.length) {
        container.innerHTML = "<div class=\"empty-chart\">Sem dados de performance no período recente.</div>";
        if (charts.performance) {
            charts.performance.destroy();
            charts.performance = null;
        }
        return;
    }

    const options = {
        chart: { type: "bar", height: 280, toolbar: { show: false } },
        series: [{ name: "Tempo médio (s)", data: values }],
        xaxis: { categories: labels },
        colors: ["#2f6fed"],
        dataLabels: { enabled: false },
        theme: { mode: "dark" },
        tooltip: { theme: "dark" },
        legend: { labels: { colors: "#aab7c7" } },
        yaxis: { labels: { formatter: (v) => `${Number(v).toFixed(1)}s` } },
        grid: { borderColor: "#263345" },
    };

    if (charts.performance) charts.performance.destroy();
    charts.performance = new ApexCharts(container, options);
    charts.performance.render();
}

function renderStatusChart(overview) {
    const container = document.getElementById("chart-status");
    if (!container || typeof ApexCharts === "undefined" || !isRenderable(container)) return;

    const breakdown = overview.status_breakdown || {};
    const labels = ["Sucesso", "Erro", "Executando", "Pendente", "Interrompido"];
    const series = [
        Number(breakdown.SUCCESS || 0),
        Number(breakdown.ERROR || 0),
        Number(breakdown.RUNNING || 0),
        Number(breakdown.PENDING || 0),
        Number(breakdown.TERMINATED || 0),
    ];

    if (!series.some((v) => v > 0)) {
        container.innerHTML = "<div class=\"empty-chart\">Sem execuções registradas para compor o gráfico.</div>";
        if (charts.status) {
            charts.status.destroy();
            charts.status = null;
        }
        return;
    }

    const options = {
        chart: { type: "donut", height: 280 },
        labels,
        series,
        colors: ["#32b178", "#e05252", "#2f6fed", "#8b98aa", "#d99a2b"],
        theme: { mode: "dark" },
        tooltip: { theme: "dark" },
        legend: { position: "bottom", labels: { colors: "#aab7c7" } },
        dataLabels: { enabled: true },
        stroke: { width: 1, colors: ["#121a26"] },
    };

    if (charts.status) charts.status.destroy();
    charts.status = new ApexCharts(container, options);
    charts.status.render();
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

async function loadExecutions(page = execPage) {
    return executionsModule.loadExecutions(page);
}

async function loadConfig() {
    return automationsModule.loadConfig();
}

async function loadSystem() {
    return systemModule.loadSystem();
}

async function toggleGlobalTestMode(enabled) {
    const desired = Boolean(enabled);
    const res = await api(`/api/automations/test-mode/global?enabled=${desired}`, "POST");
    if (res) {
        showToast(res.message || "Modo de teste global atualizado.", "success");
        await Promise.all([loadOverview(), loadConfig()]);
    } else {
        const input = document.getElementById("global-test-toggle");
        if (input) input.checked = !desired;
        showToast("Não foi possível atualizar o modo de teste global.", "error");
    }
}

function syncGlobalTestToggle(autos) {
    const input = document.getElementById("global-test-toggle");
    const pill = document.getElementById("test-mode-pill");
    if (!input) return;

    const enabledCount = autos.filter((item) => item.test_mode).length;
    const globalOn = autos.length > 0 && enabledCount === autos.length;
    input.checked = globalOn;

    if (pill) {
        pill.style.display = enabledCount > 0 ? "flex" : "none";
        pill.title = `${enabledCount}/${autos.length || 0} automações em modo sandbox`;
    }
}

async function callSystemAction(action) {
    return systemModule.callSystemAction(action);
}

function handleSearch() {
    return automationsModule.handleSearch();
}

async function openAutomationModal(automationId = null) {
    return automationsModule.openAutomationModal(automationId);
}

function addScheduleTimeFromInput() {
    return automationsModule.addScheduleTimeFromInput();
}

function removeScheduleTime(hhmm) {
    return automationsModule.removeScheduleTime(hhmm);
}

async function saveAutomation(event) {
    return automationsModule.saveAutomation(event);
}

async function pauseAuto(id) {
    return automationsModule.pauseAuto(id);
}

async function resumeAuto(id) {
    return automationsModule.resumeAuto(id);
}

async function cloneAuto(id) {
    return automationsModule.cloneAuto(id);
}

async function deleteAuto(id) {
    return automationsModule.deleteAuto(id);
}

function openAutomationHistory(id) {
    return executionsModule.openAutomationHistory(id);
}

function requeueExec(id) {
    return executionsModule.requeueExec(id);
}

function goAutoStepNext() {
    return automationsModule.goStep(1);
}

function goAutoStepPrev() {
    return automationsModule.goStep(-1);
}

function applyExecutionPreset(preset) {
    return executionsModule.applyPreset(preset);
}

function applyExecutionQueueGroup(group) {
    return executionsModule.applyQueueGroup(group);
}

function applyExecutionPriority(priority) {
    return executionsModule.applyPriority(priority);
}

function openExecutionHotspot(automationId) {
    return executionsModule.openHotspot(automationId);
}

function formatSeconds(value) {
    const sec = Number(value || 0);
    if (!Number.isFinite(sec) || sec <= 0) return "0s";
    return `${sec.toFixed(1)}s`;
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

function translateOperationalSummaryStatus(status) {
    switch (String(status || "").toLowerCase()) {
        case "incident": return "INCIDENTE";
        case "attention": return "ATENÇÃO";
        case "healthy": return "SAUDÁVEL";
        default: return String(status || "DESCONHECIDO").toUpperCase();
    }
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

function isRenderable(element) {
    return Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

function getValue(id) {
    const el = document.getElementById(id);
    return el ? el.value : "";
}
