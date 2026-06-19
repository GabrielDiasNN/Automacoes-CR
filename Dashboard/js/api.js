/**
 * api.js - Central de Automações v6.2.1
 * Camada de API e WebSocket (ES Module).
 */

// Detecta o host automaticamente
export const API_URL = "";
export const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
export let API_KEY = localStorage.getItem("orchestrator_api_key");
let latestCorrelationId = "SYSTEM";
let contractCompatibility = { compatible: true, reason: "" };
let apiKeyNoticeShown = false;
const BRAZIL_TIME_ZONE = "America/Sao_Paulo";
const BRAZIL_OFFSET_MINUTES = -180;

const FORMATTER_CACHE = new Map();

function nextRequestId() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function promptApiKey() {
    if (typeof prompt !== "function") return false;
    let provided = "";
    try {
        provided = prompt("Segurança Zero-Trust: Informe a API Key do Orchestrator:") || "";
    } catch {
        return false;
    }
    if (!provided) return false;

    API_KEY = provided.trim();
    if (!API_KEY) return false;
    localStorage.setItem("orchestrator_api_key", API_KEY);
    return true;
}

export function safePrompt(message, defaultValue = "") {
    if (typeof prompt !== "function") return null;
    try {
        return prompt(message, defaultValue);
    } catch {
        return null;
    }
}

function isValidDate(value) {
    return value instanceof Date && !Number.isNaN(value.getTime());
}

function getFormatter(options) {
    const key = JSON.stringify(options);
    if (!FORMATTER_CACHE.has(key)) {
        FORMATTER_CACHE.set(
            key,
            new Intl.DateTimeFormat("pt-BR", {
                timeZone: BRAZIL_TIME_ZONE,
                hour12: false,
                ...options,
            })
        );
    }
    return FORMATTER_CACHE.get(key);
}

function formatParts(date, options) {
    const formatter = getFormatter(options);
    const parts = formatter.formatToParts(date);
    const map = {};
    parts.forEach((part) => {
        if (part.type !== "literal") map[part.type] = part.value;
    });
    return map;
}

function buildBrazilDateFromParts(year, month, day, hour = 0, minute = 0, second = 0) {
    return new Date(Date.UTC(
        Number(year),
        Number(month) - 1,
        Number(day),
        Number(hour) - BRAZIL_OFFSET_MINUTES / 60,
        Number(minute),
        Number(second)
    ));
}

function parseBrazilFormattedString(value) {
    const trimmed = String(value || "").trim();
    const brMatch = trimmed.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$/);
    if (brMatch) {
        return buildBrazilDateFromParts(
            brMatch[3],
            brMatch[2],
            brMatch[1],
            brMatch[4] || 0,
            brMatch[5] || 0,
            brMatch[6] || 0
        );
    }

    const normalized = trimmed.replace(" ", "T");
    const isoHasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized);
    if (isoHasTimezone) {
        const parsed = new Date(normalized);
        return isValidDate(parsed) ? parsed : null;
    }

    const isoMatch = normalized.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?$/);
    if (isoMatch) {
        return buildBrazilDateFromParts(
            isoMatch[1],
            isoMatch[2],
            isoMatch[3],
            isoMatch[4] || 0,
            isoMatch[5] || 0,
            isoMatch[6] || 0
        );
    }

    const fallback = new Date(trimmed);
    return isValidDate(fallback) ? fallback : null;
}

export function parseDateValue(val) {
    if (val === null || val === undefined || val === "") return null;
    if (val instanceof Date) return isValidDate(val) ? val : null;
    if (typeof val === "number") {
        const parsed = new Date(val);
        return isValidDate(parsed) ? parsed : null;
    }
    if (typeof val !== "string") return null;
    return parseBrazilFormattedString(val);
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
    const normalizedMethod = String(method || "GET").toUpperCase();
    const isMutating = ["POST", "PUT", "PATCH", "DELETE"].includes(normalizedMethod);
    if (isMutating && !contractCompatibility.compatible) {
        if (!options.silentErrorToast) {
            showToast(
                contractCompatibility.reason || "Contrato front-back incompatível. Atualize o dashboard antes de executar ações operacionais.",
                "error"
            );
        }
        return null;
    }

    if (!API_KEY && !promptApiKey()) {
        if (!options.silentAuthToast && !apiKeyNoticeShown) {
            showToast("Informe uma API Key válida para continuar.", "warning");
            apiKeyNoticeShown = true;
        }
        return null;
    }

    // Robustez: timeout via AbortController evita travas indefinidas; retry com
    // backoff só para requisições idempotentes (GET) — mutações NÃO são repetidas
    // para não arriscar duplo-envio. 4xx/403 não são retentados.
    const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : 30000;
    const maxAttempts = isMutating ? 1 : 3;
    let lastErrorMessage = "Falha de comunicação com a API.";

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const opts = {
                method,
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": API_KEY,
                    "X-Request-Id": nextRequestId(),
                },
                signal: controller.signal,
            };
            if (body) opts.body = JSON.stringify(body);
            const res = await fetch(path, opts);
            const headerCorrelation = res.headers.get("x-request-id");
            if (headerCorrelation) latestCorrelationId = headerCorrelation;
            if (res.status === 403) {
                clearApiKey();
                if (!apiKeyNoticeShown) {
                    showToast("API Key inválida ou expirada. Informe novamente para continuar.", "warning");
                    apiKeyNoticeShown = true;
                }
                promptApiKey();
                return null;
            }
            // 5xx é transitório: para GET, tenta novamente antes de desistir.
            if (res.status >= 500 && attempt < maxAttempts) {
                lastErrorMessage = `HTTP ${res.status}`;
                await sleep(Math.min(2000, 300 * 2 ** (attempt - 1)));
                continue;
            }
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                if (err?.correlation_id) latestCorrelationId = err.correlation_id;
                const baseMessage = err.message || err.detail || `HTTP ${res.status}`;
                const correlationSuffix = latestCorrelationId ? ` (corr: ${latestCorrelationId})` : "";
                throw new Error(`${baseMessage}${correlationSuffix}`);
            }
            if (res.status === 204) return {};
            if (options.responseType === "text") {
                return await res.text();
            }
            const payload = await res.json().catch(() => ({}));
            if (payload?.trace?.correlation_id) latestCorrelationId = payload.trace.correlation_id;
            return payload;
        } catch (e) {
            const isAbort = e.name === "AbortError";
            lastErrorMessage = isAbort ? `Tempo limite excedido (${timeoutMs}ms)` : (e.message || lastErrorMessage);
            // Erros de rede (TypeError) e timeout (AbortError) são transitórios:
            // retenta apenas requisições idempotentes.
            const retriable = !isMutating && attempt < maxAttempts && (isAbort || e.name === "TypeError");
            if (retriable) {
                await sleep(Math.min(2000, 300 * 2 ** (attempt - 1)));
                continue;
            }
            console.warn(`[API] ${method} ${path} falhou:`, lastErrorMessage);
            if (!options.silentErrorToast) {
                showToast(lastErrorMessage, "error");
            }
            return null;
        } finally {
            clearTimeout(timer);
        }
    }
    return null;
}

export function getLastCorrelationId() {
    return latestCorrelationId;
}

export function setContractCompatibility(compatible, reason = "") {
    contractCompatibility = { compatible: Boolean(compatible), reason: String(reason || "") };
}

export function showToast(msg, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const span = document.createElement("span");
    span.textContent = msg;
    toast.appendChild(span);
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = "toastOut 0.3s ease forwards";
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

export function formatDate(val, short = false) {
    if (!val) return "-";
    try {
        const parsed = parseDateValue(val);
        if (!parsed) return String(val);

        if (short) {
            const timeParts = formatParts(parsed, {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
            });
            return `${timeParts.hour || "00"}:${timeParts.minute || "00"}:${timeParts.second || "00"}`;
        }

        const dateParts = formatParts(parsed, {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });

        return `${dateParts.day || "00"}/${dateParts.month || "00"}/${dateParts.year || "0000"} ${dateParts.hour || "00"}:${dateParts.minute || "00"}:${dateParts.second || "00"}`;
    } catch { return val; }
}

export function getBadgeClass(status) {
    switch (status) {
        case "SUCCESS": return "badge-success";
        case "PARTIAL": return "badge-warning";
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
        "PARTIAL": "Parcial",
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
            } catch { return match; }
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
        this.reconnectTimeout = null;
        this.attempt = 0;
        this.forceClose = false;
    }
    connect() {
        if (this.ws) return;
        this.forceClose = false;
        const keyParam = API_KEY ? `?key=${encodeURIComponent(API_KEY)}` : "";
        this.ws = new WebSocket(`${WS_URL}/ws/logs/${this.execId}${keyParam}`);

        this.ws.onopen = () => {
            this.attempt = 0; // Reset reconnection attempt counter on success
        };

        this.ws.onmessage = (evt) => {
            if (this.onMessage) this.onMessage(evt.data);
        };

        this.ws.onclose = (evt) => {
            if (this.onClose) this.onClose(evt);
            this.ws = null;
            if (!this.forceClose) {
                this._reconnect();
            }
        };

        this.ws.onerror = (err) => {
            console.warn("[WS] Erro na conexão LogStream:", err);
        };
    }
    _reconnect() {
        if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
        this.attempt++;
        const delay = Math.min(2000 * Math.pow(1.5, this.attempt - 1), 30000);
        console.log(`[WS] Tentando reconexão em ${Math.round(delay)}ms (tentativa ${this.attempt})...`);
        this.reconnectTimeout = setTimeout(() => {
            if (!this.forceClose) {
                this.connect();
            }
        }, delay);
    }
    disconnect() {
        this.forceClose = true;
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }
        if (this.ws) {
            this.ws.close(1000, "Fechamento intencional");
            this.ws = null;
        }
    }
}
