/**
 * Construtor de agenda do modal de automação.
 * Gerencia os blocos de UI de agenda (diária/semanal/mensal/intervalo/cron/once)
 * e constrói o payload de schedule para o backend.
 *
 * Recebe o estado compartilhado (state) por referência e uma callback
 * onPreviewUpdated que é chamada após cada atualização da prévia de schedule,
 * permitindo que o painel de revisão seja atualizado sem dependência circular.
 */

import { inferLegacyType } from "./automations-helpers.js";

export function createScheduleModule(ctx, state, onPreviewUpdated) {
    const { api, showToast, getValue, setValue, refreshIcons, bindActionElements } = ctx;

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

    function parseScheduleToBuilder(rawSchedule) {
        resetScheduleBuilder();
        if (!rawSchedule) return;

        try {
            const schedule = typeof rawSchedule === "string" ? JSON.parse(rawSchedule.replace(/'/g, "\"")) : rawSchedule;
            state.scheduleType = schedule.schedule_type || inferLegacyType(schedule);
            setValue("f-schedule-type", state.scheduleType);

            if (state.scheduleType === "cron") {
                setValue("f-cron-expression", schedule.cron_expression || "");
            } else if (state.scheduleType === "interval") {
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
                    if (Number.isInteger(d) && d >= 0 && d <= 6) state.scheduleDays.add(d);
                });
            } else {
                const days = Array.isArray(schedule.days_of_week) ? schedule.days_of_week : (Array.isArray(schedule.daysOfWeek) ? schedule.daysOfWeek : []);
                days.forEach((day) => {
                    const d = Number(day);
                    if (Number.isInteger(d) && d >= 0 && d <= 6) state.scheduleDays.add(d);
                });

                if (Array.isArray(schedule.times)) {
                    schedule.times.forEach((t) => {
                        const hh = String(Number(t.h || 0)).padStart(2, "0");
                        const mm = String(Number(t.m || 0)).padStart(2, "0");
                        state.scheduleTimes.push(`${hh}:${mm}`);
                    });
                } else {
                    const hours = Array.isArray(schedule.hours) ? schedule.hours : [];
                    const minutes = Array.isArray(schedule.minutes) ? schedule.minutes : [0];
                    hours.forEach((h) => {
                        minutes.forEach((m) => {
                            const hh = String(Number(h || 0)).padStart(2, "0");
                            const mm = String(Number(m || 0)).padStart(2, "0");
                            state.scheduleTimes.push(`${hh}:${mm}`);
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

            state.scheduleTimes = Array.from(new Set(state.scheduleTimes)).sort();
            updateScheduleBlocksVisibility(state.scheduleType);
            refreshScheduleUi();
        } catch {
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
        if (state.scheduleTimes.includes(hhmm)) {
            showToast("Horário já adicionado.", "warning");
            return;
        }

        state.scheduleTimes.push(hhmm);
        state.scheduleTimes.sort();
        input.value = "";
        refreshScheduleUi();
    }

    function removeScheduleTime(hhmm) {
        state.scheduleTimes = state.scheduleTimes.filter((item) => item !== hhmm);
        refreshScheduleUi();
    }

    function toggleScheduleDay(day) {
        const normalized = Number(day);
        if (!Number.isInteger(normalized) || normalized < 0 || normalized > 6) return;
        if (state.scheduleDays.has(normalized)) {
            state.scheduleDays.delete(normalized);
        } else {
            state.scheduleDays.add(normalized);
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

        if (!state.scheduleTimes.length) {
            list.innerHTML = "<span class=\"time-placeholder\">Nenhum horário selecionado.</span>";
            return;
        }

        list.innerHTML = state.scheduleTimes.map((hhmm) => `
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
            btn.classList.toggle("active", state.scheduleDays.has(day));
        });
    }

    function renderScheduleSummary() {
        const summary = document.getElementById("schedule-summary");
        if (!summary) return;

        if (state.scheduleType === "manual") {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Disparo manual (sem agenda).</span>";
            refreshIcons();
            renderSchedulePreview();
            return;
        }
        if ((state.scheduleType === "weekly" || state.scheduleType === "monthly" || state.scheduleType === "daily") && !state.scheduleTimes.length) {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Selecione ao menos um horário.</span>";
            refreshIcons();
            renderSchedulePreview();
            return;
        }
        if (state.scheduleType === "weekly" && !state.scheduleDays.size) {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Selecione ao menos um dia da semana.</span>";
            refreshIcons();
            renderSchedulePreview();
            return;
        }
        if (state.scheduleType === "cron" && !getValue("f-cron-expression").trim()) {
            summary.innerHTML = "<i data-lucide=\"info\" size=\"14\"></i><span>Insira uma expressão Cron.</span>";
            refreshIcons();
            renderSchedulePreview();
            return;
        }

        const dayNames = { 0: "Dom", 1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb" };
        let label = "Agenda configurada.";
        if (state.scheduleType === "daily") {
            label = `Diária às ${state.scheduleTimes.join(", ")}`;
        } else if (state.scheduleType === "weekly") {
            const days = Array.from(state.scheduleDays).sort((a, b) => a - b).map((d) => dayNames[d]).join(", ");
            label = `Semanal: ${days} às ${state.scheduleTimes.join(", ")}`;
        } else if (state.scheduleType === "monthly") {
            const dom = (getValue("f-days-of-month") || "").trim();
            label = `Mensal: dia(s) ${dom || "?"} às ${state.scheduleTimes.join(", ")}`;
        } else if (state.scheduleType === "interval") {
            const intervalVal = getValue("f-interval-minutes") || 0;
            const anchorVal = getValue("f-interval-anchor-time");
            const anchorSuffix = anchorVal ? `, início da cadência às ${anchorVal}` : "";

            const restrictedCheckbox = document.getElementById("f-interval-restricted");
            if (restrictedCheckbox && restrictedCheckbox.checked) {
                const days = state.scheduleDays.size > 0
                    ? Array.from(state.scheduleDays).sort((a, b) => a - b).map((d) => dayNames[d]).join(", ")
                    : "Qualquer dia";
                const start = getValue("f-interval-start-time") || "08:00";
                const end = getValue("f-interval-end-time") || "18:00";
                label = `Intervalo: a cada ${intervalVal} min (${days}, início ${start}, fim ${end}${anchorSuffix})`;
            } else {
                label = `Intervalo: a cada ${intervalVal} min${anchorSuffix ? ` (${anchorSuffix.slice(2)})` : ""}`;
            }
        } else if (state.scheduleType === "once") {
            label = `Execução única em ${getValue("f-once-run-at") || "-"}`;
        } else if (state.scheduleType === "cron") {
            label = `Cron: ${getValue("f-cron-expression")}`;
        }

        summary.innerHTML = `<i data-lucide="calendar-clock" size="14"></i><span>${label}</span>`;
        refreshIcons();
        renderSchedulePreview();
    }

    function resetScheduleBuilder() {
        state.scheduleTimes = [];
        state.scheduleDays = new Set();
        state.scheduleType = "manual";
        refreshScheduleUi();
    }

    function buildSchedulePayload() {
        if (state.scheduleType === "manual") return JSON.stringify({ schedule_type: "manual", schedule_version: 2, timezone: "America/Sao_Paulo" });
        const times = state.scheduleTimes.map((item) => {
            const [h, m] = item.split(":");
            return { h: Number(h), m: Number(m) };
        });
        if (state.scheduleType === "daily") {
            return JSON.stringify({ schedule_type: "daily", schedule_version: 2, timezone: "America/Sao_Paulo", times });
        }
        if (state.scheduleType === "weekly") {
            return JSON.stringify({
                schedule_type: "weekly",
                schedule_version: 2,
                timezone: "America/Sao_Paulo",
                days_of_week: Array.from(state.scheduleDays).sort((a, b) => a - b),
                times,
            });
        }
        if (state.scheduleType === "monthly") {
            const days = (getValue("f-days-of-month") || "")
                .split(",")
                .map((item) => Number(item.trim()))
                .filter((item) => Number.isInteger(item) && item >= 1 && item <= 31);
            return JSON.stringify({ schedule_type: "monthly", schedule_version: 2, timezone: "America/Sao_Paulo", days_of_month: days, times });
        }
        if (state.scheduleType === "interval") {
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
                intervalPayload.days_of_week = Array.from(state.scheduleDays).sort((a, b) => a - b);
            }

            return JSON.stringify(intervalPayload);
        }
        if (state.scheduleType === "once") {
            const dt = getValue("f-once-run-at");
            return JSON.stringify({ schedule_type: "once", schedule_version: 2, timezone: "America/Sao_Paulo", run_at: dt ? `${dt}:00` : null });
        }
        if (state.scheduleType === "cron") {
            return JSON.stringify({
                schedule_type: "cron",
                schedule_version: 2,
                timezone: "America/Sao_Paulo",
                cron_expression: (getValue("f-cron-expression") || "").trim(),
            });
        }
        return null;
    }

    async function renderSchedulePreview() {
        const box = document.getElementById("schedule-preview");
        if (!box) return;
        const schedule = buildSchedulePayload();
        if (!schedule) {
            box.innerHTML = "";
            state.latestSchedulePreview = null;
            state.latestAutomationPreflight = null;
            return;
        }
        const preview = await api("/api/system/schedule/preview", "POST", { schedule, limit: 5 }, { silentErrorToast: true });
        if (!preview || !preview.valid) {
            box.innerHTML = "<span>Prévia indisponível.</span>";
            state.latestSchedulePreview = null;
            state.latestAutomationPreflight = null;
            return;
        }
        state.latestSchedulePreview = preview;
        const nextRuns = (preview.next_runs_preview || []).slice(0, 5);
        box.innerHTML = `<i data-lucide="clock-3" size="14"></i><span>Próximas: ${nextRuns.length ? nextRuns.join(" | ") : "sem execução futura"}</span>`;
        refreshIcons();
        if (state.currentTabId === "tab-review") {
            onPreviewUpdated();
        }
    }

    function onScheduleTypeChanged(nextType) {
        state.scheduleType = nextType || "manual";
        updateScheduleBlocksVisibility(state.scheduleType);
        refreshScheduleUi();
    }

    return {
        updateScheduleBlocksVisibility,
        parseScheduleToBuilder,
        addScheduleTimeFromInput,
        removeScheduleTime,
        toggleScheduleDay,
        renderScheduleSummary,
        resetScheduleBuilder,
        buildSchedulePayload,
        renderSchedulePreview,
        onScheduleTypeChanged,
    };
}
