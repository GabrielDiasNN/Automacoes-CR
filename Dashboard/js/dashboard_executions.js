import { normalizeExecutionsPayload } from "./contracts.js";

export function createExecutionsModule(ctx) {
    const {
        api,
        ui,
        formatDate,
        getBadgeClass,
        translateStatus,
        escapeHtml,
        getValue,
        setExecPage,
        getExecPage,
        execPerPage,
        stopExec,
        openLogModal,
        showToast,
        loadOverview,
        bindActionElements,
        safePrompt,
        getLatestSystemDiagnostics,
    } = ctx;
    let lastLoadedItems = [];

    async function loadExecutions(page = getExecPage()) {
        setExecPage(page);
        const tbody = document.getElementById("exec-tbody");
        if (tbody) {
            tbody.innerHTML = "<tr><td colspan=\"8\">Carregando execuções...</td></tr>";
        }

        const params = new URLSearchParams({
            page: String(getExecPage()),
            per_page: String(execPerPage),
        });

        const status = getValue("filter-status");
        const automationId = getValue("filter-automation");
        const queueGroup = getValue("filter-queue-group");
        const priority = getValue("filter-priority");
        const requestedBy = getValue("filter-requested-by");
        const dateFrom = getValue("filter-date-from");
        const dateTo = getValue("filter-date-to");

        if (status) params.set("status", status);
        if (automationId) params.set("automation_id", automationId);
        if (queueGroup) params.set("queue_group", queueGroup);
        if (priority) params.set("priority", priority);
        if (requestedBy) params.set("requested_by", requestedBy);
        if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00`);
        if (dateTo) params.set("date_to", `${dateTo}T23:59:59`);

        const rawData = await api(`/api/executions?${params.toString()}`);
        if (!rawData) return;
        const data = normalizeExecutionsPayload(rawData);
        lastLoadedItems = Array.isArray(data.items) ? data.items.slice() : [];
        lastLoadedItems.sort((a, b) => {
            const scoreDiff = Number(b.operator_score || 0) - Number(a.operator_score || 0);
            if (scoreDiff !== 0) return scoreDiff;
            return String(b.started_at || "").localeCompare(String(a.started_at || ""), "pt-BR");
        });

        renderExecutionsTable(lastLoadedItems);
        renderExecutionsBanner(lastLoadedItems);
        renderTriageSummary(lastLoadedItems);
        ui.renderPagination(data.total || 0, data.page || 1, data.pages || 1, "exec-pagination", (nextPage) => {
            loadExecutions(nextPage);
        });

        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    function renderExecutionsTable(items) {
        const tbody = document.getElementById("exec-tbody");
        if (!tbody) return;

        if (!items.length) {
            tbody.innerHTML = "<tr><td colspan=\"8\">Nenhuma execução encontrada para o recorte operacional atual.</td></tr>";
            return;
        }

        tbody.innerHTML = items.map((ex) => `
        <tr data-action="open-log-row" data-execution-id="${escapeHtml(ex.id)}" style="cursor:pointer">
            <td><strong>${escapeHtml(ex.automation_name || "?")}</strong></td>
            <td style="font-family:monospace;font-size:0.75rem;opacity:0.85">${ex.id}</td>
            <td><span class="badge ${getBadgeClass(ex.status)}">${translateStatus(ex.status)}</span></td>
            <td><span class="badge badge-muted">${escapeHtml(ex.requested_by || "-")}</span></td>
            <td>${ex.duration_seconds ? Number(ex.duration_seconds).toFixed(1) + "s" : "-"}</td>
            <td>${formatDate(ex.started_at)}</td>
            <td>${renderRecoveryCell(ex)}</td>
            <td>${renderExecutionActions(ex)}</td>
        </tr>
    `).join("");
        bindActionElements(tbody);
    }

    function renderRecoveryCell(ex) {
        const attention = Boolean(ex.operator_attention_required);
        if (!attention) {
            return `<span class="triage-quiet">-</span>`;
        }

        const chips = [];
        const meta = [];
        if (ex.operator_severity && String(ex.operator_severity).toUpperCase() !== "NORMAL") {
            chips.push(`<span class="badge ${getSeverityBadgeClass(ex.operator_severity)}">${escapeHtml(ex.operator_severity)}</span>`);
        }
        if (ex.failure_reason) {
            chips.push(`<span class="badge badge-muted">${escapeHtml(ex.failure_reason)}</span>`);
        }
        if (ex.priority && String(ex.priority).toUpperCase() === "HIGH") {
            chips.push(`<span class="badge badge-blue">Alta</span>`);
        }
        if (ex.operator_action_label) {
            meta.push(`<span class="recovery-primary">${escapeHtml(ex.operator_action_label)}</span>`);
        }
        if (ex.requeue_block_reason) {
            meta.push(`<small>${escapeHtml(ex.requeue_block_reason)}</small>`);
        } else if (ex.operator_reason_summary) {
            meta.push(`<small>${escapeHtml(ex.operator_reason_summary)}</small>`);
        }
        if (!chips.length && !meta.length) {
            return `<span class="triage-quiet">-</span>`;
        }
        return `<div class="recovery-cell compact">${chips.join("")}${meta.join("")}</div>`;
    }

    function renderExecutionActions(ex) {
        if (ex.stop_allowed) {
            return `<button class="btn btn-danger btn-sm" data-action="stop-exec" data-execution-id="${escapeHtml(ex.id)}" title="Parar execução"><i data-lucide="square"></i></button>`;
        }
        if (Boolean(ex.requeue_allowed)) {
            return `<button class="btn btn-outline btn-sm" data-action="requeue-exec" data-execution-id="${escapeHtml(ex.id)}" title="Reenfileirar com auditoria"><i data-lucide="rotate-cw"></i></button>`;
        }
        if (ex.related_execution_id) {
            return `<button class="btn btn-outline btn-sm" data-action="open-log" data-execution-id="${escapeHtml(ex.related_execution_id)}" title="Abrir execução relacionada"><i data-lucide="link-2"></i></button>`;
        }
        return `<button class="btn btn-outline btn-sm" data-action="open-log" data-execution-id="${escapeHtml(ex.id)}" title="Abrir logs"><i data-lucide="terminal"></i></button>`;
    }

    function renderExecutionsBanner(items) {
        const banner = document.getElementById("exec-state-banner");
        if (!banner) return;
        if (!items.length) {
            banner.className = "state-banner";
            banner.textContent = "Nenhuma execução encontrada. Ajuste os filtros ou troque o preset.";
            return;
        }
        const active = items.filter((item) => item.stop_allowed).length;
        const attention = items.filter((item) => item.operator_attention_required).length;
        const critical = items.filter((item) => String(item.operator_severity || "") === "CRITICAL").length;
        const high = items.filter((item) => String(item.operator_severity || "") === "HIGH").length;
        banner.className = critical > 0 || attention > 0 || active > 0 ? "state-banner warning" : "state-banner success";
        banner.textContent = `Recorte atual: ${items.length} execução(ões) · ${attention} com atenção · ${critical} crítica(s) · ${high} alta(s) · ${active} ativa(s).`;
    }

    function renderTriageSummary(items) {
        const container = document.getElementById("exec-triage-summary");
        if (!container) return;
        if (!items.length) {
            container.innerHTML = "";
            return;
        }
        const diagnostics = getLatestSystemDiagnostics?.() || {};
        const findings = Array.isArray(diagnostics.findings) ? diagnostics.findings : [];
        const queue = diagnostics.queue || {};
        const oldestPending = queue.oldest_pending || {};
        const oldestRunning = queue.oldest_running || {};
        const retryPressure = Array.isArray(queue.retry_pressure) ? queue.retry_pressure : [];
        const overRuntime = Array.isArray(queue.running_over_runtime) ? queue.running_over_runtime : [];
        const hotspots = Array.isArray(diagnostics.failure_hotspots) ? diagnostics.failure_hotspots : [];
        const active = items.filter((item) => item.stop_allowed).length;
        const attention = items.filter((item) => item.operator_attention_required).length;
        const blocked = items.filter((item) => item.requeue_block_reason).length;
        const criticalCount = items.filter((item) => String(item.operator_severity || "") === "CRITICAL").length;
        const highCount = items.filter((item) => String(item.operator_severity || "") === "HIGH").length;
        const groupsMap = new Map();
        const showSummary = Boolean(
            findings.length
            || active > 0
            || attention > 0
            || retryPressure.length
            || overRuntime.length
            || hotspots.length
            || oldestPending.exec_id
            || oldestRunning.exec_id
        );
        if (!showSummary) {
            container.innerHTML = "";
            return;
        }
        items.forEach((item) => {
            const group = String(item.related_queue_group || item.queue_group || "").trim();
            if (!group) return;
            groupsMap.set(group, (groupsMap.get(group) || 0) + 1);
        });
        const topGroups = Array.from(groupsMap.entries())
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "pt-BR"))
            .slice(0, 5);

        container.innerHTML = `
            <article class="triage-card">
                <span class="eyebrow">Incidente</span>
                <h4>Itens com atenção</h4>
                <strong>${attention}</strong>
                <p>${criticalCount} crítica(s) e ${highCount} alta(s) no recorte atual.</p>
            </article>
            <article class="triage-card">
                <span class="eyebrow">Fila</span>
                <h4>Execuções em andamento</h4>
                <strong>${active}</strong>
                <p>${overRuntime.length ? `${overRuntime.length} acima do limite` : "Sem estouro de tempo no diagnóstico atual."}</p>
            </article>
            <article class="triage-card">
                <span class="eyebrow">Fila envelhecida</span>
                <h4>Mais antigos do diagnóstico</h4>
                <div class="triage-groups">
                    ${oldestPending.exec_id ? `<button class="triage-chip" type="button" data-action="execution-preset" data-execution-preset="aged-queue">PENDENTE · ${escapeHtml(formatAgeLabel(oldestPending.age_seconds || 0))}</button>` : ""}
                    ${oldestRunning.exec_id ? `<button class="triage-chip" type="button" data-action="execution-preset" data-execution-preset="incident">RUNNING · ${escapeHtml(formatAgeLabel(oldestRunning.age_seconds || 0))}</button>` : ""}
                    ${!oldestPending.exec_id && !oldestRunning.exec_id ? '<span class="cell-meta">Sem envelhecimento relevante.</span>' : ""}
                </div>
                <p>${blocked ? `${blocked} bloqueio(s) operacional(is) no recorte atual.` : "Sem bloqueios no recorte atual."}</p>
            </article>
            <article class="triage-card">
                <span class="eyebrow">Contexto</span>
                <h4>Hotspots e pressão</h4>
                <div class="triage-groups">
                    ${hotspots.length
                        ? hotspots.slice(0, 2).map((item) => `<button class="triage-chip" type="button" data-action="execution-open-hotspot" data-automation-id="${escapeHtml(String(item.automation_id))}">${escapeHtml(item.automation_name)} · ${escapeHtml(String(item.failures_24h))}</button>`).join("")
                        : '<span class="cell-meta">Sem hotspot ativo.</span>'}
                </div>
                <div class="triage-groups" style="margin-top:8px">
                    ${retryPressure.length
                        ? retryPressure.slice(0, 3).map((item) => `<button class="triage-chip" type="button" data-action="execution-apply-pressure" data-queue-group="${escapeHtml(String(item.queue_group || ""))}" data-priority="${escapeHtml(String(item.priority || ""))}">${escapeHtml(String(item.queue_group || "default"))}/${escapeHtml(String(item.priority || "NORMAL"))} · ${escapeHtml(String(item.active_count || 0))}</button>`).join("")
                        : '<span class="cell-meta">Sem pressão de retry.</span>'}
                </div>
            </article>
        `;
        bindActionElements(container);
    }

    function getSeverityBadgeClass(severity) {
        const normalized = String(severity || "").toUpperCase();
        if (normalized === "CRITICAL") return "badge-danger";
        if (normalized === "HIGH") return "badge-warning";
        if (normalized === "MODERATE") return "badge-blue";
        return "badge-muted";
    }

    function formatAgeLabel(seconds) {
        const value = Number(seconds || 0);
        if (!Number.isFinite(value) || value <= 0) return "0s";
        if (value < 60) return `${Math.round(value)}s`;
        if (value < 3600) return `${Math.floor(value / 60)}m`;
        return `${Math.floor(value / 3600)}h ${Math.floor((value % 3600) / 60)}m`;
    }

    async function requeueExec(id) {
        const reason = safePrompt("Motivo operacional para reenfileirar esta execução:", "Requeue manual após análise operacional.");
        if (reason === null) return;
        const payload = { reason: reason.trim() || "Requeue manual após análise operacional." };
        const res = await api(`/api/executions/${id}/requeue`, "POST", payload);
        if (!res) return;
        showToast(res.message || "Execução reenfileirada.", "success");
        await Promise.all([loadOverview(), loadExecutions(getExecPage())]);
    }

    function openAutomationHistory(id) {
        const select = document.getElementById("filter-automation");
        if (select) {
            select.value = String(id);
        }
        const navBtn = document.querySelector(".nav-item[data-target=\"executions\"]");
        if (navBtn) navBtn.click();
        loadExecutions(1);
    }

    function applyQueueGroup(group) {
        const select = document.getElementById("filter-queue-group");
        if (select) {
            select.value = String(group || "");
        }
        const navBtn = document.querySelector(".nav-item[data-target=\"executions\"]");
        if (navBtn) navBtn.click();
        loadExecutions(1);
    }

    function applyPriority(priority) {
        const select = document.getElementById("filter-priority");
        if (select) {
            select.value = String(priority || "");
        }
        const navBtn = document.querySelector(".nav-item[data-target=\"executions\"]");
        if (navBtn) navBtn.click();
        loadExecutions(1);
    }

    function openHotspot(automationId) {
        const select = document.getElementById("filter-automation");
        const statusInput = document.getElementById("filter-status");
        if (select) {
            select.value = String(automationId || "");
        }
        if (statusInput) {
            statusInput.value = "ERROR";
        }
        const navBtn = document.querySelector(".nav-item[data-target=\"executions\"]");
        if (navBtn) navBtn.click();
        loadExecutions(1);
    }

    function applyPressure(queueGroup, priority) {
        const queueGroupInput = document.getElementById("filter-queue-group");
        const priorityInput = document.getElementById("filter-priority");
        if (queueGroupInput) queueGroupInput.value = String(queueGroup || "");
        if (priorityInput) priorityInput.value = String(priority || "");
        const navBtn = document.querySelector(".nav-item[data-target=\"executions\"]");
        if (navBtn) navBtn.click();
        loadExecutions(1);
    }

    function applyPreset(preset) {
        const normalized = String(preset || "all");
        const statusInput = document.getElementById("filter-status");
        const queueGroupInput = document.getElementById("filter-queue-group");
        const priorityInput = document.getElementById("filter-priority");
        const automationInput = document.getElementById("filter-automation");
        const requestedByInput = document.getElementById("filter-requested-by");
        const diagnostics = getLatestSystemDiagnostics?.() || {};
        const queue = diagnostics.queue || {};
        const oldestPending = queue.oldest_pending || {};
        const oldestRunning = queue.oldest_running || {};
        const overRuntime = Array.isArray(queue.running_over_runtime) ? queue.running_over_runtime : [];
        const retryPressure = Array.isArray(queue.retry_pressure) ? queue.retry_pressure : [];
        const hotspots = Array.isArray(diagnostics.failure_hotspots) ? diagnostics.failure_hotspots : [];
        if (requestedByInput) requestedByInput.value = "";
        if (statusInput) statusInput.value = "";
        if (queueGroupInput && normalized === "all") {
            queueGroupInput.value = "";
        }
        if (priorityInput && normalized === "all") {
            priorityInput.value = "";
        }
        if (automationInput && normalized === "all") {
            automationInput.value = "";
        }
        if (normalized === "running" && statusInput) {
            statusInput.value = "RUNNING";
        } else if (normalized === "incident") {
            if (statusInput) statusInput.value = "RUNNING";
            if (priorityInput) priorityInput.value = "HIGH";
            if (overRuntime[0]?.automation_id && automationInput) {
                automationInput.value = String(overRuntime[0].automation_id);
            } else if (oldestRunning.automation_id && automationInput) {
                automationInput.value = String(oldestRunning.automation_id);
            } else if (hotspots[0]?.automation_id && automationInput) {
                automationInput.value = String(hotspots[0].automation_id);
                if (statusInput) statusInput.value = "ERROR";
            }
        } else if (normalized === "errors" && statusInput) {
            statusInput.value = "ERROR";
            if (hotspots[0]?.automation_id && automationInput) {
                automationInput.value = String(hotspots[0].automation_id);
            }
        } else if (normalized === "aged-queue") {
            if (oldestPending.exec_id) {
                if (statusInput) statusInput.value = "PENDING";
                if (automationInput && oldestPending.automation_id) {
                    automationInput.value = String(oldestPending.automation_id);
                }
                if (queueGroupInput && oldestPending.queue_group) {
                    queueGroupInput.value = String(oldestPending.queue_group);
                }
                if (priorityInput && oldestPending.priority) {
                    priorityInput.value = String(oldestPending.priority);
                }
            } else if (oldestRunning.exec_id) {
                if (statusInput) statusInput.value = "RUNNING";
                if (automationInput && oldestRunning.automation_id) {
                    automationInput.value = String(oldestRunning.automation_id);
                }
            }
        } else if (normalized === "retry-pressure") {
            const firstPressure = retryPressure[0];
            if (firstPressure) {
                if (queueGroupInput) queueGroupInput.value = String(firstPressure.queue_group || "");
                if (priorityInput) priorityInput.value = String(firstPressure.priority || "");
            }
        } else if (normalized === "requeueable" && statusInput) {
            statusInput.value = "TERMINATED";
        } else if (normalized === "high-priority") {
            if (priorityInput) priorityInput.value = "HIGH";
        } else if (normalized === "stalled") {
            if (statusInput) statusInput.value = "RUNNING";
            if (priorityInput) priorityInput.value = "HIGH";
        }
        loadExecutions(1);
    }

    async function stopVisibleExecutions() {
        const candidates = lastLoadedItems.filter((item) => item.stop_allowed);
        if (!candidates.length) {
            showToast("Nenhuma execução visível permite parada controlada neste recorte.", "warning");
            return;
        }
        if (!confirm(`Parar ${candidates.length} execução(ões) ativa(s) visível(is)?`)) return;
        const results = await Promise.all(candidates.map(async (item) => {
            const response = await api(`/api/executions/${item.id}/stop`, "POST");
            return Boolean(response);
        }));
        const successCount = results.filter(Boolean).length;
        showToast(`${successCount}/${candidates.length} execução(ões) receberam sinal de parada.`, successCount ? "success" : "warning");
        await Promise.all([loadOverview(), loadExecutions(getExecPage())]);
    }

    async function requeueVisibleExecutions() {
        const candidates = lastLoadedItems.filter((item) => item.requeue_allowed);
        if (!candidates.length) {
            showToast("Nenhuma execução visível está liberada para requeue seguro.", "warning");
            return;
        }
        const reason = safePrompt(
            `Motivo operacional para reenfileirar ${candidates.length} execução(ões) visível(is):`,
            "Requeue em lote após triagem operacional."
        );
        if (reason === null) return;
        if (!confirm(`Confirmar requeue seguro em lote para ${candidates.length} execução(ões)?`)) return;
        const payloadReason = reason.trim() || "Requeue em lote após triagem operacional.";
        const results = await Promise.all(candidates.map(async (item) => {
            const response = await api(`/api/executions/${item.id}/requeue`, "POST", {
                reason: `${payloadReason} [Lote UI]`,
            });
            return Boolean(response);
        }));
        const successCount = results.filter(Boolean).length;
        showToast(`${successCount}/${candidates.length} execução(ões) reenfileirada(s).`, successCount ? "success" : "warning");
        await Promise.all([loadOverview(), loadExecutions(getExecPage())]);
    }

    return {
        loadExecutions,
        renderExecutionsTable,
        openAutomationHistory,
        requeueExec,
        applyPreset,
        applyQueueGroup,
        applyPriority,
        openHotspot,
        applyPressure,
        stopVisibleExecutions,
        requeueVisibleExecutions,
    };
}
