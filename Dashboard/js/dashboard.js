/**
 * dashboard.js - Central de Automações v6.3.0
 * SPA operacional do orquestrador.
 */

import { api, showToast, formatDate, getBadgeClass, translateStatus } from './api.js';
import * as ui from './ui_manager.js';
import * as ide from './ide_service.js';
import * as engine from './execution_engine.js';

const EXEC_PER_PAGE = 15;
let execPage = 1;
let charts = { performance: null, status: null };
let scheduleTimes = [];
let scheduleDays = new Set();
let cachedAutomations = [];
let cachedJobs = [];
let isSavingAutomation = false;

window.automations = [];

document.addEventListener('DOMContentLoaded', () => {
    ui.initNavigation();
    bindStaticEvents();
    Promise.all([loadOverview(), loadConfig()]);

    window.addEventListener('view-changed', (e) => {
        const target = e.detail.target;
        if (target === 'dashboard') loadOverview();
        if (target === 'executions') loadExecutions(1);
        if (target === 'automations') loadConfig();
        if (target === 'observability') loadOverview();
        if (target === 'system') loadSystem();
        if (target === 'env') ide.loadEnv();
    });
});

window.runAuto = async (id) => {
    const execId = await engine.runAuto(id);
    if (execId) {
        await Promise.all([loadOverview(), loadExecutions(execPage)]);
        engine.openLogModal(execId);
    }
};
window.stopExec = async (id) => {
    if (await engine.stopExec(id)) {
        await Promise.all([loadOverview(), loadExecutions(execPage)]);
    }
};
window.openLogModal = engine.openLogModal;
window.closeLogModal = engine.closeLogModal;
window.openJsonModal = ide.openJsonModal;
window.loadSelectedJsonFile = ide.loadSelectedJsonFile;
window.saveJsonFile = ide.saveJsonFile;
window.openIdeModal = ide.openIdeModal;
window.loadSelectedIdeFile = ide.loadSelectedIdeFile;
window.saveIdeFile = ide.saveIdeFile;
window.saveEnv = ide.saveEnv;

window.openCreateModal = () => openAutomationModal();
window.saveAuto = (event) => saveAutomation(event);
window.addScheduleTime = () => addScheduleTimeFromInput();
window.toggleGlobalTestMode = (enabled) => toggleGlobalTestMode(enabled);
window.callSystemAction = (action) => callSystemAction(action);
window.handleSearch = () => handleSearch();
window.openEditAuto = (id) => openAutomationModal(id);
window.removeScheduleTime = (hhmm) => removeScheduleTime(hhmm);

function bindStaticEvents() {
    document.querySelectorAll('.day-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const day = Number(btn.dataset.day);
            if (scheduleDays.has(day)) {
                scheduleDays.delete(day);
                btn.classList.remove('active');
            } else {
                scheduleDays.add(day);
                btn.classList.add('active');
            }
            renderScheduleSummary();
        });
    });

    const modal = document.getElementById('modal-auto');
    if (modal) {
        modal.addEventListener('close', () => resetScheduleBuilder());
    }
}

async function loadOverview() {
    const overview = await api('/api/system/overview');
    if (!overview) {
        ui.updateConnectionStatus(false);
        return;
    }
    ui.updateConnectionStatus(true);

    applyOverviewKpis(overview);
    renderOverviewInsights(overview);
    renderOverviewCharts(overview);
    await populateControlTable(overview);
    syncGlobalTestToggle(overview.automations || []);
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function applyOverviewKpis(overview) {
    const kpis = overview.kpis || {};
    const health = overview.health || {};

    setText('val-total', kpis.active_automations ?? 0);

    const success24 = Number(kpis.success_24h || 0);
    const errors24 = Number(kpis.errors_24h || 0);
    const total24 = success24 + errors24;
    const successRate = total24 > 0 ? ((success24 / total24) * 100).toFixed(1) : '100.0';

    setText('val-success-rate', `${successRate}%`);
    setText('val-errors', errors24);

    const avgDuration = estimateAverageDuration(overview);
    setText('val-avg-time', formatSeconds(avgDuration));

    setText('trend-success', `${success24} sucesso(s) / 24h`);
    setText('trend-errors', `${errors24} falha(s) / 24h`);
    setText('trend-total', `${overview.scheduler?.jobs_loaded ?? 0} agenda(s)`);
    setText('trend-time', `CPU ${Math.round(health.cpu_usage || 0)}% • RAM ${Math.round(health.ram_usage_percent || 0)}%`);
}

function estimateAverageDuration(overview) {
    const recent = Array.isArray(overview.recent) ? overview.recent : [];
    const values = recent
        .map((item) => Number(item.duration_seconds || 0))
        .filter((item) => Number.isFinite(item) && item > 0);
    if (!values.length) return 0;
    return values.reduce((acc, item) => acc + item, 0) / values.length;
}

function renderOverviewInsights(overview) {
    const topFail = (overview.top_failures || [])[0];
    if (topFail) {
        setText('insight-top-fail', `${topFail.automation_name} (${topFail.failures})`);
    } else {
        setText('insight-top-fail', 'Nenhuma falha registrada em 24h');
    }

    const savedHours = (overview.kpis?.success_24h || 0) * 0.2;
    setText('insight-time-saved', `${savedHours.toFixed(1)}h estimadas no dia`);

    const nextWindow = overview.kpis?.next_window;
    setText('insight-next-window', nextWindow || 'Sem janela agendada');
}

function renderOverviewCharts(overview) {
    renderPerformanceChart(overview);
    renderStatusChart(overview);
}

function renderPerformanceChart(overview) {
    const container = document.getElementById('chart-performance');
    if (!container || typeof ApexCharts === 'undefined') return;
    if (!isRenderable(container)) return;

    const recent = Array.isArray(overview.recent) ? overview.recent : [];
    const byAutomation = new Map();

    recent.forEach((item) => {
        if (!item.automation_name || !item.duration_seconds) return;
        const key = item.automation_name;
        if (!byAutomation.has(key)) byAutomation.set(key, []);
        byAutomation.get(key).push(Number(item.duration_seconds));
    });

    const labels = [];
    const values = [];
    Array.from(byAutomation.entries())
        .slice(0, 8)
        .forEach(([name, durations]) => {
            const avg = durations.reduce((acc, d) => acc + d, 0) / durations.length;
            labels.push(name);
            values.push(Number((avg / 60).toFixed(2)));
        });

    if (!labels.length) {
        container.innerHTML = '<div class="empty-chart">Sem dados de performance no período recente.</div>';
        if (charts.performance) {
            charts.performance.destroy();
            charts.performance = null;
        }
        return;
    }

    const options = {
        chart: { type: 'bar', height: 280, toolbar: { show: false } },
        series: [{ name: 'Tempo médio (min)', data: values }],
        xaxis: { categories: labels },
        colors: ['#2f6fed'],
        dataLabels: { enabled: false },
        theme: { mode: 'dark' },
        tooltip: { theme: 'dark' },
        legend: { labels: { colors: '#aab7c7' } },
        yaxis: { labels: { formatter: (v) => `${v.toFixed(1)}m` } },
        grid: { borderColor: '#263345' },
    };

    if (charts.performance) charts.performance.destroy();
    charts.performance = new ApexCharts(container, options);
    charts.performance.render();
}

function renderStatusChart(overview) {
    const container = document.getElementById('chart-status');
    if (!container || typeof ApexCharts === 'undefined') return;
    if (!isRenderable(container)) return;

    const breakdown = overview.status_breakdown || {};
    const labels = ['Sucesso', 'Erro', 'Executando', 'Pendente', 'Interrompido'];
    const series = [
        Number(breakdown.SUCCESS || 0),
        Number(breakdown.ERROR || 0),
        Number(breakdown.RUNNING || 0),
        Number(breakdown.PENDING || 0),
        Number(breakdown.TERMINATED || 0),
    ];

    if (!series.some((v) => v > 0)) {
        container.innerHTML = '<div class="empty-chart">Sem execuções registradas para compor o gráfico.</div>';
        if (charts.status) {
            charts.status.destroy();
            charts.status = null;
        }
        return;
    }

    const options = {
        chart: { type: 'donut', height: 280 },
        labels,
        series,
        colors: ['#32b178', '#e05252', '#2f6fed', '#8b98aa', '#d99a2b'],
        theme: { mode: 'dark' },
        tooltip: { theme: 'dark' },
        legend: { position: 'bottom', labels: { colors: '#aab7c7' } },
        dataLabels: { enabled: true },
        stroke: { width: 1, colors: ['#121a26'] },
    };

    if (charts.status) charts.status.destroy();
    charts.status = new ApexCharts(container, options);
    charts.status.render();
}

async function populateControlTable(overview) {
    const tbody = document.getElementById('control-tbody');
    if (!tbody) return;

    const autos = overview.automations || [];
    const recent = overview.recent || [];
    const latestByAutomation = new Map();

    recent.forEach((item) => {
        if (!latestByAutomation.has(item.automation_id)) {
            latestByAutomation.set(item.automation_id, item);
        }
    });

    if (!autos.length) {
        tbody.innerHTML = '<tr><td colspan="5">Nenhuma automação cadastrada.</td></tr>';
        return;
    }

    tbody.innerHTML = autos.map((auto) => {
        const last = latestByAutomation.get(auto.id);
        const lastExecLabel = last ? formatDate(last.started_at) : '-';
        const lastStatus = last ? `<span class="badge ${getBadgeClass(last.status)}">${translateStatus(last.status)}</span>` : '<span class="badge badge-muted">Sem histórico</span>';
        const nextRun = auto.next_run || '-';
        const openLogAction = last ? `openLogModal('${last.id}')` : `showToast('Sem execução para exibir logs.', 'warning')`;

        return `
            <tr>
                <td><strong>${escapeHtml(auto.name)}</strong></td>
                <td>${lastStatus}</td>
                <td>${lastExecLabel}</td>
                <td>${nextRun}</td>
                <td>
                    <div class="inline-actions">
                        <button class="btn-icon" onclick="runAuto(${auto.id})" title="Executar agora"><i data-lucide="play"></i></button>
                        <button class="btn-icon" onclick="${openLogAction}" title="Abrir logs"><i data-lucide="terminal"></i></button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function loadExecutions(page = execPage) {
    execPage = page;

    const params = new URLSearchParams({
        page: String(execPage),
        per_page: String(EXEC_PER_PAGE),
    });

    const status = getValue('filter-status');
    const automationId = getValue('filter-automation');
    const requestedBy = getValue('filter-requested-by');
    const dateFrom = getValue('filter-date-from');
    const dateTo = getValue('filter-date-to');

    if (status) params.set('status', status);
    if (automationId) params.set('automation_id', automationId);
    if (requestedBy) params.set('requested_by', requestedBy);
    if (dateFrom) params.set('date_from', `${dateFrom}T00:00:00`);
    if (dateTo) params.set('date_to', `${dateTo}T23:59:59`);

    const data = await api(`/api/executions?${params.toString()}`);
    if (!data) return;

    renderExecutionsTable(data.items || []);
    ui.renderPagination(data.total || 0, data.page || 1, data.pages || 1, 'exec-pagination', (nextPage) => {
        loadExecutions(nextPage);
    });

    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function renderExecutionsTable(items) {
    const tbody = document.getElementById('exec-tbody');
    if (!tbody) return;

    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="7">Nenhuma execução encontrada para os filtros selecionados.</td></tr>';
        return;
    }

    tbody.innerHTML = items.map((ex) => `
        <tr onclick="openLogModal('${ex.id}')" style="cursor:pointer">
            <td><strong>${escapeHtml(ex.automation_name || '?')}</strong></td>
            <td style="font-family:monospace;font-size:0.75rem;opacity:0.85">${ex.id}</td>
            <td><span class="badge ${getBadgeClass(ex.status)}">${translateStatus(ex.status)}</span></td>
            <td><span class="badge badge-muted">${escapeHtml(ex.requested_by || '-')}</span></td>
            <td>${ex.duration_seconds ? Number(ex.duration_seconds).toFixed(1) + 's' : '-'}</td>
            <td>${formatDate(ex.started_at)}</td>
            <td>${['RUNNING', 'PENDING'].includes(ex.status) ? `<button class="btn btn-danger btn-sm" onclick="event.stopPropagation();stopExec('${ex.id}')"><i data-lucide="square"></i></button>` : '-'}</td>        </tr>
    `).join('');
}

async function loadConfig() {
    const [autos, jobs] = await Promise.all([
        api('/api/automations/all'),
        api('/api/system/scheduler/jobs'),
    ]);

    if (!autos) return;

    cachedAutomations = autos;
    cachedJobs = jobs || [];
    window.automations = autos;

    refreshAutomationFilterOptions(autos);
    renderAutomationTable(autos, jobs || []);
    syncGlobalTestToggle(autos);

    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function refreshAutomationFilterOptions(autos) {
    const select = document.getElementById('filter-automation');
    if (!select) return;

    const currentValue = select.value;
    const options = ['<option value="">TODOS OS ROBÔS</option>'];
    autos.forEach((auto) => {
        options.push(`<option value="${auto.id}">${escapeHtml(auto.name)}</option>`);
    });
    select.innerHTML = options.join('');
    select.value = currentValue || '';
}

function renderAutomationTable(autos, jobs) {
    const tbody = document.getElementById('fleet-tbody');
    if (!tbody) return;

    if (!autos.length) {
        tbody.innerHTML = '<tr><td colspan="7">Nenhuma automação cadastrada.</td></tr>';
        return;
    }

    const nextRunByAuto = new Map();
    jobs.forEach((job) => {
        if (!job.automation_id || !job.next_run_time) return;
        const current = nextRunByAuto.get(job.automation_id);
        if (!current || new Date(job.next_run_time) < new Date(current)) {
            nextRunByAuto.set(job.automation_id, job.next_run_time);
        }
    });

    tbody.innerHTML = autos.map((auto) => {
        const scheduleLabel = describeSchedule(auto.schedule);
        const nextRun = auto.next_run || formatDate(nextRunByAuto.get(auto.id)) || '-';
        const escapedName = escapeHtml(auto.name);
        const autoNameJs = String(auto.name || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");

        return `
            <tr>
                <td>
                    <div class="auto-info">
                        <span class="auto-name">${escapedName}</span>
                        <span class="auto-path">${escapeHtml(auto.script_path || '')}</span>
                    </div>
                </td>
                <td><span class="badge badge-muted">${scheduleLabel}</span></td>
                <td>${nextRun}</td>
                <td>${auto.test_mode ? '<span class="badge badge-warning">TESTE</span>' : '<span class="badge badge-blue">PROD</span>'}</td>
                <td>${auto.enabled ? '<span class="badge badge-success">ATIVO</span>' : '<span class="badge badge-danger">PAUSADA</span>'}</td>
                <td><span class="badge ${getBadgeClass(auto.last_status)}">${translateStatus(auto.last_status)}</span></td>
                <td>
                    <div class="inline-actions">
                        <button class="btn-icon" onclick="runAuto(${auto.id})" title="Executar"><i data-lucide="play" size="14"></i></button>
                        <button class="btn-icon" onclick="openEditAuto(${auto.id})" title="Editar cadastro"><i data-lucide="pencil" size="14"></i></button>
                        <button class="btn-icon" onclick="openJsonModal(${auto.id}, '${autoNameJs}')" title="Editar JSON"><i data-lucide="file-json" size="14"></i></button>
                        <button class="btn-icon" onclick="openIdeModal(${auto.id}, '${autoNameJs}')" title="Editar scripts"><i data-lucide="code" size="14"></i></button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function loadSystem() {
    const [health, diagnostics, audit] = await Promise.all([
        api('/api/system/health'),
        api('/api/system/diagnostics'),
        api('/api/system/audit?limit=25'),
    ]);

    if (health) renderHealthCards(health);
    if (diagnostics) {
        renderWorkerDetails(diagnostics);
        renderDiagnosticFindings(diagnostics);
    }
    if (audit) renderAuditTable(audit);

    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function renderHealthCards(health) {
    setHealthCard('health-db', health.database === 'online', health.database);
    setHealthCard('health-sched', health.scheduler === 'executando', health.scheduler);
    setHealthCard('health-worker', health.worker?.is_alive, health.worker?.is_alive ? 'Ativo' : 'Inativo');
    setHealthCard('health-disk', true, `${Number(health.disk_usage_mb || 0).toFixed(1)} MB`);
}

function setHealthCard(id, ok, text) {
    const card = document.getElementById(id);
    if (!card) return;

    card.classList.remove('ok', 'warn');
    card.classList.add(ok ? 'ok' : 'warn');

    const value = card.querySelector('.health-value');
    if (value) value.textContent = text || '-';
}

function renderWorkerDetails(diagnostics) {
    const details = document.getElementById('worker-details');
    if (!details) return;

    const worker = diagnostics.worker || {};
    const queue = diagnostics.queue || {};
    const heartbeat = diagnostics.heartbeat || {};

    details.innerHTML = `
        <div class="info-row"><span>Status:</span><b>${worker.is_alive ? 'ONLINE' : 'OFFLINE'}</b></div>
        <div class="info-row"><span>PID:</span><b>${worker.pid || '-'}</b></div>
        <div class="info-row"><span>Concluídas:</span><b>${worker.tasks_completed || 0}</b></div>
        <div class="info-row"><span>Falhas:</span><b>${worker.tasks_failed || 0}</b></div>
        <div class="info-row"><span>Ativas:</span><b>${worker.active_tasks || 0}</b></div>
        <div class="info-row"><span>Fila Ativa:</span><b>${queue.active_count || 0}</b></div>
        <div class="info-row"><span>Pendente mais antigo:</span><b>${formatQueueAge(queue.oldest_pending)}</b></div>
        <div class="info-row"><span>RUNNING mais antigo:</span><b>${formatQueueAge(queue.oldest_running)}</b></div>
        <div class="info-row"><span>Heartbeat:</span><b>${heartbeat.last_ping_age_seconds == null ? '-' : formatDuration(heartbeat.last_ping_age_seconds)}</b></div>
        <div class="info-row"><span>Versão:</span><b>${worker.version || '-'}</b></div>
    `;
}

function formatQueueAge(item) {
    if (!item || !item.exec_id) return '-';
    return `${escapeHtml(item.exec_id)} · ${formatDuration(item.age_seconds || 0)}`;
}

function renderDiagnosticFindings(diagnostics) {
    const container = document.getElementById('diagnostic-findings');
    if (!container) return;

    const findings = Array.isArray(diagnostics.findings) ? diagnostics.findings : [];
    if (!findings.length) {
        container.innerHTML = `
            <div class="finding-card info">
                <span class="badge badge-success">OK</span>
                <div>
                    <strong>Sem achados críticos</strong>
                    <p>Diagnóstico atual: ${escapeHtml(diagnostics.overall_status || 'healthy')}.</p>
                </div>
            </div>
        `;
        return;
    }

    const badgeClass = {
        ERROR: 'badge-danger',
        WARN: 'badge-warning',
        INFO: 'badge-blue',
    };

    container.innerHTML = findings.map((item) => {
        const severity = item.severity || 'INFO';
        return `
            <article class="finding-card ${severity.toLowerCase()}">
                <span class="badge ${badgeClass[severity] || 'badge-muted'}">${escapeHtml(severity)}</span>
                <div>
                    <strong>${escapeHtml(item.component || 'sistema')}</strong>
                    <p>${escapeHtml(item.message || '-')}</p>
                    <small>${escapeHtml(item.action_hint || 'Revisar diagnóstico operacional.')}</small>
                </div>
            </article>
        `;
    }).join('');
}

function renderAuditTable(items) {
    const tbody = document.getElementById('audit-tbody');
    if (!tbody) return;

    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="5">Sem eventos de auditoria.</td></tr>';
        return;
    }

    tbody.innerHTML = items.map((item) => `
        <tr>
            <td>${formatDate(item.timestamp)}</td>
            <td><span class="badge badge-muted">${escapeHtml(item.action || '-')}</span></td>
            <td>${escapeHtml(item.entity_type || '-')}</td>
            <td>${escapeHtml(item.entity_id || '-')}</td>
            <td>${escapeHtml(item.actor || '-')}</td>
        </tr>
    `).join('');
}

async function toggleGlobalTestMode(enabled) {
    const desired = Boolean(enabled);
    const res = await api(`/api/automations/test-mode/global?enabled=${desired}`, 'POST');
    if (res) {
        showToast(res.message || 'Modo de teste global atualizado.', 'success');
        await Promise.all([loadOverview(), loadConfig()]);
    } else {
        const input = document.getElementById('global-test-toggle');
        if (input) input.checked = !desired;
        showToast('Não foi possível atualizar o modo de teste global.', 'error');
    }
}

function syncGlobalTestToggle(autos) {
    const input = document.getElementById('global-test-toggle');
    const pill = document.getElementById('test-mode-pill');
    if (!input) return;

    const enabledCount = autos.filter((item) => item.test_mode).length;
    const globalOn = autos.length > 0 && enabledCount === autos.length;
    input.checked = globalOn;

    if (pill) {
        pill.style.display = enabledCount > 0 ? 'flex' : 'none';
        pill.title = `${enabledCount}/${autos.length || 0} automações em modo sandbox`;
    }
}

async function callSystemAction(action) {
    if (!action) return;

    const map = {
        resume_all: { path: '/api/automations/control/resume-all', method: 'POST', label: 'retomar todas as automações' },
        pause_all: { path: '/api/automations/control/pause-all', method: 'POST', label: 'pausar todas as automações' },
        backup: { path: '/api/system/backup', method: 'POST', label: 'executar backup do banco' },
    };

    let request = map[action];
    if (action === 'purge') {
        const retention = prompt('Informe retenção em dias para purge (mínimo 7):', '90');
        if (retention === null) return;
        const days = Number(retention);
        if (!Number.isFinite(days) || days < 7) {
            showToast('Valor inválido. Informe um número maior ou igual a 7.', 'warning');
            return;
        }
        request = {
            path: `/api/system/purge?retention_days=${Math.floor(days)}`,
            method: 'POST',
            label: `limpar execuções com retenção de ${Math.floor(days)} dia(s)`,
        };
    }

    if (!request) {
        showToast('Ação não reconhecida.', 'warning');
        return;
    }

    if (!confirm(`Confirmar ação: ${request.label}?`)) return;

    const res = await api(request.path, request.method);
    if (res) {
        showToast(res.message || 'Ação concluída com sucesso.', 'success');
        await Promise.all([loadOverview(), loadExecutions(execPage), loadSystem()]);
    }
}

function handleSearch() {
    const query = (getValue('auto-search') || '').toLowerCase().trim();
    if (!query) {
        renderAutomationTable(cachedAutomations, cachedJobs);
        if (typeof lucide !== 'undefined') lucide.createIcons();
        return;
    }

    const filtered = cachedAutomations.filter((auto) => {
        const name = (auto.name || '').toLowerCase();
        const path = (auto.script_path || '').toLowerCase();
        const desc = (auto.description || '').toLowerCase();
        return name.includes(query) || path.includes(query) || desc.includes(query);
    });

    renderAutomationTable(filtered, cachedJobs);
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

async function openAutomationModal(automationId = null) {
    const modal = document.getElementById('modal-auto');
    if (!modal) return;

    resetAutomationForm();

    if (automationId !== null) {
        const auto = await api(`/api/automations/${automationId}`);
        if (!auto) return;
        fillAutomationForm(auto);
        setText('modal-title', 'Editar Automação');
    } else {
        setText('modal-title', 'Nova Automação');
    }

    modal.showModal();
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function resetAutomationForm() {
    const form = document.getElementById('form-auto');
    if (form) form.reset();

    setValue('f-id', '');
    setValue('f-name', '');
    setValue('f-description', '');
    setValue('f-path', '');
    setValue('f-max-runtime', '30');
    setValue('f-notification-channels', '');

    const enabled = document.getElementById('f-enabled');
    const test = document.getElementById('f-test');
    if (enabled) enabled.checked = true;
    if (test) test.checked = false;

    resetScheduleBuilder();
}

function fillAutomationForm(auto) {
    setValue('f-id', auto.id);
    setValue('f-name', auto.name || '');
    setValue('f-description', auto.description || '');
    setValue('f-path', auto.script_path || '');
    setValue('f-max-runtime', String(auto.max_runtime_minutes || 30));
    setValue('f-notification-channels', auto.notification_channels || '');

    const enabled = document.getElementById('f-enabled');
    const test = document.getElementById('f-test');
    if (enabled) enabled.checked = Boolean(auto.enabled);
    if (test) test.checked = Boolean(auto.test_mode);

    parseScheduleToBuilder(auto.schedule);
}

function parseScheduleToBuilder(rawSchedule) {
    resetScheduleBuilder();
    if (!rawSchedule) return;

    try {
        const schedule = typeof rawSchedule === 'string' ? JSON.parse(rawSchedule.replace(/'/g, '"')) : rawSchedule;
        const days = Array.isArray(schedule.daysOfWeek) ? schedule.daysOfWeek : [];
        days.forEach((day) => {
            const d = Number(day);
            if (Number.isInteger(d) && d >= 0 && d <= 6) scheduleDays.add(d);
        });

        if (Array.isArray(schedule.times)) {
            schedule.times.forEach((t) => {
                const hh = String(Number(t.h || 0)).padStart(2, '0');
                const mm = String(Number(t.m || 0)).padStart(2, '0');
                scheduleTimes.push(`${hh}:${mm}`);
            });
        } else {
            const hours = Array.isArray(schedule.hours) ? schedule.hours : [];
            const minutes = Array.isArray(schedule.minutes) ? schedule.minutes : [0];
            hours.forEach((h) => {
                minutes.forEach((m) => {
                    const hh = String(Number(h || 0)).padStart(2, '0');
                    const mm = String(Number(m || 0)).padStart(2, '0');
                    scheduleTimes.push(`${hh}:${mm}`);
                });
            });
        }

        scheduleTimes = Array.from(new Set(scheduleTimes)).sort();
        refreshScheduleUi();
    } catch (_err) {
        showToast('Agenda existente inválida. Ajuste os horários manualmente.', 'warning');
    }
}

function addScheduleTimeFromInput() {
    const input = document.getElementById('f-time-input');
    if (!input || !input.value) {
        showToast('Selecione um horário para adicionar.', 'warning');
        return;
    }

    const hhmm = input.value;
    if (scheduleTimes.includes(hhmm)) {
        showToast('Horário já adicionado.', 'warning');
        return;
    }

    scheduleTimes.push(hhmm);
    scheduleTimes.sort();
    input.value = '';
    refreshScheduleUi();
}

function removeScheduleTime(hhmm) {
    scheduleTimes = scheduleTimes.filter((item) => item !== hhmm);
    refreshScheduleUi();
}

function refreshScheduleUi() {
    renderScheduleTimes();
    renderScheduleDays();
    renderScheduleSummary();
}

function renderScheduleTimes() {
    const list = document.getElementById('f-time-list');
    if (!list) return;

    if (!scheduleTimes.length) {
        list.innerHTML = '<span class="time-placeholder">Nenhum horário selecionado.</span>';
        return;
    }

    list.innerHTML = scheduleTimes.map((hhmm) => `
        <span class="time-tag">
            ${hhmm}
            <span class="remove-time" onclick="removeScheduleTime('${hhmm}')">✕</span>
        </span>
    `).join('');
}

function renderScheduleDays() {
    document.querySelectorAll('.day-btn').forEach((btn) => {
        const day = Number(btn.dataset.day);
        btn.classList.toggle('active', scheduleDays.has(day));
    });
}

function renderScheduleSummary() {
    const summary = document.getElementById('schedule-summary');
    if (!summary) return;

    if (!scheduleTimes.length || !scheduleDays.size) {
        summary.innerHTML = '<i data-lucide="info" size="14"></i><span>Selecione ao menos um dia e um horário.</span>';
        if (typeof lucide !== 'undefined') lucide.createIcons();
        return;
    }

    const dayNames = {
        0: 'Dom', 1: 'Seg', 2: 'Ter', 3: 'Qua', 4: 'Qui', 5: 'Sex', 6: 'Sáb',
    };
    const days = Array.from(scheduleDays).sort((a, b) => a - b).map((d) => dayNames[d]).join(', ');
    const times = scheduleTimes.join(', ');

    summary.innerHTML = `<i data-lucide="calendar-clock" size="14"></i><span>Agenda: ${days} às ${times}</span>`;
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function resetScheduleBuilder() {
    scheduleTimes = [];
    scheduleDays = new Set();
    refreshScheduleUi();
}

function buildSchedulePayload() {
    if (!scheduleTimes.length || !scheduleDays.size) return null;

    const times = scheduleTimes.map((item) => {
        const [h, m] = item.split(':');
        return { h: Number(h), m: Number(m) };
    });

    return JSON.stringify({
        daysOfWeek: Array.from(scheduleDays).sort((a, b) => a - b),
        times,
    });
}

async function saveAutomation(event) {
    if (event) event.preventDefault();
    if (isSavingAutomation) return;

    const automationId = getValue('f-id');
    const name = getValue('f-name');
    const scriptPath = getValue('f-path');

    if (!name || !scriptPath) {
        showToast('Nome e caminho do script são obrigatórios.', 'warning');
        return;
    }

    const payload = {
        name,
        description: getValue('f-description') || null,
        script_path: scriptPath,
        schedule: buildSchedulePayload(),
        max_runtime_minutes: Number(getValue('f-max-runtime') || 30),
        enabled: Boolean(document.getElementById('f-enabled')?.checked),
        test_mode: Boolean(document.getElementById('f-test')?.checked),
        notification_channels: getValue('f-notification-channels') || null,
    };

    const submitBtn = document.querySelector('#form-auto button[type="submit"]');
    isSavingAutomation = true;
    if (submitBtn) submitBtn.disabled = true;

    try {
        let response = null;
        if (automationId) {
            response = await api(`/api/automations/${automationId}`, 'PUT', payload, { silentErrorToast: true });
        } else {
            response = await api('/api/automations', 'POST', payload, { silentErrorToast: true });
        }

        if (!response) {
            showToast('Falha ao salvar automação. Verifique os dados informados.', 'error');
            return;
        }

        showToast('Automação salva com sucesso.', 'success');
        document.getElementById('modal-auto')?.close();
        await Promise.all([loadConfig(), loadOverview(), loadExecutions(1)]);
    } finally {
        isSavingAutomation = false;
        if (submitBtn) submitBtn.disabled = false;
    }
}

function describeSchedule(rawSchedule) {
    if (!rawSchedule) return 'MANUAL';
    try {
        const parsed = typeof rawSchedule === 'string' ? JSON.parse(rawSchedule.replace(/'/g, '"')) : rawSchedule;
        const times = Array.isArray(parsed.times) ? parsed.times : [];
        if (!times.length) return 'CONFIGURADA';
        const count = times.length;
        return `${count} horário(s)`;
    } catch (_err) {
        return 'CONFIGURADA';
    }
}

function formatSeconds(value) {
    const sec = Number(value || 0);
    if (!Number.isFinite(sec) || sec <= 0) return '0s';
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const minutes = Math.floor(sec / 60);
    const remain = Math.round(sec % 60);
    return `${minutes}m ${remain}s`;
}

function isRenderable(element) {
    return Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

function getValue(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
}

window.loadExecutions = () => loadExecutions(1);
