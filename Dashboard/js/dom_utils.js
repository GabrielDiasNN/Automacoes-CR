/**
 * dom_utils.js — Helpers de DOM compartilhados pelos módulos do dashboard.
 * Centraliza acessos por id e o disparo dos ícones Lucide, antes duplicados
 * em dashboard.js e dashboard_beneficiamento.js.
 */

export function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

export function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

export function getValue(id) {
    const el = document.getElementById(id);
    return el ? el.value : "";
}

export function isRenderable(element) {
    return Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
}

export function refreshIcons() {
    if (typeof lucide !== "undefined") lucide.createIcons();
}
