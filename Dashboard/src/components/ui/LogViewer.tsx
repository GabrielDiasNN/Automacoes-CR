import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, Maximize2, Minimize2, SlidersHorizontal } from "lucide-react";
import styles from "./LogViewer.module.css";

type Level = "info" | "warn" | "error" | "debug" | "plain";

interface LogLine {
  raw: string;
  level: Level;
  time: string | null;
  source: string | null;
  message: string;
}

const LEVEL_ORDER: Exclude<Level, "plain">[] = ["error", "warn", "info", "debug"];

const LEVEL_LABEL: Record<Level, string> = {
  error: "erro",
  warn: "aviso",
  info: "info",
  debug: "debug",
  plain: "outros",
};

const LEVEL_TINT: Record<Exclude<Level, "plain">, string> = {
  error: "var(--red)",
  warn: "var(--amber)",
  info: "var(--blue)",
  debug: "var(--grey)",
};

// Ex.: [30/07/2026 08:30:05] [PS] [INFO] [ExecId:CRON_2_1785411000] mensagem...
const LINE_RE =
  /^\[([^\]]+)\]\s*\[([^\]]+)\]\s*\[(INFO|WARN|WARNING|ERROR|ERRO|DEBUG)\]\s*(?:\[[^\]]*\]\s*)*(.*)$/i;

function parseLine(raw: string): LogLine {
  const match = LINE_RE.exec(raw);
  if (!match) {
    return { raw, level: "plain", time: null, source: null, message: raw };
  }
  const [, time, source, levelToken, message] = match;
  const token = levelToken.toUpperCase();
  const level: Level = token.startsWith("ERR") ? "error" : token.startsWith("WARN") ? "warn" : token === "DEBUG" ? "debug" : "info";
  return { raw, level, time, source, message: message.trim() || raw };
}

/** Junta continuações (linhas sem cabeçalho) à última linha reconhecida. */
function parseLog(text: string): LogLine[] {
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

function highlight(text: string, query: string) {
  if (!query.trim()) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export function LogViewer({ text, loading }: { text: string; loading?: boolean }) {
  const [query, setQuery] = useState("");
  const [activeLevels, setActiveLevels] = useState<Set<Level>>(new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  const parsed = useMemo(() => parseLog(text || ""), [text]);

  const counts = useMemo(() => {
    const c: Record<Level, number> = { info: 0, warn: 0, error: 0, debug: 0, plain: 0 };
    for (const l of parsed) c[l.level]++;
    return c;
  }, [parsed]);

  const filtered = useMemo(() => {
    return parsed.filter((l) => {
      if (activeLevels.size > 0 && !activeLevels.has(l.level)) return false;
      if (query.trim() && !l.message.toLowerCase().includes(query.trim().toLowerCase())) return false;
      return true;
    });
  }, [parsed, activeLevels, query]);

  useEffect(() => {
    if (autoScroll && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [filtered.length, autoScroll]);

  function toggleLevel(level: Level) {
    setActiveLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard indisponível — ignora silenciosamente
    }
  }

  return (
    <div className={[styles.wrap, fullscreen ? styles.fullscreen : ""].filter(Boolean).join(" ")}>
      <div className={styles.toolbar}>
        {LEVEL_ORDER.map((level) =>
          counts[level] > 0 ? (
            <button
              key={level}
              type="button"
              className={[styles.chip, activeLevels.has(level) ? styles.active : ""].filter(Boolean).join(" ")}
              style={{ "--chip-color": LEVEL_TINT[level] } as React.CSSProperties}
              onClick={() => toggleLevel(level)}
              title={`Filtrar ${LEVEL_LABEL[level]}`}
            >
              {LEVEL_LABEL[level]} <span className={styles.chipCount}>{counts[level]}</span>
            </button>
          ) : null
        )}
        <input
          className={styles.search}
          type="text"
          placeholder="buscar nos logs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className={styles.filler} />
        <button
          type="button"
          className={[styles.iconBtn, autoScroll ? styles.active : ""].filter(Boolean).join(" ")}
          onClick={() => setAutoScroll((v) => !v)}
          title={autoScroll ? "Auto-scroll ativo" : "Auto-scroll pausado"}
        >
          <SlidersHorizontal size={13} />
        </button>
        <button type="button" className={styles.iconBtn} onClick={handleCopy} title="Copiar logs">
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
        <button
          type="button"
          className={styles.iconBtn}
          onClick={() => setFullscreen((v) => !v)}
          title={fullscreen ? "Sair da tela cheia" : "Tela cheia"}
        >
          {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </button>
      </div>

      <div className={styles.body} ref={bodyRef} style={fullscreen ? { maxHeight: "none" } : { maxHeight: 360 }}>
        {loading ? (
          <div className={styles.emptyState}>carregando logs…</div>
        ) : filtered.length === 0 ? (
          <div className={styles.emptyState}>
            {parsed.length === 0 ? "— sem logs —" : "nenhuma linha corresponde ao filtro"}
          </div>
        ) : (
          filtered.map((line, i) => (
            <div key={i} className={[styles.row, styles[line.level]].join(" ")}>
              <span className={styles.time}>{line.time ?? ""}</span>
              <span className={styles.source}>{line.source ? `[${line.source}]` : ""}</span>
              <span className={styles.level}>{line.level !== "plain" ? line.level.toUpperCase() : ""}</span>
              <span className={styles.msg}>{highlight(line.message, query)}</span>
            </div>
          ))
        )}
      </div>

      <div className={styles.footer}>
        <span>
          {filtered.length}/{parsed.length} linhas
        </span>
        {counts.error > 0 && <span style={{ color: "var(--red)" }}>{counts.error} erro(s)</span>}
        {counts.warn > 0 && <span style={{ color: "var(--amber)" }}>{counts.warn} aviso(s)</span>}
      </div>
    </div>
  );
}
