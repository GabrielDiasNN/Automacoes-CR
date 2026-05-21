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
        const tabButtons = document.querySelectorAll(".modal-tabs .tab-btn");
        tabButtons.forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.tab === tabId);
        });

        const tabContents = document.querySelectorAll(".modal-body .tab-content");
        tabContents.forEach((content) => {
            content.classList.toggle("active", content.id === tabId);
        });
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
        const [autos, jobs] = await Promise.all([
            api("/api/automations/all"),
            api("/api/system/scheduler/jobs"),
        ]);

        if (!autos) return;

        cachedAutomations = autos;
        cachedJobs = jobs || [];
        window.automations = autos;

        refreshAutomationFilterOptions(autos);
        renderAutomationTable(autos, jobs || []);
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
    }

    function renderAutomationTable(autos, jobs) {
        const tbody = document.getElementById("fleet-tbody");
        if (!tbody) return;

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
            const riskLabel = buildRiskLabel(auto);
            const lastLabel = auto.last_status ? `<span class="badge ${getBadgeClass(auto.last_status)}">${translateStatus(auto.last_status)}</span>` : "<span class=\"badge badge-muted\">Sem histórico</span>";
            const pauseResumeBtn = auto.enabled
                ? `<button class="btn-icon" data-action="pause-auto" data-automation-id="${auto.id}" title="Pausar"><i data-lucide="pause" size="14"></i></button>`
                : `<button class="btn-icon" data-action="resume-auto" data-automation-id="${auto.id}" title="Retomar"><i data-lucide="play-circle" size="14"></i></button>`;
            const escapedNameAttr = escapeHtml(String(auto.name || ""));

            return `
            <tr>
                <td>
                    <div class="auto-info">
                        <span class="auto-name">${escapedName}</span>
                        <span class="auto-path">${escapeHtml(auto.script_path || "")}</span>
                    </div>
                </td>
                <td><span class="badge badge-muted">${scheduleLabel}</span></td>
                <td>${nextRun}</td>
                <td>${lastLabel}</td>
                <td>${auto.test_mode ? "<span class=\"badge badge-warning\">TESTE</span>" : "<span class=\"badge badge-blue\">PROD</span>"}</td>
                <td>${auto.enabled ? "<span class=\"badge badge-success\">ATIVO</span>" : "<span class=\"badge badge-danger\">PAUSADA</span>"}</td>
                <td>${riskLabel}</td>
                <td>
                    <div class="inline-actions">
                        <button class="btn-icon" data-action="run-auto" data-automation-id="${auto.id}" title="Executar"><i data-lucide="play" size="14"></i></button>
                        ${pauseResumeBtn}
                        <button class="btn-icon" data-action="open-edit-auto" data-automation-id="${auto.id}" title="Editar cadastro"><i data-lucide="pencil" size="14"></i></button>
                        <button class="btn-icon" data-action="clone-auto" data-automation-id="${auto.id}" title="Clonar"><i data-lucide="copy" size="14"></i></button>
                        <button class="btn-icon" data-action="open-automation-history" data-automation-id="${auto.id}" title="Histórico"><i data-lucide="history" size="14"></i></button>
                        <button class="btn-icon" data-action="open-json-modal" data-automation-id="${auto.id}" data-automation-name="${escapedNameAttr}" title="Editar JSON"><i data-lucide="file-json" size="14"></i></button>
                        <button class="btn-icon" data-action="open-ide-modal" data-automation-id="${auto.id}" data-automation-name="${escapedNameAttr}" title="Editar scripts"><i data-lucide="code" size="14"></i></button>
                    </div>
                </td>
            </tr>
        `;
        }).join("");
        bindActionElements(tbody);
    }

    function handleSearch() {
        const query = (document.getElementById("auto-search")?.value || "").toLowerCase().trim();
        const filtered = cachedAutomations.filter((auto) => {
            return (
                auto.name.toLowerCase().includes(query) ||
                (auto.description || "").toLowerCase().includes(query) ||
                auto.script_path.toLowerCase().includes(query)
            );
        });

        renderAutomationTable(filtered, cachedJobs);
        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    async function openAutomationModal(automationId = null) {
        const modal = document.getElementById("modal-auto");
        if (!modal) return;

        resetAutomationForm();
        initTabsAndEvents();

        if (automationId !== null) {
            const auto = await api(`/api/automations/${automationId}`);
            if (!auto) return;
            fillAutomationForm(auto);
            setText("modal-title", "Editar Automação");
        } else {
            setText("modal-title", "Nova Automação");
        }

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

        switchTab("tab-general");
        updateScheduleBlocksVisibility("manual");
        resetScheduleBuilder();
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

    function buildRiskLabel(auto) {
        const flags = [];
        if (Number(auto.cooldown_minutes || 0) > 0) flags.push(`CD ${auto.cooldown_minutes}m`);
        if (Number(auto.max_retries || 0) > 0) flags.push(`RT ${auto.max_retries}`);
        if (auto.queue_group) flags.push("GRP");
        const failures24h = Number(auto.failures_24h || 0);
        const timeouts24h = Number(auto.timeouts_24h || 0);
        const success24h = Number(auto.success_24h || 0);
        if (timeouts24h > 0) flags.push(`TO ${timeouts24h}/24h`);
        if (failures24h > 0) flags.push(`ER ${failures24h}/24h`);
        if (success24h > 0 && failures24h === 0 && timeouts24h === 0) flags.push(`OK ${success24h}/24h`);

        if (!flags.length) return "<span class=\"badge badge-success\">OK</span>";
        const hasFailure = failures24h > 0 || timeouts24h > 0;
        return `<span class="badge ${hasFailure ? "badge-danger" : "badge-warning"}">${flags.join(" • ")}</span>`;
    }

    async function renderSchedulePreview() {
        const box = document.getElementById("schedule-preview");
        if (!box) return;
        const schedule = buildSchedulePayload();
        if (!schedule) {
            box.innerHTML = "";
            return;
        }
        const preview = await api("/api/system/schedule/preview", "POST", { schedule, limit: 5 }, { silentErrorToast: true });
        if (!preview || !preview.valid) {
            box.innerHTML = "<span>Prévia indisponível.</span>";
            return;
        }
        const nextRuns = (preview.next_runs_preview || []).slice(0, 5);
        box.innerHTML = `<i data-lucide="clock-3" size="14"></i><span>Próximas: ${nextRuns.length ? nextRuns.join(" | ") : "sem execução futura"}</span>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
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
