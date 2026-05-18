/**
 * dashboard.js - Central de Automações v6.3.0
 * SPA operacional do orquestrador.
 */

import { api, showToast, formatDate, getBadgeClass, translateStatus } from "./api.js";
import * as ui from "./ui_manager.js";
import * as ide from "./ide_service.js";
import * as engine from "./execution_engine.js";
import { createExecutionsModule } from "./dashboard_executions.js";
import { createSystemModule } from "./dashboard_system.js";
import { createAutomationsModule } from "./dashboard_automations.js";

const EXEC_PER_PAGE = 15;
let execPage = 1;
let charts = { performance: null, status: null };
let latestSystemDiagnostics = null;

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
});

const systemModule = createSystemModule({
    api,
    showToast,
    formatDate,
    escapeHtml,
    loadOverview,
    loadExecutions: (page) => executionsModule.loadExecutions(page),
    getExecPage: () => execPage,
    setLatestSystemDiagnostics: (value) => { latestSystemDiagnostics = value; },
    getLatestSystemDiagnostics: () => latestSystemDiagnostics,
});

const automationsModule = createAutomationsModule({
    api,
    showToast,
    formatDate,
    getBadgeClass,
    translateStatus,
    escapeHtml,
    getValue,
    setValue,
    setText,
    loadOverview,
    loadExecutions: (page) => executionsModule.loadExecutions(page),
    syncGlobalTestToggle,
});

document.addEventListener("DOMContentLoaded", () => {
    ui.initNavigation();
    bindStaticEvents();
    Promise.all([loadOverview(), loadConfig()]);

    window.addEventListener("view-changed", (e) => {
        const target = e.detail.target;
        if (target === "dashboard") loadOverview();
        if (target === "executions") loadExecutions(1);
        if (target === "automations") loadConfig();
        if (target === "observability") loadOverview();
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
window.openAutomationHistory = (id) => openAutomationHistory(id);
window.loadExecutions = () => loadExecutions(1);
window.requeueExec = (id) => requeueExec(id);

function bindStaticEvents() {
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

async function loadOverview() {
    const overview = await api("/api/system/overview");
    if (!overview) {
        ui.updateConnectionStatus(false);
        return;
    }
    ui.updateConnectionStatus(true);

    applyOverviewKpis(overview);
    renderOverviewInsights(overview);
    renderOverviewCharts(overview);
    await populateControlTable(overview);
    syncGlobalTestToggle(overview.automations || []);
    if (typeof lucide !== "undefined") lucide.createIcons();
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

function renderOverviewInsights(overview) {
    const topFail = (overview.top_failures || [])[0];
    setText("insight-top-fail", topFail ? `${topFail.automation_name} (${topFail.failures})` : "Nenhuma falha registrada em 24h");
    setText("insight-time-saved", `${((overview.kpis?.success_24h || 0) * 0.2).toFixed(1)}h estimadas no dia`);
    setText("insight-next-window", overview.kpis?.next_window || "Sem janela agendada");
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
        values.push(Number((avg / 60).toFixed(2)));
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
        series: [{ name: "Tempo médio (min)", data: values }],
        xaxis: { categories: labels },
        colors: ["#2f6fed"],
        dataLabels: { enabled: false },
        theme: { mode: "dark" },
        tooltip: { theme: "dark" },
        legend: { labels: { colors: "#aab7c7" } },
        yaxis: { labels: { formatter: (v) => `${v.toFixed(1)}m` } },
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
        const lastExecLabel = last ? formatDate(last.started_at) : "-";
        const lastStatus = last
            ? `<span class="badge ${getBadgeClass(last.status)}">${translateStatus(last.status)}</span>`
            : "<span class=\"badge badge-muted\">Sem histórico</span>";
        const nextRun = auto.next_run || "-";
        const openLogAction = last ? `openLogModal('${last.id}')` : "showToast('Sem execução para exibir logs.', 'warning')";

        return `
            <tr>
                <td><strong>${escapeHtml(auto.name)}</strong></td>
                <td>${lastStatus}</td>
                <td>${lastExecLabel}</td>
                <td>${nextRun}</td>
                <td>
                    <div class="inline-actions">
                        <button class="btn-icon" onclick="runAuto(${auto.id})" title="Executar agora"><i data-lucide="play"></i></button>
                        <button class="btn-icon" onclick="${openLogAction}" title="Abrir logs"><i data-lucide="terminal"></i></button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
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

function openAutomationHistory(id) {
    return executionsModule.openAutomationHistory(id);
}

function requeueExec(id) {
    return executionsModule.requeueExec(id);
}

function formatSeconds(value) {
    const sec = Number(value || 0);
    if (!Number.isFinite(sec) || sec <= 0) return "0s";
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const minutes = Math.floor(sec / 60);
    const remain = Math.round(sec % 60);
    return `${minutes}m ${remain}s`;
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
