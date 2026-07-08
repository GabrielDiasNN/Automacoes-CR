/** Formatação de valores para telemetria — pt-BR, números tabulares. */

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${String(s).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${String(m % 60).padStart(2, "0")}m`;
}

export function formatAge(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}min`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR");
}

export function formatPercent(n: number | null | undefined, digits = 0): string {
  if (n == null) return "—";
  return `${n.toFixed(digits)}%`;
}

/** Taxa de sucesso a partir de contadores 24h. */
export function successRate(success: number, failures: number): number | null {
  const total = success + failures;
  if (total === 0) return null;
  return (success / total) * 100;
}

/** Trunca um ID longo de execução mantendo prefixo legível. */
export function shortId(id: string, len = 14): string {
  return id.length > len ? id.slice(0, len) : id;
}

/**
 * Formata um timestamp ISO naive (sem timezone, ex.: "2026-07-06T05:16:00",
 * como vem do Oracle) para DD/MM/YYYY HH:MM:SS. Parse manual via regex — não
 * usa `new Date()` para evitar reinterpretação de timezone pelo browser.
 */
export function formatDateTimeBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(iso);
  if (!match) return iso;
  const [, year, month, day, hour, minute, second] = match;
  return `${day}/${month}/${year} ${hour}:${minute}:${second ?? "00"}`;
}
