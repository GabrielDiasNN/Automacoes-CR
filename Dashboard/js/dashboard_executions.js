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
    } = ctx;

    async function loadExecutions(page = getExecPage()) {
        setExecPage(page);

        const params = new URLSearchParams({
            page: String(getExecPage()),
            per_page: String(execPerPage),
        });

        const status = getValue("filter-status");
        const automationId = getValue("filter-automation");
        const requestedBy = getValue("filter-requested-by");
        const dateFrom = getValue("filter-date-from");
        const dateTo = getValue("filter-date-to");

        if (status) params.set("status", status);
        if (automationId) params.set("automation_id", automationId);
        if (requestedBy) params.set("requested_by", requestedBy);
        if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00`);
        if (dateTo) params.set("date_to", `${dateTo}T23:59:59`);

        const data = await api(`/api/executions?${params.toString()}`);
        if (!data) return;

        renderExecutionsTable(data.items || []);
        ui.renderPagination(data.total || 0, data.page || 1, data.pages || 1, "exec-pagination", (nextPage) => {
            loadExecutions(nextPage);
        });

        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    function renderExecutionsTable(items) {
        const tbody = document.getElementById("exec-tbody");
        if (!tbody) return;

        if (!items.length) {
            tbody.innerHTML = "<tr><td colspan=\"8\">Nenhuma execução encontrada para os filtros selecionados.</td></tr>";
            return;
        }

        tbody.innerHTML = items.map((ex) => `
        <tr onclick="openLogModal('${ex.id}')" style="cursor:pointer">
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
    }

    function renderRecoveryCell(ex) {
        const parts = [];
        if (ex.failure_reason) parts.push(`<span class="badge badge-muted">${escapeHtml(ex.failure_reason)}</span>`);
        if (ex.recovery_action && ex.recovery_action !== "NONE") parts.push(`<small>${escapeHtml(ex.recovery_action)}</small>`);
        if (Number(ex.max_retries || 0) > 0) {
            parts.push(`<small>Retry ${Number(ex.retry_count || 0)}/${Number(ex.max_retries || 0)}</small>`);
        }
        return parts.length ? `<div class="recovery-cell">${parts.join("")}</div>` : "-";
    }

    function renderExecutionActions(ex) {
        if (["RUNNING", "PENDING"].includes(ex.status)) {
            return `<button class="btn btn-danger btn-sm" onclick="event.stopPropagation();stopExec('${ex.id}')" title="Parar execução"><i data-lucide="square"></i></button>`;
        }
        if (canRequeue(ex)) {
            return `<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();requeueExec('${ex.id}')" title="Reenfileirar com auditoria"><i data-lucide="rotate-cw"></i></button>`;
        }
        return "-";
    }

    function canRequeue(ex) {
        const queueable = ["ERROR", "TIMEOUT", "TERMINATED", "FAILED_BY_REBOOT", "REQUEUED"];
        if (!queueable.includes(ex.status)) return false;
        return Number(ex.retry_count || 0) < Number(ex.max_retries || 0);
    }

    async function requeueExec(id) {
        const reason = prompt("Motivo operacional para reenfileirar esta execução:", "Requeue manual após análise operacional.");
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

    return {
        loadExecutions,
        renderExecutionsTable,
        openAutomationHistory,
        requeueExec,
    };
}
