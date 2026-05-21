/**
 * ui_manager.js - Central de Automações v6.2.0
 * Gestão de UI, Navegação e Renderização de Tabelas.
 */

import { api, showToast, formatDate, getBadgeClass, translateStatus } from './api.js?v=20260521c';

export function initNavigation() {
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.addEventListener("click", () => {
            document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
            document.querySelectorAll(".view-content").forEach((v) => v.classList.remove("active"));
            item.classList.add("active");
            const target = item.dataset.target;
            document.getElementById(`view-${target}`).classList.add("active");
            const mainContent = document.querySelector(".main-content");
            if (mainContent) mainContent.scrollTop = 0;
            window.scrollTo(0, 0);
            
            // Dispatch custom event for modular loading
            window.dispatchEvent(new CustomEvent('view-changed', { detail: { target } }));
        });
    });
}

export function updateConnectionStatus(isOnline) {
    const dot = document.getElementById("server-dot");
    const txt = document.getElementById("server-txt");
    if (!dot || !txt) return;
    
    if (isOnline) {
        dot.className = "dot online";
        txt.innerText = "ONLINE";
    } else {
        dot.className = "dot offline";
        txt.innerText = "OFFLINE";
    }
}

export function renderPagination(total, current, pages, containerId, callback) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    if (pages <= 1) {
        container.innerHTML = "";
        return;
    }
    
    let html = `<span class="page-info">${total} registros</span><div class="page-controls">`;
    html += `<button class="btn-page" ${current === 1 ? "disabled" : ""} data-page="${current - 1}">&lt;</button>`;
    html += `<span class="page-current">${current} / ${pages}</span>`;
    html += `<button class="btn-page" ${current === pages ? "disabled" : ""} data-page="${current + 1}">&gt;</button>`;
    html += `</div>`;
    
    container.innerHTML = html;
    container.querySelectorAll(".btn-page[data-page]").forEach((button) => {
        button.addEventListener("click", () => {
            const page = Number(button.dataset.page || 1);
            callback(page);
        });
    });
}
