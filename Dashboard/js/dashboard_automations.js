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

    let cachedAutomations = [];
    let cachedJobs = [];
    let isSavingAutomation = false;
    let scheduleTimes = [];
    let scheduleDays = new Set();
    let scheduleType = "manual";
    let hasInitializedEvents = false;
    let hasInitializedActionMenuEvents = false;
    let currentTabId = "tab-identification";
    let latestSchedulePreview = null;
    let currentAutomationContext = null;
    let latestAutomationPreflight = null;
    let openActionMenuAutomationId = null;
    let cachedPortfolioByAutomation = new Map();
    const TAB_ORDER = ["tab-identification", "tab-schedule", "tab-execution", "tab-review"];

    function initTabsAndEvents() {
        if (hasInitializedEvents) return;
        hasInitializedEvents = true;

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
                renderScheduleSummary();
            });
        });

        // Checkbox de restrição de janela (exclusivo: controle novo, não existia antes)
        const restrictedCheckbox = document.getElementById("f-interval-restricted");
        const restrictionPanel = document.getElementById("interval-restriction-panel");
        if (restrictedCheckbox && restrictionPanel) {
            restrictedCheckbox.addEventListener("change", (e) => {
                restrictionPanel.style.display = e.target.checked ? "block" : "none";
                renderScheduleSummary();
            });
        }

        // Campos novos que dashboard.js não cobre (f-cron-expression, horários da janela)
        const cronInput = document.getElementById("f-cron-expression");
        if (cronInput) {
            cronInput.addEventListener("input", () => renderScheduleSummary());
        }

        const intervalStartInput = document.getElementById("f-interval-start-time");
        if (intervalStartInput) {
            intervalStartInput.addEventListener("change", () => renderScheduleSummary());
        }

        const intervalEndInput = document.getElementById("f-interval-end-time");
        if (intervalEndInput) {
            intervalEndInput.addEventListener("change", () => renderScheduleSummary());
        }

        const intervalAnchorInput = document.getElementById("f-interval-anchor-time");
        if (intervalAnchorInput) {
            intervalAnchorInput.addEventListener("change", () => renderScheduleSummary());
        }

        // NOTA: .day-btn, f-schedule-type, f-interval-minutes, f-days-of-month e
        // f-once-run-at são gerenciados pelo dashboard.js (bindStaticEvents).
        // NÃO registrar aqui para evitar duplo disparo que cancela o efeito.
    }

    function switchTab(tabId) {
        currentTabId = tabId;
        const tabButtons = document.querySelectorAll(".modal-tabs .tab-btn");
        tabButtons.forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.tab === tabId);
        });

        const tabContents = document.querySelectorAll(".modal-body .tab-content");
        tabContents.forEach((content) => {
            content.classList.toggle("active", content.id === tabId);
        });
        if (tabId === "tab-review") {
            refreshReviewPanel();
        }
        updateStepButtons();
    }

    function updateStepButtons() {
        const prevBtn = document.querySelector('[data-action="auto-step-prev"]');
        const nextBtn = document.querySelector('[data-action="auto-step-next"]');
        const saveBtn = document.querySelector('#form-auto button[type="submit"]');
        const currentIndex = TAB_ORDER.indexOf(currentTabId);
        if (prevBtn) prevBtn.disabled = currentIndex <= 0;
        if (nextBtn) {
            nextBtn.disabled = currentIndex >= TAB_ORDER.length - 1;
            nextBtn.style.display = currentIndex >= TAB_ORDER.length - 1 ? "none" : "inline-flex";
        }
        if (saveBtn) {
            saveBtn.textContent = currentIndex >= TAB_ORDER.length - 1 ? "Salvar automação" : "Ir para revisão";
        }
    }

    function updateScheduleBlocksVisibility(type) {
        const blocks = document.querySelectorAll(".schedule-block");
        blocks.forEach((block) => {
            block.style.display = "none";
        });

        if (type === "daily") {
            const blockTimes = document.getElementById("schedule-block-times");
            if (blockTimes) blockTimes.style.display = "block";
        } else if (type === "weekly") {
            const blockWeekly = document.getElementById("schedule-block-weekly");
            const blockTimes = document.getElementById("schedule-block-times");
            if (blockWeekly) blockWeekly.style.display = "block";
            if (blockTimes) blockTimes.style.display = "block";
        } else if (type === "monthly") {
            const blockMonthly = document.getElementById("schedule-block-monthly");
            const blockTimes = document.getElementById("schedule-block-times");
            if (blockMonthly) blockMonthly.style.display = "block";
            if (blockTimes) blockTimes.style.display = "block";
        } else if (type === "interval") {
            const blockInterval = document.getElementById("schedule-block-interval");
            if (blockInterval) blockInterval.style.display = "block";
            
            const restrictedCheckbox = document.getElementById("f-interval-restricted");
            const restrictionPanel = document.getElementById("interval-restriction-panel");
            if (restrictedCheckbox && restrictionPanel) {
                restrictionPanel.style.display = restrictedCheckbox.checked ? "block" : "none";
            }
        } else if (type === "once") {
            const blockOnce = document.getElementById("schedule-block-once");
            if (blockOnce) blockOnce.style.display = "block";
        } else if (type === "cron") {
            const blockCron = document.getElementById("schedule-block-cron");
            if (blockCron) blockCron.style.display = "block";
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

        cachedAutomations = autos;
        cachedJobs = jobs || [];
        cachedPortfolioByAutomation = buildPortfolioLookup(portfolio);
        window.automations = autos;

        refreshAutomationFilterOptions(autos);
        renderAutomationTable(getFilteredAutomations(), jobs || []);
        syncGlobalTestToggle(autos);

        if (typeof lucide !== "undefined") lucide.createIcons();
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
            const riskLabel = buildRiskLabel(auto, cachedPortfolioByAutomation.get(auto.id));
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
        if (hasInitializedActionMenuEvents) return;
        hasInitializedActionMenuEvents = true;

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

        if (openActionMenuAutomationId && !event.target.closest(".fleet-actions-menu")) {
            closeActionMenu();
        }
    }

    function handleActionMenuKeydown(event) {
        if (event.key !== "Escape" || !openActionMenuAutomationId) return;
        event.preventDefault();
        closeActionMenu({ restoreFocus: true });
    }

    function toggleActionMenu(automationId) {
        if (!automationId) return;
        if (openActionMenuAutomationId === automationId) {
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

        openActionMenuAutomationId = automationId;
        menuPanel.hidden = false;
        menuPanel.setAttribute("aria-hidden", "false");
        toggleButton.setAttribute("aria-expanded", "true");
        const firstAction = menuPanel.querySelector(".fleet-actions-menu-item");
        firstAction?.focus();
    }

    function closeActionMenu(options = {}) {
        if (!openActionMenuAutomationId) return;

        const { restoreFocus = false } = options;
        const automationId = openActionMenuAutomationId;
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

        openActionMenuAutomationId = null;
    }

    function handleSearch() {
        renderAutomationTable(getFilteredAutomations(), cachedJobs);
        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    async function openAutomationModal(automationId = null) {
        const modal = document.getElementById("modal-auto");
        if (!modal) return;

        resetAutomationForm();
        initTabsAndEvents();
        currentAutomationContext = null;
        latestAutomationPreflight = null;

        if (automationId !== null) {
            const auto = await api(`/api/automations/${automationId}`);
            if (!auto) return;
            fillAutomationForm(auto);
            currentAutomationContext = auto;
            setText("modal-title", "Editar Automação");
        } else {
            setText("modal-title", "Nova Automação");
        }

        switchTab("tab-identification");
        modal.showModal();
        if (typeof lucide !== "undefined") lucide.createIcons();
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

        currentAutomationContext = null;
        latestSchedulePreview = null;
        latestAutomationPreflight = null;
        switchTab("tab-identification");
        updateScheduleBlocksVisibility("manual");
        resetScheduleBuilder();
        clearReviewPanel();
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

        parseScheduleToBuilder(auto.schedule);
        refreshReviewPanel();
    }

    function parseScheduleToBuilder(rawSchedule) {
        resetScheduleBuilder();
        if (!rawSchedule) return;

        try {
            const schedule = typeof rawSchedule === "string" ? JSON.parse(rawSchedule.replace(/'/g, "\"")) : rawSchedule;
            scheduleType = schedule.schedule_type || inferLegacyType(schedule);
            setValue("f-schedule-type", scheduleType);

            if (scheduleType === "cron") {
                setValue("f-cron-expression", schedule.cron_expression || "");
            } else if (scheduleType === "interval") {
                setValue("f-interval-minutes", String(schedule.interval_minutes || 30));
                setValue("f-interval-anchor-time", schedule.anchor_time || "");
                const hasRestriction = Boolean(schedule.start_time || schedule.end_time || (Array.isArray(schedule.days_of_week) && schedule.days_of_week.length > 0));
                const restrictedCheckbox = document.getElementById("f-interval-restricted");
                if (restrictedCheckbox) {
                    restrictedCheckbox.checked = hasRestriction;
                }
                setValue("f-interval-start-time", schedule.start_time || "08:00");
                setValue("f-interval-end-time", schedule.end_time || "18:00");

                const days = Array.isArray(schedule.days_of_week) ? schedule.days_of_week : [];
                days.forEach((day) => {
                    const d = Number(day);
                    if (Number.isInteger(d) && d >= 0 && d <= 6) scheduleDays.add(d);
                });
            } else {
                const days = Array.isArray(schedule.days_of_week) ? schedule.days_of_week : (Array.isArray(schedule.daysOfWeek) ? schedule.daysOfWeek : []);
                days.forEach((day) => {
                    const d = Number(day);
                    if (Number.isInteger(d) && d >= 0 && d <= 6) scheduleDays.add(d);
                });

                if (Array.isArray(schedule.times)) {
                    schedule.times.forEach((t) => {
                        const hh = String(Number(t.h || 0)).padStart(2, "0");
                        const mm = String(Number(t.m || 0)).padStart(2, "0");
                        scheduleTimes.push(`${hh}:${mm}`);
                    });
                } else {
                    const hours = Array.isArray(schedule.hours) ? schedule.hours : [];
                    const minutes = Array.isArray(schedule.minutes) ? schedule.minutes : [0];
                    hours.forEach((h) => {
                        minutes.forEach((m) => {
                            const hh = String(Number(h || 0)).padStart(2, "0");
                            const mm = String(Number(m || 0)).padStart(2, "0");
                            scheduleTimes.push(`${hh}:${mm}`);
                        });
                    });
                }
                if (Array.isArray(schedule.days_of_month)) {
                    setValue("f-days-of-month", schedule.days_of_month.join(","));
                }
                if (schedule.interval_minutes) {
                    setValue("f-interval-minutes", String(schedule.interval_minutes));
                }
                if (schedule.run_at) {
                    const iso = String(schedule.run_at).replace(" ", "T");
                    setValue("f-once-run-at", iso.slice(0, 16));
                }
            }

            scheduleTimes = Array.from(new Set(scheduleTimes)).sort();
            updateScheduleBlocksVisibility(scheduleType);
            refreshScheduleUi();
        } catch (_err) {
            showToast("Agenda existente inválida. Ajuste os horários manualmente.", "warning");
        }
    }

    function addScheduleTimeFromInput() {
        const input = document.getElementById("f-time-input");
        if (!input || !input.value) {
            showToast("Selecione um horário para adicionar.", "warning");
            return;
        }

        const hhmm = input.value;
        if (scheduleTimes.includes(hhmm)) {
            showToast("Horário já adicionado.", "warning");
            return;
        }

        scheduleTimes.push(hhmm);
        scheduleTimes.sort();
        input.value = "";
        refreshScheduleUi();
    }

    function removeScheduleTime(hhmm) {
        scheduleTimes = scheduleTimes.filter((item) => item !== hhmm);
        refreshScheduleUi();
    }

    function toggleScheduleDay(day) {
        const normalized = Number(day);
        if (!Number.isInteger(normalized) || normalized < 0 || normalized > 6) return;
        if (scheduleDays.has(normalized)) {
            scheduleDays.delete(normalized);
        } else {
            scheduleDays.add(normalized);
        }
        refreshScheduleUi();
    }

    function refreshScheduleUi() {
        renderScheduleTimes();
        renderScheduleDays();
        renderScheduleSummary();
    }

    function renderScheduleTimes() {
        const list = document.getElementById("f-time-list");
        if (!list) return;

        if (!scheduleTimes.length) {
            list.innerHTML = "<span class=\"time-placeholder\">Nenhum horário selecionado.</span>";
            return;
        }

        list.innerHTML = scheduleTimes.map((hhmm) => `
        <span class="time-tag">
            ${hhmm}
            <span class="remove-time" data-action="remove-schedule-time" data-hhmm="${hhmm}">✕</span>
        </span>
    `).join("");
        bindActionElements(list);
    }

    function renderScheduleDays() {
        document.querySelectorAll(".day-btn").forEach((btn) => {
            const day = Number(btn.dataset.day);
            btn.classList.toggle("active", scheduleDays.has(day));
        });
    }

    function renderScheduleSummary() {
        const summary = document.getElementById("schedule-summary");
        if (!summary) return;

        if (scheduleType === "manual") {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Disparo manual (sem agenda).</span>";
            if (typeof lucide !== "undefined") lucide.createIcons();
            renderSchedulePreview();
            return;
        }
        if ((scheduleType === "weekly" || scheduleType === "monthly" || scheduleType === "daily") && !scheduleTimes.length) {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Selecione ao menos um horário.</span>";
            if (typeof lucide !== "undefined") lucide.createIcons();
            renderSchedulePreview();
            return;
        }
        if (scheduleType === "weekly" && !scheduleDays.size) {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Selecione ao menos um dia da semana.</span>";
            if (typeof lucide !== "undefined") lucide.createIcons();
            renderSchedulePreview();
            return;
        }
        if (scheduleType === "cron" && !getValue("f-cron-expression").trim()) {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Insira uma expressão Cron.</span>";
            if (typeof lucide !== "undefined") lucide.createIcons();
            renderSchedulePreview();
            return;
        }

        const dayNames = { 0: "Dom", 1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb" };
        let label = "Agenda configurada.";
        if (scheduleType === "daily") {
            label = `Diária às ${scheduleTimes.join(", ")}`;
        } else if (scheduleType === "weekly") {
            const days = Array.from(scheduleDays).sort((a, b) => a - b).map((d) => dayNames[d]).join(", ");
            label = `Semanal: ${days} às ${scheduleTimes.join(", ")}`;
        } else if (scheduleType === "monthly") {
            const dom = (getValue("f-days-of-month") || "").trim();
            label = `Mensal: dia(s) ${dom || "?"} às ${scheduleTimes.join(", ")}`;
        } else if (scheduleType === "interval") {
            const intervalVal = getValue("f-interval-minutes") || 0;
            const anchorVal = getValue("f-interval-anchor-time");
            const anchorSuffix = anchorVal ? `, a partir das ${anchorVal}` : "";
            
            const restrictedCheckbox = document.getElementById("f-interval-restricted");
            if (restrictedCheckbox && restrictedCheckbox.checked) {
                const days = scheduleDays.size > 0 
                    ? Array.from(scheduleDays).sort((a, b) => a - b).map((d) => dayNames[d]).join(", ") 
                    : "Qualquer dia";
                const start = getValue("f-interval-start-time") || "08:00";
                const end = getValue("f-interval-end-time") || "18:00";
                label = `Intervalo: a cada ${intervalVal} min (${days}, das ${start} às ${end}${anchorSuffix})`;
            } else {
                label = `Intervalo: a cada ${intervalVal} min${anchorSuffix ? ` (${anchorSuffix.slice(2)})` : ""}`;
            }
        } else if (scheduleType === "once") {
            label = `Execução única em ${getValue("f-once-run-at") || "-"}`;
        } else if (scheduleType === "cron") {
            label = `Cron: ${getValue("f-cron-expression")}`;
        }
        
        summary.innerHTML = `<i data-lucide="calendar-clock" size="14"></i><span>${label}</span>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
        renderSchedulePreview();
    }

    function resetScheduleBuilder() {
        scheduleTimes = [];
        scheduleDays = new Set();
        scheduleType = "manual";
        refreshScheduleUi();
    }

    function buildSchedulePayload() {
        if (scheduleType === "manual") return JSON.stringify({ schedule_type: "manual", schedule_version: 2, timezone: "America/Sao_Paulo" });
        const times = scheduleTimes.map((item) => {
            const [h, m] = item.split(":");
            return { h: Number(h), m: Number(m) };
        });
        if (scheduleType === "daily") {
            return JSON.stringify({ schedule_type: "daily", schedule_version: 2, timezone: "America/Sao_Paulo", times });
        }
        if (scheduleType === "weekly") {
            return JSON.stringify({
                schedule_type: "weekly",
                schedule_version: 2,
                timezone: "America/Sao_Paulo",
                days_of_week: Array.from(scheduleDays).sort((a, b) => a - b),
                times,
            });
        }
        if (scheduleType === "monthly") {
            const days = (getValue("f-days-of-month") || "")
                .split(",")
                .map((item) => Number(item.trim()))
                .filter((item) => Number.isInteger(item) && item >= 1 && item <= 31);
            return JSON.stringify({ schedule_type: "monthly", schedule_version: 2, timezone: "America/Sao_Paulo", days_of_month: days, times });
        }
        if (scheduleType === "interval") {
            const intervalPayload = {
                schedule_type: "interval",
                schedule_version: 2,
                timezone: "America/Sao_Paulo",
                interval_minutes: Number(getValue("f-interval-minutes") || 30),
            };

            const anchorVal = getValue("f-interval-anchor-time");
            if (anchorVal) {
                intervalPayload.anchor_time = anchorVal;
            }

            const restrictedCheckbox = document.getElementById("f-interval-restricted");
            if (restrictedCheckbox && restrictedCheckbox.checked) {
                intervalPayload.start_time = getValue("f-interval-start-time") || "08:00";
                intervalPayload.end_time = getValue("f-interval-end-time") || "18:00";
                intervalPayload.days_of_week = Array.from(scheduleDays).sort((a, b) => a - b);
            }

            return JSON.stringify(intervalPayload);
        }
        if (scheduleType === "once") {
            const dt = getValue("f-once-run-at");
            return JSON.stringify({ schedule_type: "once", schedule_version: 2, timezone: "America/Sao_Paulo", run_at: dt ? `${dt}:00` : null });
        }
        if (scheduleType === "cron") {
            return JSON.stringify({
                schedule_type: "cron",
                schedule_version: 2,
                timezone: "America/Sao_Paulo",
                cron_expression: (getValue("f-cron-expression") || "").trim(),
            });
        }
        return null;
    }

    async function saveAutomation(event) {
        if (event) event.preventDefault();
        if (isSavingAutomation) return;

        if (currentTabId !== "tab-review") {
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
            schedule: buildSchedulePayload(),
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
        latestSchedulePreview = preview;
        const preflight = await api("/api/automations/preflight", "POST", payload, { silentErrorToast: true });
        if (!preflight) {
            showToast("Falha ao validar governança da automação.", "error");
            return;
        }
        latestAutomationPreflight = preflight;
        refreshReviewPanel();

        if (preflight.valid === false) {
            const blockingIssue = Array.isArray(preflight.governance?.blocking_issues)
                ? preflight.governance.blocking_issues[0]
                : null;
            showToast(blockingIssue?.message || "Pré-validação governada reprovada.", "error");
            return;
        }

        const submitBtn = document.querySelector("#form-auto button[type=\"submit\"]");
        isSavingAutomation = true;
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
            isSavingAutomation = false;
            if (submitBtn) submitBtn.disabled = false;
        }
    }

    function describeSchedule(rawSchedule) {
        if (!rawSchedule) return "MANUAL";
        try {
            const parsed = typeof rawSchedule === "string" ? JSON.parse(rawSchedule.replace(/'/g, "\"")) : rawSchedule;
            if (parsed.schedule_type === "cron") {
                return `Cron: ${parsed.cron_expression || ""}`;
            }
            if (parsed.schedule_type === "interval") {
                const hasRestriction = Boolean(parsed.start_time || parsed.end_time || (Array.isArray(parsed.days_of_week) && parsed.days_of_week.length > 0));
                return hasRestriction ? `A cada ${parsed.interval_minutes || 0} min (Janela)` : `A cada ${parsed.interval_minutes || 0} min`;
            }
            if (parsed.schedule_type === "once") return "Execução única";
            if (parsed.schedule_type === "daily") return `Diária (${(parsed.times || []).length} horário(s))`;
            if (parsed.schedule_type === "weekly") return `Semanal (${(parsed.times || []).length} horário(s))`;
            if (parsed.schedule_type === "monthly") return `Mensal (${(parsed.days_of_month || []).length} dia(s))`;
            const times = Array.isArray(parsed.times) ? parsed.times : [];
            if (!times.length) return "CONFIGURADA";
            return `${times.length} horário(s)`;
        } catch (_err) {
            return "CONFIGURADA";
        }
    }

    function inferLegacyType(schedule) {
        if (!schedule) return "manual";
        if (schedule.interval_minutes) return "interval";
        if (schedule.run_at) return "once";
        if (Array.isArray(schedule.days_of_month)) return "monthly";
        if (Array.isArray(schedule.days_of_week) || Array.isArray(schedule.daysOfWeek)) return "weekly";
        if (Array.isArray(schedule.times)) return "daily";
        return "manual";
    }

    function buildRiskLabel(auto, governance) {
        const flags = [];
        if (Number(auto.cooldown_minutes || 0) > 0) flags.push(`CD ${auto.cooldown_minutes}m`);
        if (Number(auto.max_retries || 0) > 0) flags.push(`RT ${auto.max_retries}`);
        if (auto.queue_group) flags.push("GRP");
        const governanceStatus = String(governance?.health_status || "").toLowerCase();
        const governanceDrift = Number(governance?.drift_count || 0);
        const docsStatus = String(governance?.docs_status || "").toLowerCase();
        if (governanceStatus === "not_governed" || governanceStatus === "not_registered") flags.push("CAT");
        if (governanceDrift > 0) flags.push(`DRIFT ${governanceDrift}`);
        if (docsStatus && docsStatus !== "complete") flags.push("DOCS");
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

    async function renderSchedulePreview() {
        const box = document.getElementById("schedule-preview");
        if (!box) return;
        const schedule = buildSchedulePayload();
        if (!schedule) {
            box.innerHTML = "";
            latestSchedulePreview = null;
            latestAutomationPreflight = null;
            return;
        }
        const preview = await api("/api/system/schedule/preview", "POST", { schedule, limit: 5 }, { silentErrorToast: true });
        if (!preview || !preview.valid) {
            box.innerHTML = "<span>Prévia indisponível.</span>";
            latestSchedulePreview = null;
            latestAutomationPreflight = null;
            return;
        }
        latestSchedulePreview = preview;
        const nextRuns = (preview.next_runs_preview || []).slice(0, 5);
        box.innerHTML = `<i data-lucide="clock-3" size="14"></i><span>Próximas: ${nextRuns.length ? nextRuns.join(" | ") : "sem execução futura"}</span>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
        if (currentTabId === "tab-review") {
            refreshReviewPanel();
        }
    }

    function clearReviewPanel() {
        ["automation-review-summary", "automation-review-preview", "automation-review-impact"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<div class="empty-state">Preencha os campos para gerar o conteúdo desta etapa.</div>';
        });
        const governance = document.getElementById("automation-review-governance");
        if (governance) governance.innerHTML = '<div class="empty-state">A validação governada será exibida antes do save.</div>';
    }

    function refreshReviewPanel() {
        renderReviewSummary();
        renderReviewPreview();
        renderReviewImpact();
        renderReviewGovernance();
    }

    function renderReviewSummary() {
        const container = document.getElementById("automation-review-summary");
        if (!container) return;
        const name = getValue("f-name") || "Automação sem nome";
        const path = getValue("f-path") || "Caminho ainda não informado";
        const queueGroup = getValue("f-queue-group") || "Sem grupo operacional";
        const mode = document.getElementById("f-test")?.checked ? "Modo teste" : "Modo produtivo";
        const enabled = document.getElementById("f-enabled")?.checked ? "Ativa" : "Pausada";
        const lastContext = currentAutomationContext?.last_execution_started_at
            ? `<small>Última execução: ${escapeHtml(currentAutomationContext.last_execution_started_at)}${currentAutomationContext.last_status ? ` · ${escapeHtml(translateStatus(currentAutomationContext.last_status))}` : ""}</small>`
            : "<small>Sem histórico carregado para esta automação.</small>";

        container.innerHTML = `
            <div class="review-item">
                <strong>${escapeHtml(name)}</strong>
                <p>${escapeHtml(path)}</p>
                <small>Fila: ${escapeHtml(queueGroup)} · ${escapeHtml(mode)} · ${escapeHtml(enabled)}</small>
                ${lastContext}
            </div>
            <div class="review-item">
                <strong>Resiliência e canais</strong>
                <p>Timeout ${escapeHtml(getValue("f-max-runtime") || "30")} min · Retry ${escapeHtml(getValue("f-max-retries") || "0")} · Cooldown ${escapeHtml(getValue("f-cooldown") || "0")} min</p>
                <small>Canais: ${escapeHtml(getValue("f-notification-channels") || "não informados")}</small>
            </div>
        `;
    }

    function renderReviewPreview() {
        const container = document.getElementById("automation-review-preview");
        if (!container) return;
        const preview = latestSchedulePreview;
        const summaryLabel = preview?.schedule_summary || document.getElementById("schedule-summary")?.innerText || "Agenda ainda não validada.";
        const nextRuns = Array.isArray(preview?.next_runs_preview) ? preview.next_runs_preview : [];
        container.innerHTML = `
            <div class="review-item">
                <strong>${escapeHtml(summaryLabel)}</strong>
                <p>${nextRuns.length ? escapeHtml(nextRuns.join(" | ")) : "Sem execução futura ou sem agenda configurada."}</p>
                <small>Tipo: ${escapeHtml((preview?.schedule_type || scheduleType || "manual").toUpperCase())}</small>
            </div>
        `;
    }

    function renderReviewImpact() {
        const container = document.getElementById("automation-review-impact");
        if (!container) return;
        const retries = Number(getValue("f-max-retries") || 0);
        const cooldown = Number(getValue("f-cooldown") || 0);
        const queueGroup = getValue("f-queue-group") || "sem grupo";
        const mode = document.getElementById("f-test")?.checked ? "O fluxo será executado em modo teste." : "O fluxo poderá atuar em ambiente produtivo.";
        const retryNote = retries > 0
            ? `Permitirá ${retries} tentativa(s) automática(s) com cooldown de ${cooldown} minuto(s).`
            : "Não haverá retry automático; a recuperação dependerá de ação operacional.";
        container.innerHTML = `
            <div class="review-item">
                <strong>Impacto operacional</strong>
                <p>${escapeHtml(mode)}</p>
                <small>Grupo operacional: ${escapeHtml(queueGroup)}. ${escapeHtml(retryNote)}</small>
            </div>
            <div class="review-item">
                <strong>Validação antes do save</strong>
                <p>A agenda foi validada pelo backend e a prévia de próximas execuções foi recalculada.</p>
                <small>Se a configuração estiver incorreta, o save permanece bloqueado.</small>
            </div>
        `;
    }

    function renderReviewGovernance() {
        const container = document.getElementById("automation-review-governance");
        if (!container) return;
        const preflight = latestAutomationPreflight;
        if (!preflight) {
            container.innerHTML = '<div class="empty-state">A pré-validação governada aparecerá após a revisão da agenda.</div>';
            return;
        }

        const governance = preflight.governance || {};
        const blockingIssues = Array.isArray(governance.blocking_issues) ? governance.blocking_issues : [];
        const warnings = Array.isArray(governance.warnings) ? governance.warnings : [];
        const status = String(governance.status || "healthy").toLowerCase();

        if (status === "incident") {
            container.innerHTML = `
                <div class="review-item danger">
                    <strong>Save bloqueado pelo manifesto governado</strong>
                    <p>${escapeHtml(governance.top_issue || "Há inconsistências entre cadastro e manifesto.")}</p>
                    <small>${escapeHtml(blockingIssues[0]?.message || governance.recommended_action || "Alinhe o automation.manifest.json antes de salvar.")}</small>
                </div>
            `;
            return;
        }

        if (status === "attention") {
            container.innerHTML = `
                <div class="review-item warning">
                    <strong>Governança em atenção</strong>
                    <p>${escapeHtml(governance.top_issue || "Há avisos operacionais para esta automação.")}</p>
                    <small>${escapeHtml(warnings[0]?.message || governance.recommended_action || "Revise os avisos antes da promoção.")}</small>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="review-item success">
                <strong>Governança validada</strong>
                <p>${escapeHtml(governance.top_issue || "Cadastro alinhado ao manifesto governado.")}</p>
                <small>${escapeHtml(governance.catalog_id ? `Catálogo ${governance.catalog_id}` : "Manifesto validado.")}</small>
            </div>
        `;
    }

    function buildPortfolioLookup(portfolio) {
        const lookup = new Map();
        const items = Array.isArray(portfolio?.items) ? portfolio.items : [];
        items.forEach((item) => {
            if (item?.automation_id) {
                lookup.set(Number(item.automation_id), item);
            }
        });
        return lookup;
    }

    function getFilteredAutomations() {
        const query = (document.getElementById("auto-search")?.value || "").toLowerCase().trim();
        if (!query) return cachedAutomations;
        return cachedAutomations.filter((auto) => (
            auto.name.toLowerCase().includes(query) ||
            (auto.description || "").toLowerCase().includes(query) ||
            auto.script_path.toLowerCase().includes(query)
        ));
    }

    function goStep(direction) {
        const currentIndex = TAB_ORDER.indexOf(currentTabId);
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

    function onScheduleTypeChanged(nextType) {
        scheduleType = nextType || "manual";
        updateScheduleBlocksVisibility(scheduleType);
        refreshScheduleUi();
    }

    return {
        loadConfig,
        handleSearch,
        openAutomationModal,
        saveAutomation,
        goStep,
        addScheduleTimeFromInput,
        removeScheduleTime,
        pauseAuto,
        resumeAuto,
        cloneAuto,
        toggleScheduleDay,
        renderScheduleSummary,
        resetScheduleBuilder,
        onScheduleTypeChanged,
    };
}
