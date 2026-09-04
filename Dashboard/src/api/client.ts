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

async function doFetch(path: string, init: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    signal: withTimeout(init.signal ?? undefined),
    headers: { ...headers(), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    // `typeof res.text === "function"` tolera respostas mockadas em teste sem
    // `.text()` (ex.: `useWebSocket.test.ts`) — em produção `Response` sempre
    // tem o método.
    const text =
      typeof res.text === "function" ? await res.text().catch(() => res.statusText) : (res.statusText ?? "");

    // O backend nunca retorna 401, e usa 403 para DOIS casos distintos:
    //  - API Key inválida/ausente  (middleware.get_api_key → "...API Key...")
    //  - operação proibida: path traversal em download de artefato, diretório
    //    fora do projeto  ("Acesso negado ao arquivo." / "...fora do projeto.")
    // Só o primeiro deve derrubar a sessão. Antes, QUALQUER 403 chamava
    // clearKey() e jogava o operador na tela de login — inclusive um download
    // barrado por path safety (surto de 403 de 07/08/2026). O 401 continua
    // tratado por segurança, embora hoje seja código morto no backend.
    const isAuthFailure = res.status === 401 || (res.status === 403 && /api\s*key/i.test(text));
    if (isAuthFailure && _unauthorizedHandler) {
      _unauthorizedHandler(res.status);
    }

    const retryAfterHeader = res.headers?.get("Retry-After") ?? null;
    const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : null;
    throw new ApiError(res.status, text, Number.isFinite(retryAfter) ? retryAfter : null);
  }
  return res;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await doFetch(path, init);
  return res.json() as Promise<T>;
}

/** Como `request`, mas para rotas que devolvem texto puro em vez de JSON
 *  (ex.: `GET /api/portfolio/runbook/{catalog_id}`, `PlainTextResponse` com
 *  o Markdown bruto do runbook — `res.json()` quebraria nessas respostas). */
async function requestText(path: string, init: RequestInit = {}): Promise<string> {
  const res = await doFetch(path, init);
  return res.text();
}

/** Como `request`, mas para download de arquivo binário (ex.: artefato de
 *  execução via `GET /api/executions/{id}/download`). Reaproveita `doFetch`
 *  — o mesmo caminho de timeout/headers/401-403 — em vez de um `<a download
 *  href>` cru, que não manda o header `X-API-Key` no handshake. */
async function requestBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const res = await doFetch(path, init);
  return res.blob();
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
  // `signal ?? null` / `body ?? null`: `RequestInit` aceita `null` mas nao
  // `undefined` sob `exactOptionalPropertyTypes`.
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal: signal ?? null }),
  getText: (path: string, signal?: AbortSignal) => requestText(path, { signal: signal ?? null }),
  getBlob: (path: string, signal?: AbortSignal) => requestBlob(path, { signal: signal ?? null }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : null,
      signal: signal ?? null,
    }),
  put: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : null,
      signal: signal ?? null,
    }),
  delete: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { method: "DELETE", signal: signal ?? null }),
};
