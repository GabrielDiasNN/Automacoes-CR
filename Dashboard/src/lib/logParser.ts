/** Parsing das linhas de log de execução.
 *
 * Dois formatos coexistem durante o rollout do padrão de logging estruturado
 * (docs/logging-standard.md):
 *   1. legado  — `[30/07/2026 08:30:05] [PS] [INFO] [ExecId:...] mensagem`
 *   2. evento  — uma linha JSON no envelope de docs/log-event.schema.json
 *
 * Extraído de components/ui/LogViewer.tsx: `components/` está fora da cobertura
 * do Vitest por contrato — em lib/ passa a ser testável unitariamente.
 */

export type Level = "info" | "warn" | "error" | "debug" | "plain";

export interface LogLine {
  raw: string;
  level: Level;
  time: string | null;
  source: string | null;
  message: string;
  /** Presentes apenas quando a linha é um evento estruturado. */
  event?: string;
  step?: string;
  traceId?: string;
}

// Ex.: [30/07/2026 08:30:05] [PS] [INFO] [ExecId:CRON_2_1785411000] mensagem...
export const LINE_RE =
  /^\[([^\]]+)\]\s*\[([^\]]+)\]\s*\[(INFO|WARN|WARNING|ERROR|ERRO|DEBUG)\]\s*(?:\[[^\]]*\]\s*)*(.*)$/i;

const COMPONENT_TAG: Record<string, string> = {
  ps_script: "PS",
  python_domain: "PY",
  node_whatsapp: "WA",
  orchestrator_api: "ORC",
  orchestrator_worker: "ORC",
  orchestrator_scheduler: "ORC",
};

function levelFromToken(token: string): Level {
  const up = token.toUpperCase();
  if (up.startsWith("ERR")) return "error";
  if (up.startsWith("WARN")) return "warn";
  if (up === "DEBUG") return "debug";
  return "info";
}

/** `2026-08-27T07:01:51Z` -> `27/08/2026 07:01:51` (hora local do navegador). */
function formatTs(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(
    d.getMinutes(),
  )}:${p(d.getSeconds())}`;
}

function messageFromEvent(evt: Record<string, unknown>): string {
  const msg = typeof evt.message === "string" ? evt.message : "";
  const step = typeof evt.step === "string" ? evt.step : "";
  switch (evt.event) {
    case "execution.start":
      return `▶ ${msg || "início da execução"}`;
    case "execution.end": {
      const code = evt.outcome_code;
      const reason = typeof evt.outcome_reason === "string" ? evt.outcome_reason : msg;
      const rc = evt.record_counts as Record<string, number> | undefined;
      const counts = rc
        ? " · " +
          Object.entries(rc)
            .map(([k, v]) => `${k}=${v}`)
            .join(" ")
        : "";
      return `■ FIM code=${code ?? "?"} — ${reason}${counts}`;
    }
    case "step.start":
      return `▸ ${step}${msg ? `: ${msg}` : ""}`;
    case "step.end": {
      const ok = evt.ok === false ? "✗" : "✓";
      const ms = typeof evt.duration_ms === "number" ? ` (${(evt.duration_ms / 1000).toFixed(1)}s)` : "";
      return `${ok} ${step}${ms}${msg ? ` — ${msg}` : ""}`;
    }
    case "retry.attempt": {
      const a = evt.attempt;
      const max = evt.max_attempts;
      return `⇄ ${step} tentativa ${a}/${max}${msg ? ` — ${msg}` : ""}`;
    }
    default:
      return step ? `[${step}] ${msg}` : msg;
  }
}

function parseEnvelope(raw: string): LogLine | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return null;
  let evt: Record<string, unknown>;
  try {
    evt = JSON.parse(trimmed) as Record<string, unknown>;
  } catch {
    return null;
  }
  if (
    typeof evt.ts !== "string" ||
    typeof evt.level !== "string" ||
    typeof evt.event !== "string" ||
    typeof evt.message !== "string"
  ) {
    return null;
  }
  return {
    raw,
    level: levelFromToken(evt.level),
    time: formatTs(evt.ts),
    source:
      (typeof evt.component === "string" && COMPONENT_TAG[evt.component]) ||
      (typeof evt.component === "string" ? evt.component : null),
    message: messageFromEvent(evt),
    event: typeof evt.event === "string" ? evt.event : undefined,
    step: typeof evt.step === "string" ? evt.step : undefined,
    traceId: typeof evt.trace_id === "string" ? evt.trace_id : undefined,
  };
}

export function parseLine(raw: string): LogLine {
  const envelope = parseEnvelope(raw);
  if (envelope) return envelope;

  const match = LINE_RE.exec(raw);
  if (!match) {
    return { raw, level: "plain", time: null, source: null, message: raw };
  }
  const [, time, source, levelToken, message] = match;
  return {
    raw,
    level: levelFromToken(levelToken),
    time,
    source,
    message: message.trim() || raw,
  };
}

/** Junta continuações (linhas sem cabeçalho) à última linha reconhecida. */
export function parseLog(text: string): LogLine[] {
  const lines: LogLine[] = [];
  for (const raw of text.split(/\r?\n/)) {
    if (!raw.trim()) continue;
    const parsed = parseLine(raw);
    if (parsed.level === "plain" && lines.length && lines[lines.length - 1].level !== "plain") {
      lines[lines.length - 1].message += `\n${raw}`;
      continue;
    }
    lines.push(parsed);
  }
  return lines;
}

export function countByLevel(lines: LogLine[]): Record<Level, number> {
  const counts: Record<Level, number> = { info: 0, warn: 0, error: 0, debug: 0, plain: 0 };
  for (const line of lines) counts[line.level]++;
  return counts;
}

/** Filtra por níveis ativos (conjunto vazio = todos) e por texto na mensagem. */
export function filterLines(lines: LogLine[], activeLevels: Set<Level>, query: string): LogLine[] {
  const needle = query.trim().toLowerCase();
  return lines.filter((line) => {
    if (activeLevels.size > 0 && !activeLevels.has(line.level)) return false;
    if (needle && !line.message.toLowerCase().includes(needle)) return false;
    return true;
  });
}
