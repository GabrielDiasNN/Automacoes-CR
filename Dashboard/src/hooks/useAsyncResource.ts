import { usePolling, type PollingOptions, type PollingState } from "./usePolling";

/** Fetch sob demanda com cancelamento real — reaproveita toda a lógica já
 *  testada de `usePolling` (guarda de sequência, `AbortController`, mantém
 *  o último dado durante o refetch) com `intervalMs=0` (busca de novo só
 *  quando `deps` muda, nunca em intervalo).
 *
 *  Substitui o padrão `let cancelled = false; .then/.catch/.finally`
 *  duplicado 4x no app (`DetailDrawer`, `TingimentoPanel`,
 *  `ProductAutocomplete`, `CommandPalette`) — nenhuma cópia cancelava de
 *  verdade a requisição em voo; só descartava o resultado, deixando-a
 *  trafegar e consumir bucket de rate limit (achado nº 18, Onda 4).
 *
 *  `fetcher: null` desabilita o fetch (ex.: alvo do drawer ainda não
 *  escolhido) sem gerar requisição nem deixar `loading` preso em `true`. */
export function useAsyncResource<T>(
  fetcher: ((signal?: AbortSignal) => Promise<T>) | null,
  deps: unknown[] = [],
  options: PollingOptions = {},
): PollingState<T | null> {
  // `usePolling` lê o fetcher por ref a cada chamada, então este wrapper não
  // precisa de identidade estável (e memoizá-lo exigiria spread em deps).
  const wrapped = (signal?: AbortSignal) => (fetcher ? fetcher(signal) : Promise.resolve(null));
  return usePolling<T | null>(wrapped, 0, deps, { ...options, enabled: Boolean(fetcher) });
}
