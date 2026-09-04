import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pause, Play, Trash2 } from "lucide-react";
import { useLiveEvents, useLiveStatus } from "../context/LiveStatusContext";
import { usePolling } from "../hooks/usePolling";
import { orchestratorApi, type SystemHistory, type SystemMetricsDaily } from "../api/orchestrator";
import {
  Button,
  Card,
  FreshnessTag,
  Nameplate,
  Select,
  Sparkline,
  StatTile,
  StatusTag,
} from "../components/ui";
import { TimeSeries, type SeriesLine } from "../components/ui/TimeSeries";
import selectStyles from "../components/ui/Select.module.css";
import { healthTone, healthLabel, type Tone } from "../lib/status";
import { extractTimeBr } from "../lib/format";
import page from "./page.module.css";

interface LogLine {
  id: number;
  execId: string;
  type: string;
  message: string;
  tone: string;
}

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
  const { health, worker, wsStatus: status } = useLiveStatus();
  const [lines, setLines] = useState<LogLine[]>([]);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const idRef = useRef(0);
  const consoleRef = useRef<HTMLDivElement>(null);

  const [execFilter, setExecFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [q, setQ] = useState("");

  // Buffer + flush em requestAnimationFrame: sob rajada de eventos, várias
  // mensagens no mesmo frame viram UM `setLines` (uma cópia O(n), um re-render)
  // em vez de uma por mensagem (achado nº 32, Onda 5).
  const lineBufferRef = useRef<LogLine[]>([]);
  const flushHandleRef = useRef<number | null>(null);

  const flushLines = useCallback(() => {
    flushHandleRef.current = null;
    const buffered = lineBufferRef.current;
    if (buffered.length === 0) return;
    lineBufferRef.current = [];
    setLines((prev) => [...prev, ...buffered].slice(-300));
  }, []);

  const clearLines = useCallback(() => {
    lineBufferRef.current = [];
    setLines([]);
  }, []);

  useEffect(() => {
    return () => {
      if (flushHandleRef.current != null) cancelAnimationFrame(flushHandleRef.current);
    };
  }, []);

  const handleMessage = useCallback(
    (evt: MessageEvent) => {
      if (pausedRef.current) return;
      try {
        const parsed = JSON.parse(evt.data as string) as { type?: string; data?: Record<string, unknown> };
        const type = parsed.type ?? "UNKNOWN";
        const data = parsed.data ?? {};
        const execId = String(data.exec_id ?? "—");
        const { message, tone } = describeEvent(type, data);
        lineBufferRef.current.push({ id: (idRef.current += 1), execId, type, message, tone });
        if (flushHandleRef.current == null) {
          flushHandleRef.current = requestAnimationFrame(flushLines);
        }
      } catch {
        // mensagem não-JSON ignorada
      }
    },
    [flushLines],
  );

  // Uma única conexão `/ws/events` vive no LiveStatusProvider; a página só se
  // inscreve no fan-out de mensagens (achado nº 15).
  useLiveEvents(handleMessage);

  // Só reposiciona quando ENTRA linha nova (id do último item, monotônico) —
  // não a cada troca de identidade do array. `lines.length` não serve: fica
  // fixo em 300 depois do teto e o auto-scroll congelaria.
  const lastLine = lines[lines.length - 1];
  const lastLineId = lastLine ? lastLine.id : 0;
  useEffect(() => {
    if (!paused) consoleRef.current?.scrollTo({ top: consoleRef.current.scrollHeight });
  }, [lastLineId, paused]);

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
  const fetchHistory = useCallback(
    (signal?: AbortSignal) => orchestratorApi.getHistory(historyHours, signal),
    [historyHours],
  );
  const {
    data: history,
    error: historyError,
    lastUpdated: historyUpdated,
  } = usePolling<SystemHistory>(fetchHistory, 60_000, [historyHours]);

  // useMemo: essas transformações rodavam a cada render, inclusive a cada
  // mensagem de WebSocket (que atualiza `lines`, sem relação com o
  // histórico) — sob rajada de eventos, recomputava map/filter/reduce à toa
  // a cada linha de log recebida (achado nº 31, Onda 5).
  const historyItems = useMemo(() => history?.items ?? [], [history]);
  const { xLabels, pendingSeries, runningSeries, queueLines } = useMemo(() => {
    const xLabels = historyItems.map((p) => extractTimeBr(p.timestamp));
    const pendingSeries = historyItems.map((p) => p.pending_count);
    const runningSeries = historyItems.map((p) => p.running_count);
    const pendingLine: SeriesLine = { label: "pendentes", values: pendingSeries, tone: "amber" };
    const runningLine: SeriesLine = { label: "em execução", values: runningSeries, tone: "cyan" };
    // `queueLines` memoizado aqui — o <TimeSeries memo> só ignora re-render do
    // pai (cada mensagem de WS) se `lines` vier com referência estável.
    return { xLabels, pendingSeries, runningSeries, queueLines: [pendingLine, runningLine] };
  }, [historyItems]);

  // `void`: em react-router 7 `navigate` devolve Promise; o handler de clique
  // espera `() => void` (gate `no-misused-promises`).
  const goToExecucoes = useCallback(
    (execStatus: string) => void navigate(`/execucoes?status=${execStatus}`),
    [navigate],
  );

  const fetchDailyMetrics = useCallback(
    (signal?: AbortSignal) => orchestratorApi.getSystemMetricsDaily(14, signal),
    [],
  );
  const {
    data: dailyMetrics,
    error: dailyError,
    lastUpdated: dailyUpdated,
  } = usePolling<SystemMetricsDaily>(fetchDailyMetrics, 120_000);

  const dailyItems = useMemo(() => dailyMetrics?.items ?? [], [dailyMetrics]);
  const { dailyLabels, successRateLines, avgDurationLines } = useMemo(() => {
    const dailyLabels = dailyItems.map((d) => d.date.slice(5));
    const successRateLine: SeriesLine = {
      label: "taxa de sucesso %",
      values: dailyItems.map((d) => d.success_rate_pct),
      tone: "green",
    };
    const avgDurationLine: SeriesLine = {
      label: "duração média (s)",
      values: dailyItems.map((d) => d.avg_duration_seconds),
      tone: "blue",
    };
    return { dailyLabels, successRateLines: [successRateLine], avgDurationLines: [avgDurationLine] };
  }, [dailyItems]);

  const cutoff7d = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  }, []);
  const { errorsTrendHint, errorsTrendTone, currentWeekErrors } = useMemo(() => {
    const currentWeekErrors = dailyItems.filter((d) => d.date >= cutoff7d).reduce((sum, d) => sum + d.errors, 0);
    const previousWeekErrors = dailyItems.filter((d) => d.date < cutoff7d).reduce((sum, d) => sum + d.errors, 0);
    const errorsTrendHint =
      previousWeekErrors > 0
        ? `${currentWeekErrors >= previousWeekErrors ? "+" : ""}${Math.round(((currentWeekErrors - previousWeekErrors) / previousWeekErrors) * 100)}% vs 7d anteriores`
        : "sem base de comparação";
    const errorsTrendTone: Tone | undefined =
      currentWeekErrors > previousWeekErrors ? "red" : currentWeekErrors < previousWeekErrors ? "green" : undefined;
    return { errorsTrendHint, errorsTrendTone, currentWeekErrors };
  }, [dailyItems, cutoff7d]);

  // `value`/`hint` em JSX são recriados a cada render — sem memoizar, o
  // <StatTile memo> re-renderiza a cada frame de log mesmo com os dados iguais.
  const statusValue = useMemo(
    () => (
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-body)", textTransform: "uppercase" }}>
        {healthLabel(health?.status)}
      </span>
    ),
    [health?.status],
  );
  const pendingHint = useMemo(
    () => (pendingSeries.length > 1 ? <Sparkline data={pendingSeries} tone="amber" width={96} height={24} /> : undefined),
    [pendingSeries],
  );
  const runningHint = useMemo(
    () => (runningSeries.length > 1 ? <Sparkline data={runningSeries} tone="cyan" width={96} height={24} /> : undefined),
    [runningSeries],
  );

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
        <StatTile label="status geral" value={statusValue} tone={healthTone(health?.status)} big={false} />
        <ClickableTile onClick={() => goToExecucoes("PENDING")}>
          <StatTile
            label="pendentes"
            value={health?.pending_tasks ?? 0}
            tone={health && health.pending_tasks > 0 ? "amber" : undefined}
            hint={pendingHint}
          />
        </ClickableTile>
        <ClickableTile onClick={() => goToExecucoes("RUNNING")}>
          <StatTile
            label="em execução"
            value={worker?.active_tasks ?? 0}
            tone={worker?.active_tasks ? "amber" : undefined}
            hint={runningHint}
          />
        </ClickableTile>
        <ClickableTile onClick={() => goToExecucoes("SUCCESS")}>
          <StatTile label="concluídas" value={worker?.tasks_completed ?? 0} tone="green" />
        </ClickableTile>
        <ClickableTile onClick={() => goToExecucoes("ERROR")}>
          <StatTile label="falhas" value={worker?.tasks_failed ?? 0} tone={worker?.tasks_failed ? "red" : undefined} />
        </ClickableTile>
        <StatTile label="falhas (7d)" value={currentWeekErrors} tone={errorsTrendTone} hint={errorsTrendHint} />
      </div>

      {(pendingSeries.length > 1 || runningSeries.length > 1) && (
        <Card
          label="tendência da fila"
          actions={
            <div className={page.toolbar}>
              <FreshnessTag lastUpdated={historyUpdated} error={history && historyError ? historyError : null} />
              <Select
                value={historyHours}
                onChange={(e) => setHistoryHours(Number(e.target.value))}
                aria-label="Janela de tempo"
              >
                {HISTORY_WINDOWS.map((w) => (
                  <option key={w.hours} value={w.hours}>
                    {w.label}
                  </option>
                ))}
              </Select>
            </div>
          }
        >
          <TimeSeries xLabels={xLabels} lines={queueLines} height={160} />
        </Card>
      )}

      {dailyItems.length > 1 && (
        <div className={page.split}>
          <Card
            label="taxa de sucesso · 14 dias"
            actions={<FreshnessTag lastUpdated={dailyUpdated} error={dailyMetrics && dailyError ? dailyError : null} />}
          >
            <TimeSeries xLabels={dailyLabels} lines={successRateLines} height={160} />
          </Card>
          <Card label="duração média (s) · 14 dias">
            <TimeSeries xLabels={dailyLabels} lines={avgDurationLines} height={160} />
          </Card>
        </div>
      )}

      <Card
        label="console de telemetria · stream ao vivo"
        actions={
          <>
            <Select
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
            </Select>
            <Select
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
            </Select>
            <input
              type="search"
              placeholder="buscar…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Buscar no console"
              className={selectStyles.select}
              style={{ width: 140 }}
            />
            <Button
              size="sm"
              variant="subtle"
              icon={paused ? <Play size={13} /> : <Pause size={13} />}
              onClick={() => setPaused((p) => !p)}
            >
              {paused ? "Retomar" : "Pausar"}
            </Button>
            <Button size="sm" variant="subtle" icon={<Trash2 size={13} />} onClick={clearLines}>
              Limpar
            </Button>
          </>
        }
        padded={false}
      >
        <div
          ref={consoleRef}
          // `role="log"`: live region própria para stream de mensagens tipo
          // console/chat — sem isso o conteúdo mudava sozinho sob o cursor
          // sem nenhum anúncio a leitor de tela. `aria-relevant="additions"`
          // evita que "Limpar" (esvazia a lista) dispare um anúncio de
          // remoção em massa.
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          style={{
            height: 420,
            overflowY: "auto",
            padding: "var(--sp-3)",
            background: "var(--surface-sunken)",
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
