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
} from "./api.js";
import { bindActionElements, registerAction } from "./action_registry.js";
import { escapeHtml, formatSeconds } from "./formatters.js";
import { normalizeBeneficiamentoPayload } from "./contracts.js";
import * as ui from "./ui_manager.js";
import * as ide from "./ide_service.js";
import * as engine from "./execution_engine.js";
import { createExecutionsModule } from "./dashboard_executions.js";
import { createSystemModule } from "./dashboard_system.js";
import { createAutomationsModule } from "./dashboard_automations.js";
import { createBeneficiamentoModule } from "./dashboard_beneficiamento.js";
import { createChartsModule } from "./dashboard_charts.js";
import { createOverviewModule } from "./dashboard_overview.js";
import { createObservabilityModule } from "./dashboard_observability.js";

const EXEC_PER_PAGE = 15;
const EXPECTED_CONTRACT_PREFIX = "2026.05.";
let execPage = 1;
let latestSystemDiagnostics = null;
let contractLockNotified = false;

function _debounce(fn, wait) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); };
}

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
    normalizeBeneficiamentoPayload,
});

const chartsModule = createChartsModule();

const overviewModule = createOverviewModule({
    api,
    showToast,
    formatDate,
    formatSeconds,
    getBadgeClass,
    translateStatus,
    escapeHtml,
    ui,
    renderOverviewCharts: chartsModule.renderOverviewCharts,
    applyContractCompatibility,
    syncGlobalTestToggle,
});

const observabilityModule = createObservabilityModule({
    api,
    ui,
    escapeHtml,
    formatSeconds,
    renderOverviewCharts: chartsModule.renderOverviewCharts,
    applyContractCompatibility,
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

const runAuto = async (id) => {
    const execId = await engine.runAuto(id);
    if (execId) {
        await Promise.all([loadOverview(), loadExecutions(execPage)]);
        engine.openLogModal(execId);
    }
    return execId;
};
const stopExec = async (id) => {
    if (await engine.stopExec(id)) {
        await Promise.all([loadOverview(), loadExecutions(execPage)]);
    }
};

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

    const _debouncedLoadExec = _debounce(() => loadExecutions(1), 300);
    const _textFilters = new Set(["filter-requested-by", "filter-date-from", "filter-date-to"]);

    ["filter-automation", "filter-queue-group", "filter-status", "filter-priority", "filter-requested-by", "filter-date-from", "filter-date-to", "auto-review-filter"].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (id === "auto-review-filter") {
            el.addEventListener("change", () => handleSearch());
        } else if (_textFilters.has(id)) {
            el.addEventListener("input", _debouncedLoadExec);
        } else {
            el.addEventListener("change", () => loadExecutions(1));
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
    registerAction("benef-refresh-live", () => beneficiamentoModule.refreshLive());
    registerAction("open-create-modal", () => openAutomationModal());
    registerAction("refresh-executions", () => loadExecutions(1));
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
        engine.openLogModal(executionId);
    });
    registerAction("pause-auto", (_event, element) => pauseAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("resume-auto", (_event, element) => resumeAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("open-edit-auto", (_event, element) => openAutomationModal(Number(element?.dataset?.automationId || 0)));
    registerAction("clone-auto", (_event, element) => cloneAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("delete-auto", (_event, element) => deleteAuto(Number(element?.dataset?.automationId || 0)));
    registerAction("open-automation-history", (_event, element) => openAutomationHistory(Number(element?.dataset?.automationId || 0)));
    registerAction("open-portfolio-runbook", (_event, element) => overviewModule.openPortfolioRunbook(element?.dataset?.catalogId || ""));
    registerAction("open-json-modal", (_event, element) => ide.openJsonModal(Number(element?.dataset?.automationId || 0), element?.dataset?.automationName || ""));
    registerAction("open-ide-modal", (_event, element) => ide.openIdeModal(Number(element?.dataset?.automationId || 0), element?.dataset?.automationName || ""));
    registerAction("remove-schedule-time", (_event, element) => removeScheduleTime(element?.dataset?.hhmm || ""));
    registerAction("open-log-row", (_event, element) => {
        const executionId = element?.dataset?.executionId;
        if (executionId) {
            engine.openLogModal(executionId);
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
    registerAction("close-log-modal", () => engine.closeLogModal());
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
    return overviewModule.loadOverview();
}

async function loadObservability() {
    return observabilityModule.loadObservability();
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
