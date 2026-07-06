import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pause, Play, Trash2 } from "lucide-react";
import { useDiagnostics } from "../hooks/useDiagnostics";
import { useWebSocket } from "../hooks/useWebSocket";
import { usePolling } from "../hooks/usePolling";
import { getApiKey } from "../api/client";
import { orchestratorApi, type SystemHistory } from "../api/orchestrator";
import {
  Button,
  Card,
  Nameplate,
  Sparkline,
  StatTile,
  StatusTag,
  TimeSeries,
  type SeriesLine,
} from "../components/ui";
import { healthTone, healthLabel } from "../lib/status";
import page from "./page.module.css";

interface LogLine {
  id: number;
  execId: string;
  type: string;
  message: string;
  tone: string;
}

const WS_BASE = `${typeof location !== "undefined" && location.protocol === "https:" ? "wss:" : "ws:"}//${
  typeof location !== "undefined" ? location.host : ""
}`;

function lineColor(message: string): string {
  if (/erro|error|fail|falh|exception|traceback|critical/i.test(message)) return "var(--red)";
  if (/warn|aviso|atenç|timeout|retry/i.test(message)) return "var(--amber)";
  if (/success|sucesso|conclu|ok\b/i.test(message)) return "var(--green)";
  return "var(--text-mid)";
}

/** Traduz o evento real do event bus ({type, data}) em uma linha legível do console. */
function describeEvent(type: string, data: Record<string, unknown>): { message: string; tone: string } {
  switch (type) {
    case "LOG_UPDATE": {
      const preview = String(data.preview ?? "");
      return { message: preview, tone: lineColor(preview) };
    }
    case "TASK_STARTED":
      return { message: `iniciada (automação ${data.automation_id ?? "—"})`, tone: "var(--cyan)" };
    case "TASK_STOPPED":
      return { message: "interrompida pelo operador", tone: "var(--amber)" };
    case "TASK_TIMEOUT":
      return { message: "timeout atingido", tone: "var(--red)" };
    case "TASK_FAILED":
      return { message: `falhou: ${data.error ?? "erro desconhecido"}`, tone: "var(--red)" };
    case "TASK_COMPLETED":
      return {
        message: `concluída: ${data.status ?? "—"} (${data.duration_seconds ?? "?"}s, exit ${data.exit_code ?? "?"})`,
        tone: data.status === "SUCCESS" ? "var(--green)" : "var(--red)",
      };
    default:
      return { message: JSON.stringify(data), tone: "var(--text-lo)" };
  }
}

const HISTORY_WINDOWS = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
];

const selectStyle: React.CSSProperties = {
  background: "var(--surface-up)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  color: "var(--text-mid)",
  fontFamily: "var(--font-mono)",
  fontSize: "var(--fs-small)",
  padding: "6px var(--sp-3)",
};

interface ClickableTileProps {
  onClick?: () => void;
  children: React.ReactNode;
}

function ClickableTile({ onClick, children }: ClickableTileProps) {
  if (!onClick) return <>{children}</>;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter") onClick();
      }}
      style={{ cursor: "pointer" }}
    >
      {children}
    </div>
  );
}

export function MonitorPage() {
  const navigate = useNavigate();
  const { health, worker } = useDiagnostics(10_000);
  const [lines, setLines] = useState<LogLine[]>([]);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const idRef = useRef(0);
  const consoleRef = useRef<HTMLDivElement>(null);

  const [execFilter, setExecFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [q, setQ] = useState("");

  const key = getApiKey();
  const handleMessage = useCallback((evt: MessageEvent) => {
    if (pausedRef.current) return;
    try {
      const parsed = JSON.parse(evt.data as string) as { type?: string; data?: Record<string, unknown> };
      const type = parsed.type ?? "UNKNOWN";
      const data = parsed.data ?? {};
      const execId = String(data.exec_id ?? "—");
      const { message, tone } = describeEvent(type, data);
      setLines((prev) => [...prev, { id: (idRef.current += 1), execId, type, message, tone }].slice(-300));
    } catch {
      // mensagem não-JSON ignorada
    }
  }, []);

  const { status } = useWebSocket(key ? `${WS_BASE}/ws/events?key=${encodeURIComponent(key)}` : "", {
    onMessage: handleMessage,
    enabled: !!key,
  });

  useEffect(() => {
    if (!paused) consoleRef.current?.scrollTo({ top: consoleRef.current.scrollHeight });
  }, [lines, paused]);

  const wsTone = status === "open" ? "green" : status === "connecting" ? "amber" : "red";

  const execOptions = useMemo(() => Array.from(new Set(lines.map((l) => l.execId))).slice(-30), [lines]);
  const typeOptions = useMemo(() => Array.from(new Set(lines.map((l) => l.type))), [lines]);
  const filteredLines = useMemo(
    () =>
      lines.filter(
        (l) =>
          (!execFilter || l.execId === execFilter) &&
          (!typeFilter || l.type === typeFilter) &&
          (!q || l.message.toLowerCase().includes(q.toLowerCase())),
      ),
    [lines, execFilter, typeFilter, q],
  );

  const [historyHours, setHistoryHours] = useState(24);
  const fetchHistory = useCallback(() => orchestratorApi.getHistory(historyHours), [historyHours]);
  const { data: history } = usePolling<SystemHistory>(fetchHistory, 60_000, [historyHours]);

  const historyItems = history?.items ?? [];
  const xLabels = historyItems.map((p) => String(p.timestamp).slice(11, 16));
  const pendingSeries = historyItems.map((p) => p.pending_count);
  const runningSeries = historyItems.map((p) => p.running_count);
  const pendingLine: SeriesLine = { label: "pendentes", values: pendingSeries, tone: "amber" };
  const runningLine: SeriesLine = { label: "em execução", values: runningSeries, tone: "cyan" };

  const goToExecucoes = useCallback((execStatus: string) => navigate(`/execucoes?status=${execStatus}`), [navigate]);

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// operação"
        title="Monitor"
        actions={
          <StatusTag tone={wsTone} dot pulse={status === "connecting"}>
            sinal {status === "open" ? "ativo" : status}
          </StatusTag>
        }
      />

      <div className={page.tiles}>
        <StatTile
          label="status geral"
          value={
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-body)", textTransform: "uppercase" }}>
              {healthLabel(health?.status)}
            </span>
          }
          tone={healthTone(health?.status)}
          big={false}
        />
        <ClickableTile onClick={() => goToExecucoes("PENDING")}>
          <StatTile
            label="pendentes"
            value={health?.pending_tasks ?? 0}
            tone={health && health.pending_tasks > 0 ? "amber" : undefined}
            hint={pendingSeries.length > 1 ? <Sparkline data={pendingSeries} tone="amber" width={96} height={24} /> : undefined}
          />
        </ClickableTile>
        <ClickableTile onClick={() => goToExecucoes("RUNNING")}>
          <StatTile
            label="em execução"
            value={worker?.active_tasks ?? 0}
            tone={worker?.active_tasks ? "amber" : undefined}
            hint={runningSeries.length > 1 ? <Sparkline data={runningSeries} tone="cyan" width={96} height={24} /> : undefined}
          />
        </ClickableTile>
        <ClickableTile onClick={() => goToExecucoes("SUCCESS")}>
          <StatTile label="concluídas" value={worker?.tasks_completed ?? 0} tone="green" />
        </ClickableTile>
        <ClickableTile onClick={() => goToExecucoes("ERROR")}>
          <StatTile label="falhas" value={worker?.tasks_failed ?? 0} tone={worker?.tasks_failed ? "red" : undefined} />
        </ClickableTile>
      </div>

      {(pendingSeries.length > 1 || runningSeries.length > 1) && (
        <Card
          label="tendência da fila"
          actions={
            <select
              style={selectStyle}
              value={historyHours}
              onChange={(e) => setHistoryHours(Number(e.target.value))}
              aria-label="Janela de tempo"
            >
              {HISTORY_WINDOWS.map((w) => (
                <option key={w.hours} value={w.hours}>
                  {w.label}
                </option>
              ))}
            </select>
          }
        >
          <TimeSeries xLabels={xLabels} lines={[pendingLine, runningLine]} height={160} />
        </Card>
      )}

      <Card
        label="console de telemetria · stream ao vivo"
        actions={
          <>
            <select
              style={selectStyle}
              value={execFilter}
              onChange={(e) => setExecFilter(e.target.value)}
              aria-label="Filtrar por execução"
            >
              <option value="">todas as execuções</option>
              {execOptions.map((id) => (
                <option key={id} value={id}>
                  {id.slice(0, 14)}
                </option>
              ))}
            </select>
            <select
              style={selectStyle}
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              aria-label="Filtrar por tipo de evento"
            >
              <option value="">todos os tipos</option>
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              type="search"
              placeholder="buscar…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Buscar no console"
              style={{ ...selectStyle, width: 140 }}
            />
            <Button
              size="sm"
              variant="subtle"
              icon={paused ? <Play size={13} /> : <Pause size={13} />}
              onClick={() => setPaused((p) => !p)}
            >
              {paused ? "Retomar" : "Pausar"}
            </Button>
            <Button size="sm" variant="subtle" icon={<Trash2 size={13} />} onClick={() => setLines([])}>
              Limpar
            </Button>
          </>
        }
        padded={false}
      >
        <div
          ref={consoleRef}
          style={{
            height: 420,
            overflowY: "auto",
            padding: "var(--sp-3)",
            background: "var(--graphite-950)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--fs-label)",
            lineHeight: 1.7,
          }}
        >
          {filteredLines.length === 0 ? (
            <span style={{ color: "var(--text-lo)" }}>
              {lines.length === 0 ? "aguardando sinal de eventos via websocket…" : "nenhuma linha corresponde aos filtros ativos"}
            </span>
          ) : (
            filteredLines.map((l) => (
              <div key={l.id} style={{ color: l.tone, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                <span style={{ color: "var(--cyan)" }}>[{l.execId.slice(0, 10)}]</span> {l.message}
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
