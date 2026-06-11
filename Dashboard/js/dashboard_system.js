import { normalizeDiagnosticsPayload } from "./contracts.js";
import { getSystemActionRequest } from "./system_actions.js";
import { bindActionElements } from "./action_registry.js";
import { renderTable } from "./ui_manager.js";

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
        getLastCorrelationId,
        safePrompt,
    } = ctx;

    async function loadSystem() {
        renderSystemLoadingState();
        const [health, diagnostics, audit] = await Promise.all([
            api("/api/system/health"),
            api("/api/system/diagnostics"),
            api("/api/system/audit?limit=25"),
        ]);

        if (health) renderHealthCards(health);
        if (diagnostics) {
            const normalizedDiagnostics = normalizeDiagnosticsPayload(diagnostics);
            setLatestSystemDiagnostics(normalizedDiagnostics);
            updateWorkerActionButton(normalizedDiagnostics);
            renderWorkerDetails(normalizedDiagnostics);
            renderDiagnosticFindings(normalizedDiagnostics);
            renderRuntimeContract(normalizedDiagnostics);
        } else {
            renderSystemUnavailableState();
        }
        if (audit) renderAuditTable(audit);

        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    function renderSystemLoadingState() {
        const workerDetails = document.getElementById("worker-details");
        const diagnosticFindings = document.getElementById("diagnostic-findings");
        const diagnosticContract = document.getElementById("diagnostic-contract");
        const auditTbody = document.getElementById("audit-tbody");

        if (workerDetails) {
            workerDetails.innerHTML = `
                <div class="info-row"><span>Status:</span><b>Carregando...</b></div>
                <div class="info-row"><span>PID:</span><b>-</b></div>
                <div class="info-row"><span>Concluídas:</span><b>-</b></div>
                <div class="info-row"><span>Falhas:</span><b>-</b></div>
                <div class="info-row"><span>Ativas:</span><b>-</b></div>
                <div class="info-row"><span>Fila Ativa:</span><b>-</b></div>
                <div class="info-row"><span>Pendente mais antigo:</span><b>-</b></div>
                <div class="info-row"><span>Em execução mais antiga:</span><b>-</b></div>
                <div class="info-row"><span>Acima do limite:</span><b>-</b></div>
                <div class="info-row"><span>Pressão de retry:</span><b>-</b></div>
                <div class="info-row"><span>Timeout por grupo (24h):</span><b>-</b></div>
                <div class="info-row"><span>Heartbeat:</span><b>-</b></div>
                <div class="info-row"><span>Correlação API:</span><b>-</b></div>
                <div class="info-row"><span>Versão:</span><b>-</b></div>
            `;
        }
        if (diagnosticFindings) {
            diagnosticFindings.innerHTML = `
                <div class="finding-card info">
                    <span class="badge badge-muted">Carregando</span>
                    <div>
                        <strong>Leitura diagnóstica em andamento</strong>
                        <p>Aguardando resposta da API para renderizar achados operacionais.</p>
                    </div>
                </div>
            `;
        }
        if (diagnosticContract) {
            diagnosticContract.innerHTML = `
                <article class="contract-card">
                    <h4>Contrato de dados</h4>
                    <p>Leitura diagnóstica em andamento.</p>
                    <small>A interface aguarda o payload operacional do Orchestrator.</small>
                </article>
                <article class="contract-card">
                    <h4>Base operacional</h4>
                    <p>Status: <strong>Carregando...</strong></p>
                    <small>Atenção: - · Incidente: -</small>
                </article>
                <article class="contract-card">
                    <h4>Performance da API</h4>
                    <p>Coleta: <strong>Aguardando</strong></p>
                    <small>Os tempos de montagem por etapa aparecerão após a resposta da API.</small>
                </article>
            `;
        }
        if (auditTbody) {
            auditTbody.innerHTML = "<tr><td colspan=\"5\">Carregando auditoria...</td></tr>";
        }
    }

    function renderSystemUnavailableState() {
        const diagnosticFindings = document.getElementById("diagnostic-findings");
        const diagnosticContract = document.getElementById("diagnostic-contract");
        const workerDetails = document.getElementById("worker-details");

        if (diagnosticFindings) {
            diagnosticFindings.innerHTML = `
                <div class="finding-card error">
                    <span class="badge badge-danger">Indisponível</span>
                    <div>
                        <strong>Diagnóstico operacional indisponível</strong>
                        <p>A API não respondeu com o payload esperado. Verifique a conexão ou recarregue a página.</p>
                    </div>
                </div>
            `;
        }
        if (diagnosticContract) {
            diagnosticContract.innerHTML = `
                <article class="contract-card">
                    <h4>Contrato de dados</h4>
                    <p>Status: <strong>Indisponível</strong></p>
                    <small>O dashboard não conseguiu ler o diagnóstico operacional agora.</small>
                    <small>Ação recomendada: recarregar o painel ou confirmar a API.</small>
                </article>
            `;
        }
        if (workerDetails) {
            workerDetails.innerHTML = `
                <div class="info-row"><span>Status:</span><b>Indisponível</b></div>
                <div class="info-row"><span>PID:</span><b>-</b></div>
                <div class="info-row"><span>Correlação API:</span><b>-</b></div>
            `;
        }
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
        const trace = diagnostics.trace || {};
        const runningOverRuntime = Array.isArray(queue.running_over_runtime) ? queue.running_over_runtime : [];
        const retryPressure = Array.isArray(queue.retry_pressure) ? queue.retry_pressure : [];
        const timeoutByGroup = Array.isArray(queue.timeouts_24h_by_group) ? queue.timeouts_24h_by_group : [];
        const overRuntimeLabel = runningOverRuntime.length
            ? `${runningOverRuntime.length} acima do limite`
            : "0";
        const retryLabel = retryPressure.length
            ? retryPressure.slice(0, 2).map((item) => `${item.queue_group}/${item.priority}:${item.active_count}`).join(" | ")
            : "Sem pressão";
        const timeoutLabel = timeoutByGroup.length
            ? timeoutByGroup.slice(0, 2).map((item) => `${item.queue_group}:${item.timeouts_24h}`).join(" | ")
            : "Sem timeout";

        details.innerHTML = `
        <div class="info-row"><span>Status:</span><b>${worker.is_alive ? "ONLINE" : "OFFLINE"}</b></div>
        <div class="info-row"><span>PID:</span><b>${worker.pid || "-"}</b></div>
        <div class="info-row"><span>Concluídas:</span><b>${worker.tasks_completed || 0}</b></div>
        <div class="info-row"><span>Falhas:</span><b>${worker.tasks_failed || 0}</b></div>
        <div class="info-row"><span>Ativas:</span><b>${worker.active_tasks || 0}</b></div>
        <div class="info-row"><span>Fila Ativa:</span><b>${queue.active_count || 0}</b></div>
        <div class="info-row"><span>Pendente mais antigo:</span><b>${formatQueueAge(queue.oldest_pending)}</b></div>
        <div class="info-row"><span>Em execução mais antiga:</span><b>${formatQueueAge(queue.oldest_running)}</b></div>
        <div class="info-row"><span>Acima do limite:</span><b>${escapeHtml(overRuntimeLabel)}</b></div>
        <div class="info-row"><span>Pressão de retry:</span><b>${escapeHtml(retryLabel)}</b></div>
        <div class="info-row"><span>Timeout por grupo (24h):</span><b>${escapeHtml(timeoutLabel)}</b></div>
        <div class="info-row"><span>Heartbeat:</span><b>${heartbeat.last_ping_age_seconds == null ? "-" : formatDuration(heartbeat.last_ping_age_seconds)}</b></div>
        <div class="info-row"><span>Correlação API:</span><b>${escapeHtml(trace.correlation_id || getLastCorrelationId() || "SYSTEM")}</b></div>
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
                    <p>Diagnóstico atual: ${escapeHtml(translateOverviewStatus(diagnostics.overall_status || "healthy"))}.</p>
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
                <button class="btn btn-outline btn-sm" type="button" data-action="system-action" data-system-action="show_running">
                    Ver ativas
                </button>
                <button class="btn btn-outline btn-sm" type="button" data-action="system-action" data-system-action="show_errors">
                    Ver falhas
                </button>
                ${operatorActions.map((item) => `
                    <button class="btn btn-outline btn-sm" type="button" data-action="system-action" data-system-action="${escapeHtml(item.action_code)}">
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
                ? `<button class="btn btn-outline btn-sm" data-action="system-action" data-system-action="${escapeHtml(shortcut.action)}">${escapeHtml(shortcut.label)}</button>`
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
        bindActionElements(container);
    }

    function renderRuntimeContract(diagnostics) {
        const container = document.getElementById("diagnostic-contract");
        if (!container) return;

        const checks = Array.isArray(diagnostics.checks) ? diagnostics.checks : [];
        const baseline = diagnostics.operational_baseline || {};
        const baselineMetrics = Array.isArray(baseline.metrics) ? baseline.metrics : [];
        const recovery = diagnostics.recovery || {};
        const trace = diagnostics.trace || {};
        const failureHotspots = Array.isArray(diagnostics.failure_hotspots) ? diagnostics.failure_hotspots : [];
        const activeByGroup = diagnostics.queue?.active_by_group || {};
        const lightActions = Array.isArray(recovery.light_actions) ? recovery.light_actions : [];
        const strongActions = Array.isArray(recovery.strong_actions) ? recovery.strong_actions : [];
        const baselineStatus = String(baseline.status || "healthy").toUpperCase();
        const baselineSummary = baselineMetrics
            .filter((item) => item.status && item.status !== "healthy")
            .slice(0, 2)
            .map((item) => `${item.label}: ${translateOverviewStatus(item.status)}`)
            .join(" | ");
        const performance = diagnostics.performance || {};
        const timings = performance.timings_ms || {};
        const timingEntries = Object.entries(timings)
            .filter(([, value]) => Number.isFinite(Number(value)))
            .slice(0, 5)
            .map(([key, value]) => `${key}: ${Number(value).toFixed(1)} ms`);
        const performanceSummary = timingEntries.length
            ? timingEntries.join(" | ")
            : "Tempos de montagem indisponíveis";

        const checksHtml = checks.length
            ? checks.map((item) => `
                <article class="contract-card">
                    <h4>${escapeHtml(item.label || item.code || "check")}</h4>
                    <p>Status: <strong>${escapeHtml(String(item.status || "unknown").toUpperCase())}</strong></p>
                    <small>${escapeHtml(item.detail || "-")}</small>
                    ${item.value ? `<small>Valor: ${escapeHtml(String(item.value))}</small>` : ""}
                </article>
            `).join("")
            : `<article class="contract-card"><h4>Verificações indisponíveis</h4><p>O diagnóstico ainda não retornou verificações do ambiente operacional.</p></article>`;

        const recommended = recovery.recommended_action
            ? `<small>Ação recomendada: ${escapeHtml(recovery.recommended_action)}</small>`
            : "";

        const groupEntries = Object.entries(activeByGroup).slice(0, 5);
        const groupsHtml = groupEntries.length
            ? `<article class="contract-card">
                <h4>Grupos ativos</h4>
                <p>Atalhos para abrir a bancada de triagem já filtrada por grupo operacional.</p>
                <div class="triage-groups">
                    ${groupEntries.map(([group, count]) => `
                        <button class="triage-chip" type="button" data-action="execution-filter-group" data-queue-group="${escapeHtml(group)}">
                            ${escapeHtml(group)} · ${escapeHtml(String(count))}
                        </button>
                    `).join("")}
                </div>
            </article>`
            : "";

        const hotspotsHtml = failureHotspots.length
            ? `<article class="contract-card">
                <h4>Focos de falha</h4>
                <p>Atalhos para abrir a bancada diretamente nas automações com mais falhas nas últimas 24h.</p>
                <div class="triage-groups">
                    ${failureHotspots.slice(0, 5).map((item) => `
                        <button class="triage-chip" type="button" data-action="execution-open-hotspot" data-automation-id="${escapeHtml(String(item.automation_id))}">
                            ${escapeHtml(item.automation_name)} · ${escapeHtml(String(item.failures_24h))}
                        </button>
                    `).join("")}
                </div>
                <small>O atalho aplica recorte por automação e status de falha para acelerar a análise.</small>
            </article>`
            : "";

        container.innerHTML = `
            <article class="contract-card">
                <h4>Contrato de dados</h4>
                <p>Versão ativa: <strong>${escapeHtml(diagnostics.contract_version || "legacy")}</strong></p>
                <small>O dashboard consome este contrato para visão geral, diagnósticos e ações operacionais.</small>
                <small>Correlação: ${escapeHtml(trace.correlation_id || getLastCorrelationId() || "SYSTEM")}</small>
                ${recommended}
            </article>
            <article class="contract-card">
                <h4>Base operacional</h4>
                <p>Status: <strong>${escapeHtml(translateOverviewStatus(baselineStatus))}</strong></p>
                <small>Atenção: ${escapeHtml(String(baseline.attention_count || 0))} · Incidente: ${escapeHtml(String(baseline.incident_count || 0))}</small>
                <small>${escapeHtml(baselineSummary || "Sem desvios relevantes na base operacional atual.")}</small>
                ${baseline.recommended_action ? `<small>Ação recomendada: ${escapeHtml(String(baseline.recommended_action))}</small>` : ""}
            </article>
            <article class="contract-card">
                <h4>Performance da API</h4>
                <p>Status: <strong>${escapeHtml(performanceSummary)}</strong></p>
                <small>Tempos de montagem por etapa do diagnóstico e do overview para localizar gargalos reais.</small>
                ${timingEntries.length ? `<small>Etapas: ${escapeHtml(timingEntries.join(" • "))}</small>` : ""}
            </article>
            <article class="contract-card">
                <h4>Recuperação leve</h4>
                <p>${escapeHtml(lightActions.join(", ") || "Nenhuma ação sugerida")}</p>
                <small>Ações para ativação do processador, recarga da agenda, checkpoint e triagem sem reinício forte.</small>
            </article>
            <article class="contract-card">
                <h4>Recuperação forte</h4>
                <p>${escapeHtml(strongActions.join(", ") || "Nenhuma ação sugerida")}</p>
                <small>Ações para recuperação canônica e proteção operacional antes de mudanças maiores.</small>
            </article>
            ${groupsHtml}
            ${hotspotsHtml}
            ${checksHtml}
        `;
        bindActionElements(container);
    }

    function getWorkerSystemAction(diagnostics) {
        const worker = diagnostics?.worker || {};
        if (!worker.is_alive) {
            return { action: "worker_recover", label: "Recuperar processador", icon: "refresh-cw" };
        }
        return { action: "worker_wakeup", label: "Ativar processador", icon: "activity" };
    }

    function updateWorkerActionButton(diagnostics, override = null) {
        const button = document.getElementById("system-worker-action");
        if (!button) return;

        const descriptor = override || getWorkerSystemAction(diagnostics);
        button.innerHTML = `<i data-lucide="${descriptor.icon || "activity"}"></i>${escapeHtml(descriptor.label || "Ativar processador")}`;
        button.disabled = Boolean(descriptor.disabled);
        button.dataset.systemAction = descriptor.action || "";
        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    function renderAuditTable(items) {
        renderTable(document.getElementById("audit-tbody"), items, (item) => `
        <tr>
            <td>${formatDate(item.timestamp)}</td>
            <td><span class="badge badge-muted">${escapeHtml(item.action || "-")}</span></td>
            <td>${escapeHtml(item.entity_type || "-")}</td>
            <td>${escapeHtml(item.entity_id || "-")}</td>
            <td>${escapeHtml(item.actor || "-")}</td>
        </tr>
    `, "Sem eventos de auditoria.", 5);
    }

    async function callSystemAction(action) {
        if (!action) return;
        let request = getSystemActionRequest(action);
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
            const retention = safePrompt("Informe retenção em dias para purge (mínimo 7):", "90");
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
        return `${sec.toFixed(1)}s`;
    }

    function translateOverviewStatus(status) {
        switch (String(status || "").toLowerCase()) {
            case "healthy": return "saudável";
            case "attention": return "atenção";
            case "incident": return "incidente";
            case "unhealthy": return "não saudável";
            case "warn": return "atenção";
            case "ok": return "ok";
            case "error": return "erro";
            default: return String(status || "-");
        }
    }

    return {
        loadSystem,
        callSystemAction,
        updateWorkerActionButton,
    };
}
