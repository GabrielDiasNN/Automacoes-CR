export function createSystemModule(ctx) {
    const {
        api,
        showToast,
        formatDate,
        escapeHtml,
        loadOverview,
        loadExecutions,
        getExecPage,
        setLatestSystemDiagnostics,
        getLatestSystemDiagnostics,
    } = ctx;

    async function loadSystem() {
        const [health, diagnostics, audit] = await Promise.all([
            api("/api/system/health"),
            api("/api/system/diagnostics"),
            api("/api/system/audit?limit=25"),
        ]);

        if (health) renderHealthCards(health);
        if (diagnostics) {
            setLatestSystemDiagnostics(diagnostics);
            updateWorkerActionButton(diagnostics);
            renderWorkerDetails(diagnostics);
            renderDiagnosticFindings(diagnostics);
        }
        if (audit) renderAuditTable(audit);

        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    function renderHealthCards(health) {
        setHealthCard("health-db", health.database === "online", health.database);
        setHealthCard("health-sched", health.scheduler === "executando", health.scheduler);
        setHealthCard("health-worker", health.worker?.is_alive, health.worker?.is_alive ? "Ativo" : "Inativo");
        setHealthCard("health-disk", true, `${Number(health.disk_usage_mb || 0).toFixed(1)} MB`);
    }

    function setHealthCard(id, ok, text) {
        const card = document.getElementById(id);
        if (!card) return;

        card.classList.remove("ok", "warn");
        card.classList.add(ok ? "ok" : "warn");

        const value = card.querySelector(".health-value");
        if (value) value.textContent = text || "-";
    }

    function renderWorkerDetails(diagnostics) {
        const details = document.getElementById("worker-details");
        if (!details) return;

        const worker = diagnostics.worker || {};
        const queue = diagnostics.queue || {};
        const heartbeat = diagnostics.heartbeat || {};

        details.innerHTML = `
        <div class="info-row"><span>Status:</span><b>${worker.is_alive ? "ONLINE" : "OFFLINE"}</b></div>
        <div class="info-row"><span>PID:</span><b>${worker.pid || "-"}</b></div>
        <div class="info-row"><span>Concluídas:</span><b>${worker.tasks_completed || 0}</b></div>
        <div class="info-row"><span>Falhas:</span><b>${worker.tasks_failed || 0}</b></div>
        <div class="info-row"><span>Ativas:</span><b>${worker.active_tasks || 0}</b></div>
        <div class="info-row"><span>Fila Ativa:</span><b>${queue.active_count || 0}</b></div>
        <div class="info-row"><span>Pendente mais antigo:</span><b>${formatQueueAge(queue.oldest_pending)}</b></div>
        <div class="info-row"><span>RUNNING mais antigo:</span><b>${formatQueueAge(queue.oldest_running)}</b></div>
        <div class="info-row"><span>Heartbeat:</span><b>${heartbeat.last_ping_age_seconds == null ? "-" : formatDuration(heartbeat.last_ping_age_seconds)}</b></div>
        <div class="info-row"><span>Versão:</span><b>${worker.version || "-"}</b></div>
    `;
    }

    function formatQueueAge(item) {
        if (!item || !item.exec_id) return "-";
        return `${escapeHtml(item.exec_id)} · ${formatDuration(item.age_seconds || 0)}`;
    }

    function renderDiagnosticFindings(diagnostics) {
        const container = document.getElementById("diagnostic-findings");
        if (!container) return;

        const findings = Array.isArray(diagnostics.findings) ? diagnostics.findings : [];
        const operatorActions = Array.isArray(diagnostics.operator_actions) ? diagnostics.operator_actions : [];
        if (!findings.length) {
            container.innerHTML = `
            <div class="finding-card info">
                <span class="badge badge-success">OK</span>
                <div>
                    <strong>Sem achados críticos</strong>
                    <p>Diagnóstico atual: ${escapeHtml(diagnostics.overall_status || "healthy")}.</p>
                </div>
            </div>
        `;
            return;
        }

        const badgeClass = {
            ERROR: "badge-danger",
            WARN: "badge-warning",
            INFO: "badge-blue",
        };

        const workerAction = getWorkerSystemAction(diagnostics);
        const actionByComponent = {
            worker: workerAction,
            queue: workerAction,
            scheduler: { action: "scheduler_reload", label: "Sincronizar agenda" },
            database: { action: "checkpoint", label: "Executar checkpoint" },
        };

        const actionsHtml = operatorActions.length
            ? `
            <div class="operator-actions">
                ${operatorActions.map((item) => `
                    <button class="btn btn-outline btn-sm" type="button" onclick="callSystemAction('${escapeHtml(item.action_code)}')">
                        ${escapeHtml(item.action_label || item.action_code)}
                    </button>
                `).join("")}
            </div>
        `
            : "";

        const findingsHtml = findings.map((item) => {
            const severity = item.severity || "INFO";
            const shortcut = item.action_code
                ? { action: item.action_code, label: item.action_label || item.action_hint }
                : actionByComponent[item.component];
            const actionHtml = shortcut
                ? `<button class="btn btn-outline btn-sm" onclick="callSystemAction('${shortcut.action}')">${shortcut.label}</button>`
                : "";
            return `
            <article class="finding-card ${severity.toLowerCase()}">
                <span class="badge ${badgeClass[severity] || "badge-muted"}">${escapeHtml(severity)}</span>
                <div>
                    <strong>${escapeHtml(item.component || "sistema")}</strong>
                    <p>${escapeHtml(item.message || "-")}</p>
                    ${item.impact ? `<small>${escapeHtml(item.impact)}</small>` : ""}
                    <small>${escapeHtml(item.action_hint || "Revisar diagnóstico operacional.")}</small>
                    <div style="margin-top:8px">${actionHtml}</div>
                </div>
            </article>
        `;
        }).join("");

        container.innerHTML = actionsHtml + findingsHtml;
    }

    function getWorkerSystemAction(diagnostics) {
        const worker = diagnostics?.worker || {};
        if (!worker.is_alive) {
            return { action: "worker_recover", label: "Recuperar worker", icon: "refresh-cw" };
        }
        return { action: "worker_wakeup", label: "Acordar worker", icon: "activity" };
    }

    function updateWorkerActionButton(diagnostics, override = null) {
        const button = document.getElementById("system-worker-action");
        if (!button) return;

        const descriptor = override || getWorkerSystemAction(diagnostics);
        button.innerHTML = `<i data-lucide="${descriptor.icon || "activity"}"></i>${escapeHtml(descriptor.label || "Acordar worker")}`;
        button.disabled = Boolean(descriptor.disabled);
        button.onclick = descriptor.action ? () => callSystemAction(descriptor.action) : null;
        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    function renderAuditTable(items) {
        const tbody = document.getElementById("audit-tbody");
        if (!tbody) return;

        if (!items.length) {
            tbody.innerHTML = "<tr><td colspan=\"5\">Sem eventos de auditoria.</td></tr>";
            return;
        }

        tbody.innerHTML = items.map((item) => `
        <tr>
            <td>${formatDate(item.timestamp)}</td>
            <td><span class="badge badge-muted">${escapeHtml(item.action || "-")}</span></td>
            <td>${escapeHtml(item.entity_type || "-")}</td>
            <td>${escapeHtml(item.entity_id || "-")}</td>
            <td>${escapeHtml(item.actor || "-")}</td>
        </tr>
    `).join("");
    }

    async function callSystemAction(action) {
        if (!action) return;

        const map = {
            resume_all: { path: "/api/automations/control/resume-all", method: "POST", label: "retomar todas as automações" },
            pause_all: { path: "/api/automations/control/pause-all", method: "POST", label: "pausar todas as automações" },
            scheduler_reload: { path: "/api/system/scheduler/reload", method: "POST", label: "sincronizar agenda do scheduler" },
            worker_wakeup: { path: "/api/system/worker/wakeup", method: "POST", label: "acordar worker para validar fila" },
            worker_recover: { path: "/api/system/worker/recover", method: "POST", label: "recuperar Orchestrator e worker" },
            checkpoint: { path: "/api/system/checkpoint", method: "POST", label: "executar checkpoint WAL" },
            backup: { path: "/api/system/backup", method: "POST", label: "executar backup do banco" },
        };

        let request = map[action];
        if (action === "show_running" || action === "show_errors") {
            const status = action === "show_running" ? "RUNNING" : "ERROR";
            const select = document.getElementById("filter-status");
            if (select) select.value = status;
            const navBtn = document.querySelector(".nav-item[data-target=\"executions\"]");
            if (navBtn) navBtn.click();
            await loadExecutions(1);
            return;
        }
        if (action === "purge") {
            const retention = prompt("Informe retenção em dias para purge (mínimo 7):", "90");
            if (retention === null) return;
            const days = Number(retention);
            if (!Number.isFinite(days) || days < 7) {
                showToast("Valor inválido. Informe um número maior ou igual a 7.", "warning");
                return;
            }
            request = {
                path: `/api/system/purge?retention_days=${Math.floor(days)}`,
                method: "POST",
                label: `limpar execuções com retenção de ${Math.floor(days)} dia(s)`,
            };
        }

        if (!request) {
            showToast("Ação não reconhecida.", "warning");
            return;
        }

        if (!confirm(`Confirmar ação: ${request.label}?`)) return;

        const res = await api(request.path, request.method);
        if (res) {
            showToast(res.message || "Ação concluída com sucesso.", "success");
            if (action === "worker_recover") {
                updateWorkerActionButton(getLatestSystemDiagnostics(), {
                    action: null,
                    label: "Recuperando...",
                    icon: "refresh-cw",
                    disabled: true,
                });
                setTimeout(() => {
                    loadSystem();
                }, 20000);
                return;
            }
            await Promise.all([loadOverview(), loadExecutions(getExecPage()), loadSystem()]);
        }
    }

    function formatDuration(value) {
        const sec = Number(value || 0);
        if (!Number.isFinite(sec) || sec < 0) return "-";
        if (sec < 60) return `${Math.round(sec)}s`;
        if (sec < 3600) {
            const minutes = Math.floor(sec / 60);
            const remain = Math.round(sec % 60);
            return remain > 0 ? `${minutes}m ${remain}s` : `${minutes}m`;
        }
        const hours = Math.floor(sec / 3600);
        const minutes = Math.floor((sec % 3600) / 60);
        return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
    }

    return {
        loadSystem,
        callSystemAction,
        updateWorkerActionButton,
    };
}
