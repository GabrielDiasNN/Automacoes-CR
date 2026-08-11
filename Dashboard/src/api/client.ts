const API_BASE = "";
const STORAGE_KEY = "orchestrator_api_key";

// Inicializa a key do sessionStorage imediatamente no carregamento do módulo
// para evitar race condition entre ApiKeyContext.useEffect e os primeiros fetches
let _apiKey = (typeof sessionStorage !== "undefined" ? sessionStorage.getItem(STORAGE_KEY) : null) ?? "";
let _unauthorizedHandler: ((status: number) => void) | null = null;

export function setApiKey(key: string) {
  _apiKey = key;
}

export function getApiKey(): string {
  return _apiKey;
}

export function setUnauthorizedHandler(handler: ((status: number) => void) | null) {
  _unauthorizedHandler = handler;
}

function headers(): HeadersInit {
  return _apiKey ? { "X-API-Key": _apiKey } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...headers(), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    if ((res.status === 401 || res.status === 403) && _unauthorizedHandler) {
      _unauthorizedHandler(res.status);
    }
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

/** Monta query-string a partir de um objeto, omitindo null/undefined. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  /** `signal` permite cancelar a requisição — ver usePolling, que aborta o
   *  fetch anterior ao trocar de parâmetros ou desmontar. */
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
