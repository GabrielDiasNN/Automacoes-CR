/**
 * dashboard_charts.js — Gráficos ApexCharts compartilhados pelas views de
 * painel operacional e observabilidade. Detém o estado das instâncias para
 * permitir atualização incremental sem recriar os gráficos.
 */

import { isRenderable } from "./dom_utils.js";

export function createChartsModule() {
    const charts = { performance: null, status: null };

    function renderOverviewCharts(overview) {
        renderPerformanceChart(overview);
        renderStatusChart(overview);
    }

    function renderPerformanceChart(overview) {
        const container = document.getElementById("chart-performance");
        if (!container || typeof ApexCharts === "undefined" || !isRenderable(container)) return;

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
        Array.from(byAutomation.entries()).slice(0, 8).forEach(([name, durations]) => {
            const avg = durations.reduce((acc, d) => acc + d, 0) / durations.length;
            labels.push(name);
            values.push(Number(avg.toFixed(2)));
        });

        if (!labels.length) {
            container.innerHTML = "<div class=\"empty-chart\">Sem dados de performance no período recente.</div>";
            if (charts.performance) {
                charts.performance.destroy();
                charts.performance = null;
            }
            return;
        }

        const options = {
            chart: { type: "bar", height: 280, toolbar: { show: false } },
            series: [{ name: "Tempo médio (s)", data: values }],
            xaxis: { categories: labels },
            colors: ["#2f6fed"],
            dataLabels: { enabled: false },
            theme: { mode: "dark" },
            tooltip: { theme: "dark" },
            legend: { labels: { colors: "#aab7c7" } },
            yaxis: { labels: { formatter: (v) => `${Number(v).toFixed(1)}s` } },
            grid: { borderColor: "#263345" },
        };

        if (charts.performance) {
            charts.performance.updateOptions({
                series: options.series,
                xaxis: options.xaxis,
            }, false, true);
            return;
        }
        charts.performance = new ApexCharts(container, options);
        charts.performance.render();
    }

    function renderStatusChart(overview) {
        const container = document.getElementById("chart-status");
        if (!container || typeof ApexCharts === "undefined" || !isRenderable(container)) return;

        const breakdown = overview.status_breakdown || {};
        const labels = ["Sucesso", "Erro", "Executando", "Pendente", "Interrompido"];
        const series = [
            Number(breakdown.SUCCESS || 0),
            Number(breakdown.ERROR || 0),
            Number(breakdown.RUNNING || 0),
            Number(breakdown.PENDING || 0),
            Number(breakdown.TERMINATED || 0),
        ];

        if (!series.some((v) => v > 0)) {
            container.innerHTML = "<div class=\"empty-chart\">Sem execuções registradas para compor o gráfico.</div>";
            if (charts.status) {
                charts.status.destroy();
                charts.status = null;
            }
            return;
        }

        const options = {
            chart: { type: "donut", height: 280 },
            labels,
            series,
            colors: ["#32b178", "#e05252", "#2f6fed", "#8b98aa", "#d99a2b"],
            theme: { mode: "dark" },
            tooltip: { theme: "dark" },
            legend: { position: "bottom", labels: { colors: "#aab7c7" } },
            dataLabels: { enabled: true },
            stroke: { width: 1, colors: ["#121a26"] },
        };

        if (charts.status) {
            charts.status.updateSeries(options.series, true);
            return;
        }
        charts.status = new ApexCharts(container, options);
        charts.status.render();
    }

    return { renderOverviewCharts };
}
