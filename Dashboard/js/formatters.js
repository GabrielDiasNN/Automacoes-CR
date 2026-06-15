/**
 * formatters.js — Utilitários de formatação numérica e de datas (pt-BR).
 * Consumido por dashboard_beneficiamento.js e outros módulos que precisem
 * de formatação locale-aware sem depender do contexto central.
 */

const _fmtInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const _fmt1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function numberValue(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

export function formatNumber(value, digits = 0) {
    const parsed = numberValue(value);
    return digits === 1 ? _fmt1.format(parsed) : _fmtInt.format(parsed);
}

export function formatPercent(value) {
    return `${formatNumber(value, 1)}%`;
}

export function formatDateBr(value) {
    if (!value) return "-";
    const raw = String(value).slice(0, 10);
    const parts = raw.split("-");
    return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : String(value);
}

export function formatDateTimeBr(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return formatDateBr(value);
    return date.toLocaleString("pt-BR", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
    });
}

export function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

export function formatSeconds(value) {
    const sec = Number(value || 0);
    if (!Number.isFinite(sec) || sec <= 0) return "0s";
    return `${sec.toFixed(1)}s`;
}

export function formatAge(seconds) {
    const s = numberValue(seconds);
    if (!s) return "agora";
    if (s < 60) return `${formatNumber(s, 0)}s`;
    if (s < 3600) return `${formatNumber(s / 60, 0)} min`;
    if (s < 86400) return `${formatNumber(s / 3600, 1)} h`;
    return `${formatNumber(s / 86400, 1)} d`;
}
