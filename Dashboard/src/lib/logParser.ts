/** Parsing das linhas de log de execução.
 *
 * Extraído de components/ui/LogViewer.tsx: é lógica pura e não trivial (regex de
 * nível, junção de continuações), e `components/` está fora da cobertura do
 * Vitest por contrato — em lib/ passa a ser testável unitariamente.
 */

export type Level = "info" | "warn" | "error" | "debug" | "plain";

export interface LogLine {
  raw: string;
  level: Level;
  time: string | null;
  source: string | null;
  message: string;
}

// Ex.: [30/07/2026 08:30:05] [PS] [INFO] [ExecId:CRON_2_1785411000] mensagem...
export const LINE_RE =
  /^\[([^\]]+)\]\s*\[([^\]]+)\]\s*\[(INFO|WARN|WARNING|ERROR|ERRO|DEBUG)\]\s*(?:\[[^\]]*\]\s*)*(.*)$/i;

export function parseLine(raw: string): LogLine {
  const match = LINE_RE.exec(raw);
  if (!match) {
    return { raw, level: "plain", time: null, source: null, message: raw };
  }
  const [, time, source, levelToken, message] = match;
  const token = levelToken.toUpperCase();
  const level: Level = token.startsWith("ERR")
    ? "error"
    : token.startsWith("WARN")
      ? "warn"
      : token === "DEBUG"
        ? "debug"
        : "info";
  return { raw, level, time, source, message: message.trim() || raw };
}

/** Junta continuações (linhas sem cabeçalho) à última linha reconhecida. */
export function parseLog(text: string): LogLine[] {
  const lines: LogLine[] = [];
  for (const raw of text.split(/\r?\n/)) {
    if (!raw.trim()) continue;
    const parsed = parseLine(raw);
    if (parsed.level === "plain" && lines.length && LINE_RE.test(lines[lines.length - 1].raw)) {
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
