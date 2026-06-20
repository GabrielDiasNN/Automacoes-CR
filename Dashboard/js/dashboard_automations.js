import { refreshIcons } from "./dom_utils.js";
import {
    buildPortfolioLookup,
    buildRiskLabel,
    describeSchedule,
    renderReviewStatusBadge,
} from "./automations-helpers.js";
import { createReviewModule } from "./automations-review.js";
import { createScheduleModule } from "./automations-schedule.js";

export function createAutomationsModule(ctx) {
    const {
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
        loadExecutions,
        syncGlobalTestToggle,
        bindActionElements,
    } = ctx;

    const state = {
        cachedAutomations: [],
        cachedJobs: [],
        isSavingAutomation: false,
        scheduleTimes: [],
        scheduleDays: new Set(),
        scheduleType: "manual",
        hasInitializedEvents: false,
        hasInitializedActionMenuEvents: false,
        currentTabId: "tab-identification",
        latestSchedulePreview: null,
        currentAutomationContext: null,
        latestAutomationPreflight: null,
        openActionMenuAutomationId: null,
        cachedPortfolioByAutomation: new Map(),
    };

    const TAB_ORDER = ["tab-identification", "tab-schedule", "tab-execution", "tab-review"];

    const reviewCtx = { escapeHtml, translateStatus, getValue };
    const review = createReviewModule(reviewCtx, state);

    const scheduleCtx = { api, showToast, getValue, setValue, refreshIcons, bindActionElements };
    const schedule = createScheduleModule(scheduleCtx, state, review.refreshReviewPanel);

    function initTabsAndEvents() {
        if (state.hasInitializedEvents) return;
        state.hasInitializedEvents = true;

        // Abas do modal (exclusivo: dashboard.js não gerencia abas internas do modal)
        const tabButtons = document.querySelectorAll(".modal-tabs .tab-btn");
        tabButtons.forEach((btn) => {
            btn.addEventListener("click", () => {
                const tabId = btn.dataset.tab;
                switchTab(tabId);
            });
        });

        // Presets Cron (exclusivo: dashboard.js não conhece .cron-preset)
        const cronPresets = document.querySelectorAll(".cron-preset");
        cronPresets.forEach((preset) => {
            preset.addEventListener("click", () => {
                const cronVal = preset.dataset.cron;
                setValue("f-cron-expression", cronVal);
                schedule.renderScheduleSummary();
            });
        });

        // Checkbox de restrição de janela (exclusivo: controle novo, não existia antes)
        const restrictedCheckbox = document.getElementById("f-interval-restricted");
        const restrictionPanel = document.getElementById("interval-restriction-panel");
        if (restrictedCheckbox && restrictionPanel) {
            restrictedCheckbox.addEventListener("change", (e) => {
                restrictionPanel.style.display = e.target.checked ? "block" : "none";
                schedule.renderScheduleSummary();
            });
        }

        // Campos novos que dashboard.js não cobre (f-cron-expression, horários da janela)
        const cronInput = document.getElementById("f-cron-expression");
        if (cronInput) {
            cronInput.addEventListener("input", () => schedule.renderScheduleSummary());
        }

        const intervalStartInput = document.getElementById("f-interval-start-time");
        if (intervalStartInput) {
            intervalStartInput.addEventListener("change", () => schedule.renderScheduleSummary());
        }

        const intervalEndInput = document.getElementById("f-interval-end-time");
        if (intervalEndInput) {
            intervalEndInput.addEventListener("change", () => schedule.renderScheduleSummary());
        }

        const intervalAnchorInput = document.getElementById("f-interval-anchor-time");
        if (intervalAnchorInput) {
            intervalAnchorInput.addEventListener("change", () => schedule.renderScheduleSummary());
        }

        // NOTA: .day-btn, f-schedule-type, f-interval-minutes, f-days-of-month e
        // f-once-run-at são gerenciados pelo dashboard.js (bindStaticEvents).
        // NÃO registrar aqui para evitar duplo disparo que cancela o efeito.
    }

    function switchTab(tabId) {
        state.currentTabId = tabId;
        const tabButtons = document.querySelectorAll(".modal-tabs .tab-btn");
        tabButtons.forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.tab === tabId);
        });

        const tabContents = document.querySelectorAll(".modal-body .tab-content");
        tabContents.forEach((content) => {
            content.classList.toggle("active", content.id === tabId);
        });
        if (tabId === "tab-review") {
            review.refreshReviewPanel();
        }
        updateStepButtons();
    }

    function updateStepButtons() {
        const prevBtn = document.querySelector('[data-action="auto-step-prev"]');
        const nextBtn = document.querySelector('[data-action="auto-step-next"]');
        const saveBtn = document.querySelector('#form-auto button[type="submit"]');
        const currentIndex = TAB_ORDER.indexOf(state.currentTabId);
        if (prevBtn) prevBtn.disabled = currentIndex <= 0;
        if (nextBtn) {
            nextBtn.disabled = currentIndex >= TAB_ORDER.length - 1;
            nextBtn.style.display = currentIndex >= TAB_ORDER.length - 1 ? "none" : "inline-flex";
        }
        if (saveBtn) {
            saveBtn.textContent = currentIndex >= TAB_ORDER.length - 1 ? "Salvar automação" : "Ir para revisão";
        }
    }

    async function loadConfig() {
        initActionMenuEvents();
        const [autos, jobs, portfolio] = await Promise.all([
            api("/api/automations/all"),
            api("/api/system/scheduler/jobs"),
            api("/api/portfolio/health"),
        ]);

        if (!autos) return;

        state.cachedAutomations = autos;
        state.cachedJobs = jobs || [];
        state.cachedPortfolioByAutomation = buildPortfolioLookup(portfolio);
        window.automations = autos;

        refreshAutomationFilterOptions(autos);
        renderAutomationTable(getFilteredAutomations(), jobs || []);
        syncGlobalTestToggle(autos);

        refreshIcons();
    }

    function refreshAutomationFilterOptions(autos) {
        const select = document.getElementById("filter-automation");
        if (!select) return;

        const currentValue = select.value;
        const options = ["<option value=\"\">TODOS OS ROBÔS</option>"];
        autos.forEach((auto) => {
            options.push(`<option value="${auto.id}">${escapeHtml(auto.name)}</option>`);
        });
        select.innerHTML = options.join("");
        select.value = currentValue || "";

        const queueGroupSelect = document.getElementById("filter-queue-group");
        if (queueGroupSelect) {
            const currentGroupValue = queueGroupSelect.value;
            const groups = Array.from(
                new Set(
                    autos
                        .map((auto) => String(auto.queue_group || "").trim())
                        .filter((item) => item)
                )
            ).sort((a, b) => a.localeCompare(b, "pt-BR"));
            const groupOptions = ["<option value=\"\">TODOS OS GRUPOS</option>"];
            groups.forEach((group) => {
                groupOptions.push(`<option value="${escapeHtml(group)}">${escapeHtml(group)}</option>`);
            });
            queueGroupSelect.innerHTML = groupOptions.join("");
            queueGroupSelect.value = currentGroupValue || "";
        }
    }

    function renderAutomationTable(autos, jobs) {
        const tbody = document.getElementById("fleet-tbody");
        if (!tbody) return;
        closeActionMenu();

        if (!autos.length) {
            tbody.innerHTML = "<tr><td colspan=\"8\">Nenhuma automação cadastrada.</td></tr>";
            return;
        }

        const nextRunByAuto = new Map();
        jobs.forEach((job) => {
            if (!job.automation_id || !job.next_run_time) return;
            const candidate = parseDateValue(job.next_run_time);
            if (!candidate) return;
            const current = nextRunByAuto.get(job.automation_id);
            if (!current || candidate.getTime() < current.getTime()) {
                nextRunByAuto.set(job.automation_id, candidate);
            }
        });

        tbody.innerHTML = autos.map((auto) => {
            const scheduleLabel = auto.schedule_summary || describeSchedule(auto.schedule);
            const nextRun = auto.next_run || formatDate(nextRunByAuto.get(auto.id)) || "-";
            const escapedName = escapeHtml(auto.name);
            const governance = state.cachedPortfolioByAutomation.get(auto.id);
            const riskLabel = buildRiskLabel(auto, governance, escapeHtml);
            const reviewBadge = renderReviewStatusBadge(governance, escapeHtml);
            const lastLabel = auto.last_status ? `<span class="badge ${getBadgeClass(auto.last_status)}">${translateStatus(auto.last_status)}</span>` : "<span class=\"badge badge-muted\">Sem histórico</span>";
            const lastMeta = auto.last_execution_started_at
                ? `<span class="cell-meta">${escapeHtml(auto.last_execution_started_at)}</span>`
                : "<span class=\"cell-meta\">Sem execução recente</span>";
            const lastReason = auto.last_failure_reason
                ? `<span class="cell-meta">Falha: ${escapeHtml(auto.last_failure_reason)}</span>`
                : "";
            const pauseResumeBtn = auto.enabled
                ? `<button class="btn-icon" type="button" data-action="pause-auto" data-automation-id="${auto.id}" title="Pausar"><i data-lucide="pause" size="14"></i></button>`
                : `<button class="btn-icon" type="button" data-action="resume-auto" data-automation-id="${auto.id}" title="Retomar"><i data-lucide="play-circle" size="14"></i></button>`;
            const escapedNameAttr = escapeHtml(String(auto.name || ""));

            return `
            <tr>
                <td>
                    <div class="auto-info">
                        <span class="auto-name">${escapedName}</span>
                        <span class="auto-path">${escapeHtml(auto.script_path || "")}</span>
                        ${reviewBadge}
                    </div>
                </td>
                <td class="fleet-cell-schedule"><span class="badge badge-muted badge-wrap fleet-schedule-badge">${scheduleLabel}</span></td>
                <td class="fleet-cell-next">${nextRun}</td>
                <td class="fleet-cell-last"><div class="fleet-last-stack">${lastLabel}${lastMeta}${lastReason}</div></td>
                <td>${auto.test_mode ? "<span class=\"badge badge-warning\">TESTE</span>" : "<span class=\"badge badge-blue\">PROD</span>"}</td>
                <td>${auto.enabled ? "<span class=\"badge badge-success\">ATIVO</span>" : "<span class=\"badge badge-danger\">PAUSADA</span>"}</td>
                <td class="fleet-cell-risk">${riskLabel}</td>
                <td class="fleet-cell-actions">
                    <div class="fleet-actions-inline" data-automation-id="${auto.id}">
                        <button class="btn-icon" type="button" data-action="run-auto" data-automation-id="${auto.id}" title="Executar"><i data-lucide="play" size="14"></i></button>
                        ${pauseResumeBtn}
                        <button class="btn-icon" type="button" data-action="open-edit-auto" data-automation-id="${auto.id}" title="Editar cadastro"><i data-lucide="pencil" size="14"></i></button>
                        <button class="btn-icon" type="button" data-action="open-automation-history" data-automation-id="${auto.id}" title="Histórico"><i data-lucide="history" size="14"></i></button>
                        <div class="fleet-actions-menu" data-automation-id="${auto.id}">
                            <button
                                class="btn-icon btn-icon-subtle btn-icon-menu-toggle"
                                type="button"
                                data-action-menu-toggle="${auto.id}"
                                aria-haspopup="true"
                                aria-expanded="false"
                                aria-controls="fleet-actions-menu-${auto.id}"
                                title="Mais ações"
                            >
                                <span class="btn-icon-glyph" aria-hidden="true">···</span>
                            </button>
                            <div
                                id="fleet-actions-menu-${auto.id}"
                                class="fleet-actions-menu-panel"
                                role="menu"
                                aria-label="Mais ações para ${escapedNameAttr}"
                                aria-hidden="true"
                                hidden
                            >
                                <button class="fleet-actions-menu-item" type="button" role="menuitem" data-action="clone-auto" data-automation-id="${auto.id}" title="Clonar">
                                    <i data-lucide="copy" size="14"></i>
                                    <span>Clonar</span>
                                </button>
                                <button class="fleet-actions-menu-item" type="button" role="menuitem" data-action="open-json-modal" data-automation-id="${auto.id}" data-automation-name="${escapedNameAttr}" title="Editar JSON">
                                    <i data-lucide="file-json" size="14"></i>
                                    <span>Editar JSON</span>
                                </button>
                                <button class="fleet-actions-menu-item" type="button" role="menuitem" data-action="open-ide-modal" data-automation-id="${auto.id}" data-automation-name="${escapedNameAttr}" title="Editar scripts">
                                    <i data-lucide="code" size="14"></i>
                                    <span>Editar scripts</span>
                                </button>
                                <button class="fleet-actions-menu-item" type="button" role="menuitem" data-action="delete-auto" data-automation-id="${auto.id}" title="Excluir cadastro">
                                    <i data-lucide="trash-2" size="14"></i>
                                    <span>Excluir cadastro</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
        }).join("");
        bindActionElements(tbody);
    }

    function initActionMenuEvents() {
        if (state.hasInitializedActionMenuEvents) return;
        state.hasInitializedActionMenuEvents = true;

        document.addEventListener("click", handleActionMenuClick);
        document.addEventListener("keydown", handleActionMenuKeydown);
        window.addEventListener("view-changed", (event) => {
            if (event?.detail?.target !== "automations") {
                closeActionMenu();
            }
        });
    }

    function handleActionMenuClick(event) {
        const toggleButton = event.target.closest("[data-action-menu-toggle]");
        if (toggleButton) {
            event.preventDefault();
            event.stopPropagation();
            toggleActionMenu(toggleButton.dataset.actionMenuToggle || "");
            return;
        }

        const menuItem = event.target.closest(".fleet-actions-menu-item");
        if (menuItem) {
            closeActionMenu();
            return;
        }

        if (state.openActionMenuAutomationId && !event.target.closest(".fleet-actions-menu")) {
            closeActionMenu();
        }
    }

    function handleActionMenuKeydown(event) {
        if (event.key !== "Escape" || !state.openActionMenuAutomationId) return;
        event.preventDefault();
        closeActionMenu({ restoreFocus: true });
    }

    function toggleActionMenu(automationId) {
        if (!automationId) return;
        if (state.openActionMenuAutomationId === automationId) {
            closeActionMenu({ restoreFocus: true });
            return;
        }
        openActionMenu(automationId);
    }

    function openActionMenu(automationId) {
        closeActionMenu();

        const menuPanel = document.getElementById(`fleet-actions-menu-${automationId}`);
        const toggleButton = document.querySelector(`[data-action-menu-toggle="${automationId}"]`);
        if (!menuPanel || !toggleButton) return;

        state.openActionMenuAutomationId = automationId;
        menuPanel.hidden = false;
        menuPanel.setAttribute("aria-hidden", "false");
        toggleButton.setAttribute("aria-expanded", "true");
        const firstAction = menuPanel.querySelector(".fleet-actions-menu-item");
        firstAction?.focus();
    }

    function closeActionMenu(options = {}) {
        if (!state.openActionMenuAutomationId) return;

        const { restoreFocus = false } = options;
        const automationId = state.openActionMenuAutomationId;
        const menuPanel = document.getElementById(`fleet-actions-menu-${automationId}`);
        const toggleButton = document.querySelector(`[data-action-menu-toggle="${automationId}"]`);

        if (menuPanel) {
            menuPanel.hidden = true;
            menuPanel.setAttribute("aria-hidden", "true");
        }
        if (toggleButton) {
            toggleButton.setAttribute("aria-expanded", "false");
            if (restoreFocus) toggleButton.focus();
        }

        state.openActionMenuAutomationId = null;
    }

    function handleSearch() {
        renderAutomationTable(getFilteredAutomations(), state.cachedJobs);
        refreshIcons();
    }

    async function openAutomationModal(automationId = null) {
        const modal = document.getElementById("modal-auto");
        if (!modal) return;

        resetAutomationForm();
        initTabsAndEvents();
        state.currentAutomationContext = null;
        state.latestAutomationPreflight = null;

        if (automationId !== null) {
            const auto = await api(`/api/automations/${automationId}`);
            if (!auto) return;
            fillAutomationForm(auto);
            state.currentAutomationContext = auto;
            setText("modal-title", "Editar Automação");
        } else {
            setText("modal-title", "Nova Automação");
        }

        switchTab("tab-identification");
        modal.showModal();
        refreshIcons();
    }

    function resetAutomationForm() {
        const form = document.getElementById("form-auto");
        if (form) form.reset();

        setValue("f-id", "");
        setValue("f-name", "");
        setValue("f-description", "");
        setValue("f-path", "");
        setValue("f-max-runtime", "30");
        setValue("f-max-retries", "0");
        setValue("f-cooldown", "0");
        setValue("f-queue-group", "");
        setValue("f-notification-channels", "");
        setValue("f-schedule-type", "manual");
        setValue("f-days-of-month", "");
        setValue("f-interval-minutes", "30");
        setValue("f-interval-anchor-time", "");
        setValue("f-once-run-at", "");
        setValue("f-cron-expression", "");

        const restrictedCheckbox = document.getElementById("f-interval-restricted");
        if (restrictedCheckbox) restrictedCheckbox.checked = false;
        setValue("f-interval-start-time", "08:00");
        setValue("f-interval-end-time", "18:00");

        const enabled = document.getElementById("f-enabled");
        const test = document.getElementById("f-test");
        if (enabled) enabled.checked = true;
        if (test) test.checked = false;

        state.currentAutomationContext = null;
        state.latestSchedulePreview = null;
        state.latestAutomationPreflight = null;
        switchTab("tab-identification");
        schedule.updateScheduleBlocksVisibility("manual");
        schedule.resetScheduleBuilder();
        review.clearReviewPanel();
    }

    function fillAutomationForm(auto) {
        setValue("f-id", auto.id);
        setValue("f-name", auto.name || "");
        setValue("f-description", auto.description || "");
        setValue("f-path", auto.script_path || "");
        setValue("f-max-runtime", String(auto.max_runtime_minutes || 30));
        setValue("f-max-retries", String(auto.max_retries || 0));
        setValue("f-cooldown", String(auto.cooldown_minutes || 0));
        setValue("f-queue-group", auto.queue_group || "");
        setValue("f-notification-channels", auto.notification_channels || "");

        const enabled = document.getElementById("f-enabled");
        const test = document.getElementById("f-test");
        if (enabled) enabled.checked = Boolean(auto.enabled);
        if (test) test.checked = Boolean(auto.test_mode);

        schedule.parseScheduleToBuilder(auto.schedule);
        review.refreshReviewPanel();
    }

    async function saveAutomation(event) {
        if (event) event.preventDefault();
        if (state.isSavingAutomation) return;

        if (state.currentTabId !== "tab-review") {
            switchTab("tab-review");
            showToast("Revise o cadastro na etapa final antes de salvar.", "warning");
            return;
        }

        const automationId = getValue("f-id");
        const name = getValue("f-name");
        const scriptPath = getValue("f-path");

        if (!name || !scriptPath) {
            showToast("Nome e caminho do script são obrigatórios.", "warning");
            return;
        }

        const payload = {
            name,
            description: getValue("f-description") || null,
            script_path: scriptPath,
            schedule: schedule.buildSchedulePayload(),
            max_runtime_minutes: Number(getValue("f-max-runtime") || 30),
            max_retries: Number(getValue("f-max-retries") || 0),
            cooldown_minutes: Number(getValue("f-cooldown") || 0),
            queue_group: getValue("f-queue-group") || null,
            enabled: Boolean(document.getElementById("f-enabled")?.checked),
            test_mode: Boolean(document.getElementById("f-test")?.checked),
            notification_channels: getValue("f-notification-channels") || null,
        };

        const preview = await api("/api/system/schedule/preview", "POST", { schedule: payload.schedule, limit: 3 }, { silentErrorToast: true });
        if (!preview || !preview.valid) {
            showToast((preview?.errors || ["Agenda inválida."])[0], "error");
            return;
        }
        state.latestSchedulePreview = preview;
        const preflight = await api("/api/automations/preflight", "POST", payload, { silentErrorToast: true });
        if (!preflight) {
            showToast("Falha ao validar governança da automação.", "error");
            return;
        }
        state.latestAutomationPreflight = preflight;
        review.refreshReviewPanel();

        if (preflight.valid === false) {
            const blockingIssue = Array.isArray(preflight.governance?.blocking_issues)
                ? preflight.governance.blocking_issues[0]
                : null;
            showToast(blockingIssue?.message || "Pré-validação governada reprovada.", "error");
            return;
        }

        const submitBtn = document.querySelector("#form-auto button[type=\"submit\"]");
        state.isSavingAutomation = true;
        if (submitBtn) submitBtn.disabled = true;

        try {
            let response = null;
            if (automationId) {
                response = await api(`/api/automations/${automationId}`, "PUT", payload, { silentErrorToast: true });
            } else {
                response = await api("/api/automations", "POST", payload, { silentErrorToast: true });
            }

            if (!response) {
                showToast("Falha ao salvar automação. Verifique os dados informados.", "error");
                return;
            }

            showToast("Automação salva com sucesso.", "success");
            document.getElementById("modal-auto")?.close();
            await Promise.all([loadConfig(), loadOverview(), loadExecutions(1)]);
        } finally {
            state.isSavingAutomation = false;
            if (submitBtn) submitBtn.disabled = false;
        }
    }

    function getFilteredAutomations() {
        const query = (document.getElementById("auto-search")?.value || "").toLowerCase().trim();
        return state.cachedAutomations.filter((auto) => {
            const matchesQuery = !query || (
                auto.name.toLowerCase().includes(query) ||
                (auto.description || "").toLowerCase().includes(query) ||
                auto.script_path.toLowerCase().includes(query)
            );
            if (!matchesQuery) return false;
            const reviewFilter = String(document.getElementById("auto-review-filter")?.value || "").trim();
            if (!reviewFilter) return true;
            const governance = state.cachedPortfolioByAutomation.get(auto.id);
            return String(governance?.review_status || "active") === reviewFilter;
        });
    }

    function goStep(direction) {
        const currentIndex = TAB_ORDER.indexOf(state.currentTabId);
        const nextIndex = Math.max(0, Math.min(TAB_ORDER.length - 1, currentIndex + Number(direction || 0)));
        switchTab(TAB_ORDER[nextIndex]);
    }

    async function pauseAuto(id) {
        const res = await api(`/api/automations/${id}/pause`, "POST");
        if (res) {
            showToast(res.message || "Automação pausada.", "success");
            await Promise.all([loadConfig(), loadOverview()]);
        }
    }

    async function resumeAuto(id) {
        const res = await api(`/api/automations/${id}/resume`, "POST");
        if (res) {
            showToast(res.message || "Automação retomada.", "success");
            await Promise.all([loadConfig(), loadOverview()]);
        }
    }

    async function cloneAuto(id) {
        const res = await api(`/api/automations/${id}/clone`, "POST");
        if (res) {
            showToast("Automação clonada com sucesso.", "success");
            await Promise.all([loadConfig(), loadOverview()]);
        }
    }

    async function deleteAuto(id) {
        const automation = state.cachedAutomations.find((item) => Number(item.id) === Number(id));
        const confirmed = window.confirm(
            `Excluir o cadastro da automação "${automation?.name || id}"? O histórico permanece auditável, mas a agenda e o ambiente operacional serão removidos.`
        );
        if (!confirmed) return;

        const res = await api(`/api/automations/${id}`, "DELETE");
        if (res) {
            showToast(res.message || "Cadastro removido com sucesso.", "success");
            await Promise.all([loadConfig(), loadOverview(), loadExecutions(1)]);
        }
    }

    return {
        loadConfig,
        handleSearch,
        openAutomationModal,
        saveAutomation,
        goStep,
        addScheduleTimeFromInput: schedule.addScheduleTimeFromInput,
        removeScheduleTime: schedule.removeScheduleTime,
        pauseAuto,
        resumeAuto,
        cloneAuto,
        deleteAuto,
        toggleScheduleDay: schedule.toggleScheduleDay,
        renderScheduleSummary: schedule.renderScheduleSummary,
        resetScheduleBuilder: schedule.resetScheduleBuilder,
        onScheduleTypeChanged: schedule.onScheduleTypeChanged,
    };
}
