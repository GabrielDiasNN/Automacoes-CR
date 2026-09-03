import { useEffect, useState } from "react";

/** Espelha `window.matchMedia(query)` em estado React, reagindo a resize
 *  (inclusive DevTools em modo responsivo). SSR-safe: `false` até o primeiro
 *  effect rodar no cliente. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
