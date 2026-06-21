import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, Trash2 } from "lucide-react";
import { useDiagnostics } from "../hooks/useDiagnostics";
import { useWebSocket } from "../hooks/useWebSocket";
import { getApiKey } from "../api/client";
import { Button, Card, Nameplate, StatTile, StatusTag } from "../components/ui";
import { healthTone, healthLabel } from "../lib/status";
import page from "./page.module.css";

interface LogLine {
  id: number;
  exec_id: string;
  message: string;
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

export function ObservabilidadePage() {
  const { health, worker } = useDiagnostics(10_000);
  const [lines, setLines] = useState<LogLine[]>([]);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const idRef = useRef(0);
  const consoleRef = useRef<HTMLDivElement>(null);

  const key = getApiKey();
  const handleMessage = useCallback((evt: MessageEvent) => {
    if (pausedRef.current) return;
    try {
      const data = JSON.parse(evt.data as string);
      if (Array.isArray(data.logs)) {
        setLines((prev) =>
          [
            ...prev,
            ...data.logs.map((l: { exec_id: string; message: string }) => ({
              id: (idRef.current += 1),
              exec_id: l.exec_id ?? "—",
              message: l.message ?? "",
            })),
          ].slice(-300),
        );
      }
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

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// operação"
        title="Observabilidade"
        actions={
          <StatusTag tone={wsTone} dot pulse={status === "connecting"}>
            sinal {status === "open" ? "ativo" : status}
          </StatusTag>
        }
      />

      <div className={page.tiles}>
        <StatTile
          label="status geral"
          value={<span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-body)", textTransform: "uppercase" }}>{healthLabel(health?.status)}</span>}
          tone={healthTone(health?.status)}
          big={false}
        />
        <StatTile label="pendentes" value={health?.pending_tasks ?? 0} tone={health && health.pending_tasks > 0 ? "amber" : undefined} />
        <StatTile label="em execução" value={worker?.active_tasks ?? 0} tone={worker?.active_tasks ? "amber" : undefined} />
        <StatTile label="concluídas" value={worker?.tasks_completed ?? 0} tone="green" />
        <StatTile label="falhas" value={worker?.tasks_failed ?? 0} tone={worker?.tasks_failed ? "red" : undefined} />
      </div>

      <Card
        label="console de telemetria · stream ao vivo"
        actions={
          <>
            <Button size="sm" variant="subtle" icon={paused ? <Play size={13} /> : <Pause size={13} />} onClick={() => setPaused((p) => !p)}>
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
          {lines.length === 0 ? (
            <span style={{ color: "var(--text-lo)" }}>aguardando sinal de eventos via websocket…</span>
          ) : (
            lines.map((l) => (
              <div key={l.id} style={{ color: lineColor(l.message), whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                <span style={{ color: "var(--cyan)" }}>[{l.exec_id.slice(0, 10)}]</span> {l.message}
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
