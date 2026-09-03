import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, Maximize2, Minimize2, SlidersHorizontal } from "lucide-react";
import { countByLevel, filterLines, parseLog, type Level } from "../../lib/logParser";
import { IconButton } from "./IconButton";
import { Input } from "./Input";
import styles from "./LogViewer.module.css";

// Teto de linhas efetivamente montadas no DOM. O worker permite até 5 MB de log
// por execução (MAX_LOG_CHARS): renderizar tudo criaria dezenas de milhares de
// nós e travaria a aba. Mostramos a JANELA FINAL — que é a relevante para
// diagnóstico e a que o auto-scroll persegue — e sinalizamos o que ficou fora.
const MAX_RENDERED_LINES = 2_000;

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

/** Destaca TODAS as ocorrências do termo buscado, não só a primeira. */
function highlight(text: string, query: string) {
  const needle = query.trim();
  if (!needle) return text;

  const haystack = text.toLowerCase();
  const target = needle.toLowerCase();
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let idx = haystack.indexOf(target);
  if (idx === -1) return text;

  let key = 0;
  while (idx !== -1) {
    if (idx > cursor) parts.push(text.slice(cursor, idx));
    parts.push(<mark key={key++}>{text.slice(idx, idx + needle.length)}</mark>);
    cursor = idx + needle.length;
    idx = haystack.indexOf(target, cursor);
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}

export function LogViewer({ text, loading }: { text: string; loading?: boolean }) {
  const [query, setQuery] = useState("");
  const [activeLevels, setActiveLevels] = useState<Set<Level>>(new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  const parsed = useMemo(() => parseLog(text || ""), [text]);

  const counts = useMemo(() => countByLevel(parsed), [parsed]);

  const filtered = useMemo(
    () => filterLines(parsed, activeLevels, query),
    [parsed, activeLevels, query],
  );

  // Janela final efetivamente montada — ver MAX_RENDERED_LINES.
  const hidden = Math.max(0, filtered.length - MAX_RENDERED_LINES);
  const visible = useMemo(
    () => (hidden > 0 ? filtered.slice(-MAX_RENDERED_LINES) : filtered),
    [filtered, hidden],
  );

  useEffect(() => {
    if (autoScroll && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [visible.length, autoScroll]);

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
        <Input
          className={styles.search}
          type="text"
          placeholder="buscar nos logs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Buscar nos logs"
        />
        <div className={styles.filler} />
        <IconButton
          size="sm"
          active={autoScroll}
          onClick={() => setAutoScroll((v) => !v)}
          title={autoScroll ? "Auto-scroll ativo" : "Auto-scroll pausado"}
          aria-label={autoScroll ? "Desativar auto-scroll" : "Ativar auto-scroll"}
        >
          <SlidersHorizontal size={13} />
        </IconButton>
        <IconButton size="sm" onClick={() => void handleCopy()} title="Copiar logs" aria-label="Copiar logs">
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </IconButton>
        <IconButton
          size="sm"
          onClick={() => setFullscreen((v) => !v)}
          title={fullscreen ? "Sair da tela cheia" : "Tela cheia"}
          aria-label={fullscreen ? "Sair da tela cheia" : "Tela cheia"}
        >
          {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </IconButton>
      </div>

      <div
        className={styles.body}
        ref={bodyRef}
        role="log"
        style={fullscreen ? { maxHeight: "none" } : { maxHeight: 360 }}
      >
        {loading ? (
          <div className={styles.emptyState}>carregando logs…</div>
        ) : filtered.length === 0 ? (
          <div className={styles.emptyState}>
            {parsed.length === 0 ? "— sem logs —" : "nenhuma linha corresponde ao filtro"}
          </div>
        ) : (
          <>
          {hidden > 0 && (
            <div className={styles.emptyState}>
              {hidden} linha(s) anterior(es) ocultada(s) — exibindo as últimas {MAX_RENDERED_LINES}.
              Use o botão de copiar para obter o log completo.
            </div>
          )}
          {visible.map((line, i) => (
            <div key={i} className={[styles.row, styles[line.level]].join(" ")}>
              <span className={styles.time}>{line.time ?? ""}</span>
              <span className={styles.source}>{line.source ? `[${line.source}]` : ""}</span>
              <span className={styles.level}>{line.level !== "plain" ? line.level.toUpperCase() : ""}</span>
              <span className={styles.msg}>{highlight(line.message, query)}</span>
            </div>
          ))}
          </>
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
