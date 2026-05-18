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
            tbody.innerHTML = "<tr><td colspan=\"7\">Nenhuma execução encontrada para os filtros selecionados.</td></tr>";
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
            <td>${["RUNNING", "PENDING"].includes(ex.status) ? `<button class="btn btn-danger btn-sm" onclick="event.stopPropagation();stopExec('${ex.id}')"><i data-lucide="square"></i></button>` : "-"}</td>        </tr>
    `).join("");
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
    };
}
