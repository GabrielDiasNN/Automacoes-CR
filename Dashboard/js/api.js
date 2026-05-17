/**
 * api.js - Central de Automações v6.2.0
 * Camada de API e WebSocket (ES Module).
 */

// Detecta o host automaticamente
export const API_URL = ""; 
export const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
export let API_KEY = localStorage.getItem("orchestrator_api_key");

function promptApiKey() {
    const provided = prompt("Segurança Zero-Trust: Informe a API Key do Orchestrator:");
    if (!provided) return false;

    API_KEY = provided.trim();
    if (!API_KEY) return false;
    localStorage.setItem("orchestrator_api_key", API_KEY);
    return true;
}

// Zero-Trust Auth (bootstrap)
if (!API_KEY) {
    promptApiKey();
}

function clearApiKey() {
    API_KEY = "";
    localStorage.removeItem("orchestrator_api_key");
}

export async function api(path, method = "GET", body = null, options = {}) {
    if (!API_KEY && !promptApiKey()) {
        if (!options.silentAuthToast) {
            showToast("Informe uma API Key válida para continuar.", "warning");
        }
        return null;
    }

    try {
        const opts = {
            method,
            headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
        };
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(path, opts);
        if (res.status === 403) {
            clearApiKey();
            showToast("API Key inválida ou expirada. Informe novamente para continuar.", "warning");
            promptApiKey();
            return null;
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        if (res.status === 204) return {};
        return await res.json().catch(() => ({}));
    } catch (e) {
        console.warn(`[API] ${method} ${path} falhou:`, e.message);
        if (!options.silentErrorToast) {
            showToast(e.message || "Falha de comunicação com a API.", "error");
        }
        return null;
    }
}

export function showToast(msg, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${msg}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = "toastOut 0.3s ease forwards";
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

export function formatDate(val, short = false) {
    if (!val) return "-";
    try {
        // Assume formato DD/MM/YYYY HH:MM:SS vindo do backend
        if (short) return val.split(" ")[1] || val;
        return val;
    } catch (e) { return val; }
}

export function getBadgeClass(status) {
    switch (status) {
        case "SUCCESS": return "badge-success";
        case "ERROR": return "badge-danger";
        case "RUNNING": return "badge-warning pulse";
        case "PENDING": return "badge-muted";
        case "TIMEOUT": return "badge-danger";
        default: return "badge-muted";
    }
}

export function translateStatus(status) {
    if (!status) return "Sem histórico";
    const map = {
        "SUCCESS": "Sucesso",
        "ERROR": "Falha",
        "RUNNING": "Rodando",
        "PENDING": "Fila",
        "TIMEOUT": "Timeout",
        "TERMINATED": "Parado"
    };
    return map[status] || status;
}

export function decodeLogLine(line) {
    if (!line) return "";
    if (line.includes("B64:")) {
        return line.replace(/B64:([A-Za-z0-9+/=]+)/g, (match, b64) => {
            try {
                const bin = atob(b64);
                const bytes = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                return new TextDecoder("utf-8").decode(bytes);
            } catch (e) { return match; }
        });
    }
    return line;
}

export class LogStream {
    constructor(execId) {
        this.execId = execId;
        this.ws = null;
        this.onMessage = null;
        this.onClose = null;
    }
    connect() {
        if (this.ws) return;
        this.ws = new WebSocket(`${WS_URL}/ws/logs/${this.execId}`);
        this.ws.onmessage = (evt) => { if (this.onMessage) this.onMessage(evt.data); };
        this.ws.onclose = () => { if (this.onClose) this.onClose(); };
    }
    disconnect() {
        if (this.ws) { this.ws.close(); this.ws = null; }
    }
}
