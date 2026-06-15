/**
 * Módulo V1 de Beneficiamento.
 * Consome apenas contratos GET baseados no SQLite local do Orchestrator.
 */

import { numberValue, formatNumber, formatPercent, formatDateBr, formatDateTimeBr, formatAge } from "./formatters.js";
import { renderTable } from "./ui_manager.js";
import { setText, refreshIcons } from "./dom_utils.js";

export function createBeneficiamentoModule(ctx) {
    const { api, showToast, escapeHtml, bindActionElements, normalizeBeneficiamentoPayload } = ctx;

    const charts = { overview: null };
    const state = {
        initialized: false,
        dashboard: null,
        overview: null,
        detail: null,
        detailRawLoaded: false,
        detailContext: null,
        loadToken: 0,
        reloadTimer: null,
        selectedPeriodKey: "mensal",
    };

    function translateHealthStatus(value) {
        switch (String(value || "").toLowerCase()) {
            case "healthy": return "Saudável";
            case "attention": return "Atenção";
            case "missing": return "Indisponível";
            case "no_data": return "Sem dados";
            case "blocked": return "Bloqueado";
            default: return value || "-";
        }
    }

    function setHtml(id, value) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = value;
    }

    function setBannerState(kind, message) {
        const banner = document.getElementById("benef-banner");
        if (!banner) return;
        banner.className = `state-banner ${kind}`;
        banner.textContent = message;
        banner.style.display = "block";
    }

    function activePeriodPayload() {
        const dashboard = state.dashboard || {};
        const periods = dashboard.periods || {};
        return periods[state.selectedPeriodKey] || periods[dashboard.default_period] || {};
    }

    function currentFilters() {
        return {
            dt_inicio: document.getElementById("benef-filter-dt-inicio")?.value || "",
            dt_fim: document.getElementById("benef-filter-dt-fim")?.value || "",
            q: document.getElementById("benef-filter-search")?.value?.trim() || "",
            alternativo: document.getElementById("benef-filter-alt")?.value?.trim() || "",
            maquina: document.getElementById("benef-filter-machine")?.value || "",
            fase: document.getElementById("benef-filter-phase")?.value || "",
            turno: document.getElementById("benef-filter-turn")?.value || "",
        };
    }

    function buildQuery(filters) {
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value !== "" && value !== undefined && value !== null) params.append(key, value);
        });
        return params.toString();
    }

    function optionHtml(value) {
        return `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`;
    }

    function populateSelect(id, label, values) {
        const select = document.getElementById(id);
        if (!select) return;
        const current = select.value;
        select.innerHTML = `<option value="">${label}</option>${(values || []).map(optionHtml).join("")}`;
        select.value = values?.includes(current) ? current : "";
    }

    function destroyChart(key) {
        if (!charts[key]) return;
        try {
            charts[key].destroy();
        } catch (_error) {
            // ignore
        }
        charts[key] = null;
    }

    async function loadBeneficiamento() {
        const loadToken = ++state.loadToken;
        try {
            setBannerState("info", "Carregando base histórica, períodos e análise do Beneficiamento...");
            const query = buildQuery(currentFilters());
            const [dashboardPayload, overviewPayload] = await Promise.all([
                api("/api/beneficiamento/dashboard"),
                api(`/api/beneficiamento/overview${query ? `?${query}` : ""}`),
            ]);
            if (loadToken !== state.loadToken) return;
            state.dashboard = normalizeBeneficiamentoPayload(dashboardPayload || {});
            state.selectedPeriodKey = state.dashboard?.periods?.[state.selectedPeriodKey]
                ? state.selectedPeriodKey
                : (state.dashboard?.default_period || "mensal");
            state.overview = overviewPayload;
            renderProgressive(state.dashboard, overviewPayload);
            applyBannerFromState();
        } catch (error) {
            if (loadToken !== state.loadToken) return;
            console.error("Erro ao carregar dashboard de Beneficiamento:", error);
            renderUnavailable();
            if (showToast) showToast("Erro ao carregar Beneficiamento.", "danger");
        }
    }

    function syncEffectiveDates(payload) {
        const effective = payload?.filters?.effective || {};
        const dtInicio = document.getElementById("benef-filter-dt-inicio");
        const dtFim = document.getElementById("benef-filter-dt-fim");
        if (dtInicio && !dtInicio.value && effective.dt_inicio) dtInicio.value = effective.dt_inicio;
        if (dtFim && !dtFim.value && effective.dt_fim) dtFim.value = effective.dt_fim;
    }

    function renderPeriodGrid(dashboard) {
        const container = document.getElementById("benef-period-grid");
        if (!container) return;
        const periods = dashboard?.periods || {};
        container.innerHTML = ["diario", "semanal", "mensal", "anual"].map((key) => {
            const period = periods[key] || {};
            const metrics = period.metrics || {};
            const badgeClass = period.status === "healthy"
                ? "badge-success"
                : (period.status === "attention" ? "badge-warning" : "badge-muted");
            const activeClass = key === state.selectedPeriodKey ? " active" : "";
            return `
                <button class="benef-period-card${activeClass}" type="button" data-benef-period="${escapeHtml(key)}">
                    <div class="benef-period-head">
                        <span class="eyebrow">${escapeHtml(period.label || key)}</span>
                        <span class="badge ${badgeClass}">${escapeHtml(translateHealthStatus(period.status || "missing"))}</span>
                    </div>
                    <strong>${formatNumber(metrics.kg_total, 0)} kg</strong>
                    <small>${period.updated_at ? `Atualizado ${formatDateTimeBr(period.updated_at)} · ${formatAge(period.age_seconds)}` : "Snapshot indisponível"}</small>
                </button>
            `;
        }).join("");
    }

    function firstHealthIssue(periodOrHealth) {
        const issues = Array.isArray(periodOrHealth?.issues) ? periodOrHealth.issues : [];
        return issues[0] || null;
    }

    function renderStatus(dashboard, payload) {
        const effective = payload?.filters?.effective || {};
        const health = payload?.health || {};
        const activePeriod = activePeriodPayload();
        const healthRoot = dashboard?.health || {};
        setText(
            "benef-selected-meta",
            `Janela efetiva ${formatDateBr(effective.dt_inicio)} a ${formatDateBr(effective.dt_fim)} · ${activePeriod.label || "Período"} em foco · base local observável`
        );
        setText("benef-health-status", translateHealthStatus(healthRoot.status || activePeriod.status || "-"));
        setText("benef-default-period", activePeriod.label || dashboard?.default_period || "-");
        setText("benef-health-updated", formatDateTimeBr(activePeriod.updated_at));
        setText("benef-health-age", formatAge(activePeriod.age_seconds));
        setText("benef-health-source", healthRoot.source === "snapshot_local" ? "Snapshots locais + SQLite histórico" : "SQLite + snapshots locais");
        setText("benef-max-data", formatDateBr(health.max_data_fim));
        setText("benef-records", formatNumber(health.records, 0));
    }

    function buildBannerDescriptor() {
        const dashboard = state.dashboard || {};
        const overview = state.overview || {};
        const activePeriod = activePeriodPayload();
        const health = dashboard.health || {};
        const primaryIssue = firstHealthIssue(activePeriod) || firstHealthIssue(health);
        if (overview?.health?.status === "no_data") {
            return {
                kind: "warning",
                message: "Base histórica local disponível, mas o recorte atual não encontrou produção.",
            };
        }
        if (health.status === "healthy" && activePeriod.updated_at) {
            return {
                kind: "success",
                message: `Base histórica local atualizada em ${formatDateTimeBr(activePeriod.updated_at)}, pronta para análise operacional.`,
            };
        }
        if (health.status === "attention") {
            return {
                kind: "warning",
                message: primaryIssue?.action_hint
                    ? `${primaryIssue.label || activePeriod.label || "Período"}: ${primaryIssue.message} Ação recomendada: ${primaryIssue.action_hint}`
                    : `${primaryIssue?.label || activePeriod.label || "Período"}: ${primaryIssue?.message || "Base disponível com atenção operacional."}`,
            };
        }
        if (health.status === "missing") {
            return {
                kind: "danger",
                message: health.recommended_action
                    ? `Snapshots do Beneficiamento indisponíveis para a leitura operacional. ${health.recommended_action}`
                    : "Snapshots do Beneficiamento indisponíveis para a leitura operacional.",
            };
        }
        if (health.status === "no_data") {
            return {
                kind: "info",
                message: primaryIssue?.message || "Snapshot promovido, mas sem linhas úteis para o período analisado.",
            };
        }
        return {
            kind: "info",
            message: "Leitura local do Beneficiamento carregada. Verifique o estado dos períodos para validar confiança do dado.",
        };
    }

    function applyBannerFromState() {
        const descriptor = buildBannerDescriptor();
        setBannerState(descriptor.kind, descriptor.message);
    }

    function renderKpis(kpis) {
        setText("benef-kpi-obs", formatNumber(kpis?.ob_distintas, 0));
        setText("benef-kpi-fases", formatNumber(kpis?.fases_concluidas, 0));
        setText("benef-kpi-kg", formatNumber(kpis?.kg_total, 0));
        setText("benef-kpi-mt", formatNumber(kpis?.mt_total, 0));
        setText("benef-kpi-eficiencia", formatPercent(kpis?.eficiencia_tempo_pct));
        setText("benef-kpi-reprocesso", formatPercent(kpis?.reprocesso_kg_pct));
        setText("benef-kpi-desvio", `${formatNumber(kpis?.desvio_tempo_min, 0)} min`);
        setText("benef-kpi-produtividade", `${formatNumber(kpis?.produtividade_kg_h, 1)} kg/h`);
    }

    function renderFilterOptions(options) {
        populateSelect("benef-filter-machine", "Todas", options?.maquinas || []);
        populateSelect("benef-filter-phase", "Todas", options?.fases || []);
        populateSelect("benef-filter-turn", "Todos", options?.turnos || []);
    }

    function renderOverviewChart(series) {
        const container = document.getElementById("benef-overview-chart");
        if (!container) return;
        const volume = series?.volume_diario || [];
        const eficiencia = series?.eficiencia_diaria || [];
        if (!volume.length || typeof ApexCharts === "undefined") {
            destroyChart("overview");
            container.innerHTML = '<div class="empty-chart">Sem série diária para o recorte.</div>';
            return;
        }

        const categories = volume.map((item) => formatDateBr(item.date));
        const eficienciaByDate = new Map(eficiencia.map((item) => [item.date, numberValue(item.eficiencia_tempo_pct)]));
        destroyChart("overview");
        charts.overview = new ApexCharts(container, {
            chart: { type: "line", height: 300, toolbar: { show: false }, animations: { enabled: false } },
            series: [
                { name: "KG", type: "column", data: volume.map((item) => numberValue(item.kg_total)) },
                { name: "Eficiência de tempo", type: "line", data: volume.map((item) => eficienciaByDate.get(item.date) || 0) },
            ],
            stroke: { width: [0, 3] },
            colors: ["#2f6fed", "#32b178"],
            dataLabels: { enabled: false },
            xaxis: { categories, labels: { rotate: -35 } },
            yaxis: [
                { labels: { formatter: (value) => `${formatNumber(value, 0)} kg` } },
                { opposite: true, labels: { formatter: (value) => `${formatNumber(value, 0)}%` }, max: 140 },
            ],
            tooltip: { theme: "dark" },
            grid: { borderColor: "rgba(148,163,184,0.10)" },
            legend: { labels: { colors: "#aab7c7" } },
        });
        charts.overview.render();
    }

    function rowAttrs(targetType, extra = {}) {
        const pairs = Object.entries(extra).map(([key, value]) => `data-${key}="${escapeHtml(String(value ?? ""))}"`);
        return `class="table-row-button" data-detail-target="${escapeHtml(targetType)}" ${pairs.join(" ")}`;
    }

    function renderTurnos(items) {
        renderTable(document.getElementById("benef-turn-tbody"), items, (item) => `
            <tr ${rowAttrs("turno", { turno: item.turno_label })}>
                <td>${escapeHtml(item.turno_label || "Indefinido")}</td>
                <td>${formatNumber(item.kg_total, 0)} kg</td>
                <td>${formatNumber(item.ob_distintas, 0)}</td>
                <td>${formatPercent(item.eficiencia_tempo_pct)}</td>
                <td>${formatPercent(item.reprocesso_kg_pct)}</td>
                <td>${formatNumber(item.produtividade_kg_h, 1)}</td>
            </tr>
        `, "Sem turnos no recorte.", 6);
    }

    function renderBottlenecks(items) {
        renderTable(document.getElementById("benef-bottleneck-tbody"), items, (item) => `
            <tr ${rowAttrs("maquina_fase", { maquina: item.maquina, fase: item.fase })}>
                <td>${escapeHtml(item.maquina || "-")}</td>
                <td>${escapeHtml(item.fase || "-")}</td>
                <td>${formatNumber(item.kg_total, 0)} kg</td>
                <td>${formatNumber(item.desvio_min, 0)} min</td>
                <td><span class="badge ${numberValue(item.eficiencia_tempo_pct) >= 80 ? "badge-success" : "badge-warning"}">${formatPercent(item.eficiencia_tempo_pct)}</span></td>
            </tr>
        `, "Sem gargalos no recorte.", 5);
    }

    function renderProducts(items) {
        renderTable(document.getElementById("benef-product-tbody"), items, (item) => `
            <tr ${rowAttrs("produto", { alternativo: item.codigo })}>
                <td>${escapeHtml(item.codigo || "-")}</td>
                <td>${escapeHtml(item.produto || "-")}</td>
                <td>${escapeHtml(item.artigo || "-")}</td>
                <td>${escapeHtml(item.cor || "-")}</td>
                <td>${formatNumber(item.kg_total, 0)} kg</td>
                <td>${formatPercent(item.reprocesso_kg_pct)}</td>
                <td>${formatNumber(item.produtividade_kg_h, 1)}</td>
            </tr>
        `, "Sem produtos no recorte.", 7);
    }

    function renderPhases(items) {
        renderTable(document.getElementById("benef-phase-tbody"), items, (item) => `
            <tr ${rowAttrs("fase", { fase: item.fase })}>
                <td>${escapeHtml(item.fase || "-")}</td>
                <td>${formatNumber(item.kg_total, 0)} kg</td>
                <td>${formatPercent(item.eficiencia_tempo_pct)}</td>
                <td>${formatPercent(item.reprocesso_kg_pct)}</td>
            </tr>
        `, "Sem fases no recorte.", 4);
    }

    function renderTingimento(tingimento) {
        const summary = tingimento?.summary || {};
        setText("benef-ting-kg-medio", `${formatNumber(summary.kg_medio_fase, 1)} kg`);
        setText("benef-ting-min-real", `${formatNumber(summary.min_real_medio, 1)} min`);
        setText("benef-ting-eficiencia", formatPercent(summary.eficiencia_media_pct));
        setText("benef-ting-reprocesso", formatPercent(summary.reprocesso_kg_pct));
        const items = tingimento?.rankings?.por_alternativo || [];
        renderTable(document.getElementById("benef-ting-product-tbody"), items, (item) => `
            <tr ${rowAttrs("produto", { alternativo: item.alternativo, fase: "03 - TINGIMENTO" })}>
                <td>${escapeHtml(item.alternativo || "-")}</td>
                <td>${escapeHtml(item.produto || "-")}</td>
                <td>${formatNumber(item.kg_total, 0)} kg</td>
                <td>${formatNumber(item.ob_distintas, 0)}</td>
                <td>${formatPercent(item.eficiencia_media_pct)}</td>
                <td>${formatPercent(item.reprocesso_kg_pct)}</td>
            </tr>
        `, "Sem registros de Tingimento no recorte.", 6);
    }

    async function pesquisarHistorico() {
        const ob = document.getElementById("benef-hist-ob")?.value?.trim() || "";
        const alternativo = document.getElementById("benef-hist-alt")?.value?.trim() || "";
        if (!ob && !alternativo) {
            if (showToast) showToast("Informe uma OB ou produto para rastrear.", "warning");
            return;
        }
        const params = new URLSearchParams({ limit: "30" });
        if (ob) params.append("ob", ob);
        if (alternativo) params.append("alternativo", alternativo);
        try {
            const payload = await api(`/api/beneficiamento/historico?${params.toString()}`);
            renderHistorico(payload?.records || []);
        } catch (error) {
            console.error("Erro ao pesquisar histórico de Beneficiamento:", error);
            if (showToast) showToast("Erro ao pesquisar histórico de Beneficiamento.", "danger");
        }
    }

    function renderHistorico(records) {
        renderTable(document.getElementById("benef-hist-tbody"), records, (item) => `
            <tr ${rowAttrs("ob", { ob: item.NUMERO_OB })}>
                <td>${escapeHtml(item.NUMERO_OB || "-")}</td>
                <td>${escapeHtml(item.SEQ ?? "-")}</td>
                <td>${formatDateBr(item.DATA_FIM || item.DATA_HORA_FIM)}</td>
                <td>${escapeHtml(item.CD_DS_FASE || "-")}</td>
                <td>${escapeHtml((item.NOME_MAQUINA || "").trim() || "-")}</td>
                <td>${escapeHtml(item.TURNO_DESC || "Indefinido")}</td>
                <td>${escapeHtml(item.DESCR_ITEM || item.CODIGO_ALTERNATIVO || item.REDUZ || "-")}</td>
                <td>${formatNumber(item.QT_KG, 0)}</td>
                <td>${formatNumber(item.MIN_REAL, 0)}</td>
            </tr>
        `, "Nenhum registro encontrado.", 9);
    }

    function switchDetailTab(tab) {
        document.querySelectorAll("[data-benef-tab]").forEach((button) => {
            button.classList.toggle("active", button.dataset.benefTab === tab);
        });
        document.querySelectorAll(".benef-detail-tab").forEach((panel) => {
            panel.classList.toggle("active", panel.id === `benef-detail-tab-${tab}`);
        });
        if (tab === "raw" && state.detailContext && !state.detailRawLoaded) {
            loadDetail(state.detailContext, true);
        }
    }

    async function loadDetail(context, includeRaw = false) {
        const params = new URLSearchParams({ ...currentFilters(), ...context, page: String(context.page || 1), limit: String(context.limit || 50) });
        if (includeRaw) params.set("include_raw", "true");
        try {
            const payload = await api(`/api/beneficiamento/detail?${params.toString()}`);
            state.detail = payload;
            state.detailRawLoaded = includeRaw || payload.raw_records?.length > 0;
            renderDetail();
            document.getElementById("modal-benef-detail")?.showModal();
        } catch (error) {
            console.error("Erro ao carregar detalhe de Beneficiamento:", error);
            if (showToast) showToast("Erro ao abrir detalhe do Beneficiamento.", "danger");
        }
    }

    function renderDetail() {
        const payload = state.detail || {};
        setText("benef-detail-title", payload?.target?.label || "Detalhe do Beneficiamento");
        const summary = payload.summary || {};
        const summaryItems = [
            ["OBs", formatNumber(summary.ob_distintas, 0)],
            ["Fases", formatNumber(summary.fases_concluidas, 0)],
            ["KG", `${formatNumber(summary.kg_total, 0)} kg`],
            ["MT", `${formatNumber(summary.mt_total, 0)} mt`],
            ["Eficiência", formatPercent(summary.eficiencia_tempo_pct)],
            ["Reprocesso", formatPercent(summary.reprocesso_kg_pct)],
            ["KG/h", formatNumber(summary.produtividade_kg_h, 1)],
            ["Turnos", escapeHtml((summary.turnos || []).join(", ") || "-")],
        ];
        setHtml("benef-detail-summary-grid", summaryItems.map(([label, value]) => `
            <div class="benef-mini-kpi">
                <span>${escapeHtml(label)}</span>
                <strong>${value}</strong>
            </div>
        `).join(""));

        setHtml("benef-detail-trace", (payload.trace || []).map((group) => `
            <article class="benef-trace-card">
                <h4>OB ${escapeHtml(group.ob || "-")}</h4>
                <p>${(group.fases || []).length} fase(s) no recorte</p>
                ${(group.fases || []).map((item) => `
                    <div class="benef-trace-line">
                        <strong>Seq ${escapeHtml(String(item.seq ?? "-"))}</strong>
                        <span>${escapeHtml(item.fase || "-")}</span>
                        <span>${escapeHtml(item.maquina || "-")}</span>
                        <span>${escapeHtml(item.turno || "Indefinido")}</span>
                        <span>${formatNumber(item.kg, 0)} kg</span>
                    </div>
                `).join("")}
            </article>
        `).join("") || "<div class=\"empty-state\">Sem rastreabilidade no recorte.</div>");

        setHtml("benef-detail-records-tbody", (payload.records || []).map((item) => `
            <tr>
                <td>${escapeHtml(item.ob || "-")}</td>
                <td>${escapeHtml(String(item.seq ?? "-"))}</td>
                <td>${formatDateBr(item.data_fim)}</td>
                <td>${escapeHtml(item.fase || "-")}</td>
                <td>${escapeHtml(item.maquina || "-")}</td>
                <td>${escapeHtml(item.turno || "Indefinido")}</td>
                <td>${escapeHtml(item.alternativo || item.reduz || "-")}</td>
                <td>${escapeHtml(item.produto || "-")}</td>
                <td>${formatNumber(item.kg, 0)}</td>
                <td>${formatNumber(item.min_real, 0)}</td>
            </tr>
        `).join("") || '<tr><td colspan="10">Sem registros no detalhe.</td></tr>');

        const raw = payload.raw_records?.length ? JSON.stringify(payload.raw_records, null, 2) : "Clique na aba Payload bruto para carregar o registro completo.";
        setText("benef-detail-raw", raw);

        const pagination = payload.pagination || {};
        setHtml("benef-detail-pagination", `
            <span>Página ${formatNumber(pagination.page || 1, 0)} de ${formatNumber(pagination.pages || 1, 0)} · ${formatNumber(pagination.total || 0, 0)} registro(s)</span>
        `);
    }

    function renderPrimary(dashboard, payload) {
        syncEffectiveDates(payload);
        renderPeriodGrid(dashboard);
        renderStatus(dashboard, payload);
        renderKpis(payload.kpis || {});
        renderFilterOptions(payload.filter_options || {});
    }

    function renderSecondary(payload) {
        renderOverviewChart(payload.series || {});
        renderTurnos(payload.turnos || []);
        renderBottlenecks(payload.rankings?.gargalos || []);
        renderProducts(payload.rankings?.produtos_principais || []);
        renderPhases(payload.rankings?.fases_criticas || []);
        renderTingimento(payload.tingimento || {});
        refreshIcons();
    }

    function renderProgressive(dashboard, payload) {
        const root = document.getElementById("view-beneficiamento");
        if (!root || !payload) return;
        setup(root);
        renderPrimary(dashboard, payload);
        window.requestAnimationFrame(() => {
            if (state.overview !== payload) return;
            renderSecondary(payload);
        });
    }

    function renderUnavailable() {
        destroyChart("overview");
        setBannerState("danger", "Falha ao carregar Beneficiamento pelo SQLite local.");
        ["benef-health-status", "benef-default-period", "benef-health-updated", "benef-health-age", "benef-health-source", "benef-max-data", "benef-records", "benef-kpi-obs", "benef-kpi-fases", "benef-kpi-kg", "benef-kpi-mt", "benef-kpi-eficiencia", "benef-kpi-reprocesso", "benef-kpi-desvio", "benef-kpi-produtividade", "benef-ting-kg-medio", "benef-ting-min-real", "benef-ting-eficiencia", "benef-ting-reprocesso"].forEach((id) => setText(id, "-"));
        setText("benef-selected-meta", "Base local indisponível no momento");
        setHtml("benef-period-grid", `
            <button class="benef-period-card active" type="button">
                <div class="benef-period-head">
                    <span class="eyebrow">Períodos</span>
                    <span class="badge badge-danger">Indisponível</span>
                </div>
                <strong>-</strong>
                <small>Não foi possível ler os snapshots locais.</small>
            </button>
        `);
        const chart = document.getElementById("benef-overview-chart");
        if (chart) chart.innerHTML = '<div class="empty-chart">Dados indisponíveis.</div>';
    }

    function clearFilters() {
        ["benef-filter-dt-inicio", "benef-filter-dt-fim", "benef-filter-search", "benef-filter-alt", "benef-filter-machine", "benef-filter-phase", "benef-filter-turn"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = "";
        });
        loadBeneficiamento();
    }

    function scheduleReload(delay = 180) {
        if (state.reloadTimer) window.clearTimeout(state.reloadTimer);
        state.reloadTimer = window.setTimeout(() => {
            state.reloadTimer = null;
            loadBeneficiamento();
        }, delay);
    }

    function setup(root) {
        if (state.initialized) return;
        state.initialized = true;
        const reload = () => scheduleReload();
        ["benef-filter-dt-inicio", "benef-filter-dt-fim", "benef-filter-machine", "benef-filter-phase", "benef-filter-turn"].forEach((id) => {
            document.getElementById(id)?.addEventListener("change", reload);
        });
        ["benef-filter-search", "benef-filter-alt"].forEach((id) => {
            document.getElementById(id)?.addEventListener("keydown", (event) => {
                if (event.key === "Enter") reload();
            });
        });
        document.getElementById("benef-filter-clear")?.addEventListener("click", clearFilters);
        document.getElementById("benef-hist-search-btn")?.addEventListener("click", pesquisarHistorico);
        document.getElementById("benef-hist-clear-btn")?.addEventListener("click", () => {
            ["benef-hist-ob", "benef-hist-alt"].forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.value = "";
            });
            renderHistorico([]);
        });
        root.addEventListener("click", (event) => {
            const periodCard = event.target.closest("[data-benef-period]");
            if (periodCard) {
                state.selectedPeriodKey = periodCard.dataset.benefPeriod || state.selectedPeriodKey;
                renderPrimary(state.dashboard || {}, state.overview || {});
                applyBannerFromState();
                return;
            }
            const row = event.target.closest("[data-detail-target]");
            if (!row) return;
            state.detailContext = {
                target_type: row.dataset.detailTarget,
                alternativo: row.dataset.alternativo || "",
                maquina: row.dataset.maquina || "",
                fase: row.dataset.fase || "",
                turno: row.dataset.turno || "",
                ob: row.dataset.ob || "",
                page: 1,
                limit: 50,
            };
            state.detailRawLoaded = false;
            switchDetailTab("summary");
            loadDetail(state.detailContext, false);
        });
        document.querySelectorAll("[data-benef-tab]").forEach((button) => {
            button.addEventListener("click", () => switchDetailTab(button.dataset.benefTab));
        });
        ["benef-hist-ob", "benef-hist-alt"].forEach((id) => {
            document.getElementById(id)?.addEventListener("keydown", (event) => {
                if (event.key === "Enter") pesquisarHistorico();
            });
        });
        bindActionElements(root);
    }

    return {
        loadBeneficiamento,
    };
}
