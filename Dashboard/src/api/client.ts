const API_BASE = "";
const STORAGE_KEY = "orchestrator_api_key";
const REQUEST_TIMEOUT_MS = 30_000;

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

/** Erro de requisição tipado — permite discriminar por `status`/`retryAfter`
 *  sem parsear a mensagem. `.message` mantém o formato `"${status} ${body}"`
 *  por compatibilidade com o código e os testes existentes. */
export class ApiError extends Error {
  readonly status: number;
  /** Segundos até a janela liberar, lido de `Retry-After` (presente em 429 —
   *  ver `Orchestrator/app/middleware.py` `RateLimitMiddleware`). */
  readonly retryAfter: number | null;

  constructor(status: number, body: string, retryAfter: number | null = null) {
    super(`${status} ${body}`);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

/** Combina o signal do chamador (ex.: aborto de `usePolling` ao trocar de
 *  parâmetro) com um timeout — sem isso, uma requisição pendurada nunca
 *  resolve e a tela fica em `loading` para sempre. */
function withTimeout(signal?: AbortSignal): AbortSignal {
  const timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  return signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    signal: withTimeout(init.signal ?? undefined),
    headers: { ...headers(), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    if ((res.status === 401 || res.status === 403) && _unauthorizedHandler) {
      _unauthorizedHandler(res.status);
    }
    // `typeof res.text === "function"` tolera respostas mockadas em teste sem
    // `.text()` (ex.: `useWebSocket.test.ts`) — em produção `Response` sempre
    // tem o método.
    const text =
      typeof res.text === "function" ? await res.text().catch(() => res.statusText) : (res.statusText ?? "");
    const retryAfterHeader = res.headers?.get("Retry-After") ?? null;
    const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : null;
    throw new ApiError(res.status, text, Number.isFinite(retryAfter) ? retryAfter : null);
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
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    }),
  put: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    }),
  delete: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: "DELETE", signal }),
};
