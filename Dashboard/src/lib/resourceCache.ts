/** Cache stale-while-revalidate mínimo, em memória de módulo.
 *
 *  Objetivo estreito: `/painel → /sistema → /painel` refazia `getOverview` do
 *  zero a cada remontagem, com `Loading` de tela cheia, porque `data` volta a
 *  `null` quando o componente desmonta. Com este cache, a remontagem semeia
 *  `data` a partir da última resposta conhecida e revalida por baixo — sem
 *  flash de tela em branco.
 *
 *  NÃO é um framework de dados (a decisão de não adotar react-query segue
 *  valendo). Sem deduplicação de requisições em voo, sem GC automático além do
 *  TTL na leitura, sem persistência. Chave é escolhida pelo chamador
 *  (`usePolling(..., { cacheKey })`) porque o `fetcher` é opaco — não dá para
 *  derivar de URL.
 *
 *  Risco conhecido: cache mal invalidado mostra dado velho, pior que
 *  recarregar. Mitigação: como é sempre revalidado no mount, a janela de
 *  staleness é ~1 requisição; e ações que mutam estado invalidam a chave
 *  explicitamente (`useAction({ invalidate })`). `FreshnessTag` continua
 *  sinalizando quando a revalidação falha. */

interface Entry {
  data: unknown;
  ts: number;
}

const store = new Map<string, Entry>();

/** Retorna o valor em cache só se ele existe e está dentro do TTL.
 *
 *  A referência é ESTÁVEL entre leituras, de propósito. `usePolling` faz
 *  `setData(cached)` a cada tick do caminho de dedupe (`skipIfFresh`); com uma
 *  referência estável o React aborta o re-render pelo `Object.is`, e o
 *  `React.memo` das telas continua valendo. Devolver cópia a cada leitura
 *  trocaria um risco hipotético de mutação por um re-render garantido a cada
 *  15s — a proteção contra mutação é feita no `writeCache`, congelando. */
export function readCache<T>(key: string, ttlMs: number): T | undefined {
  const entry = store.get(key);
  if (!entry) return undefined;
  if (Date.now() - entry.ts > ttlMs) {
    store.delete(key);
    return undefined;
  }
  return entry.data as T;
}

/** Congela o valor (raso) antes de guardar: dois consumidores da mesma chave
 *  compartilham a instância, então uma mutação em um contaminaria o outro.
 *  Congelado, a tentativa de mutar lança em vez de corromper silenciosamente
 *  — módulo ES roda em strict mode. Raso basta: os payloads da API são JSON
 *  e ninguém muta estrutura aninhada hoje. */
export function writeCache(key: string, data: unknown): void {
  if (data !== null && typeof data === "object") Object.freeze(data);
  store.set(key, { data, ts: Date.now() });
}

/** Invalida uma chave exata ou, se `key` terminar em `:`, todas as que
 *  começam com esse prefixo (ex.: `invalidateCache("exec:")`). */
export function invalidateCache(key: string): void {
  if (key.endsWith(":")) {
    for (const k of store.keys()) if (k.startsWith(key)) store.delete(k);
    return;
  }
  store.delete(key);
}

/** Só para testes — zera o cache entre casos. */
export function _clearCache(): void {
  store.clear();
}
