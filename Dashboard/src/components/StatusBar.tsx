import { Activity, Cpu, Layers } from "lucide-react";
import { useDiagnostics } from "../hooks/useDiagnostics";
import { useWebSocket } from "../hooks/useWebSocket";
import { getApiKey } from "../api/client";
import { healthTone, healthLabel, toneVar } from "../lib/status";
import styles from "./StatusBar.module.css";

/** Barra de status global ao vivo — estado do sistema, fila, worker, sinal. */
export function StatusBar() {
  const { health, worker } = useDiagnostics(10_000);
  const key = getApiKey();
  // O hook troca a API Key por um token efêmero antes de abrir o WebSocket,
  // então a chave não aparece mais na URL de handshake.
  const { status: ws } = useWebSocket("/ws/events", key ?? "", {
    enabled: !!key,
  });

  const tone = healthTone(health?.status);
  const wsOnline = ws === "open";

  return (
    <div className={styles.bar}>
      <div className={styles.group}>
        <span
          className={styles.lamp}
          style={{
            background: toneVar[tone],
            animation: health?.status === "critical" ? "blink-alarm 1s steps(1,end) infinite" : undefined,
          }}
        />
        <span className={styles.state} style={{ color: toneVar[tone] }}>
          {healthLabel(health?.status)}
        </span>
      </div>

      <span className={styles.sep} />

      <div className={styles.group} title="Execuções pendentes na fila">
        <Layers size={13} className={styles.ico} />
        <span className={styles.metric}>{health?.pending_tasks ?? "—"}</span>
        <span className={styles.unit}>fila</span>
      </div>

      <div className={styles.group} title="Tarefas em execução / estado do worker">
        <Cpu size={13} className={styles.ico} style={{ color: worker?.is_alive ? "var(--green)" : "var(--red)" }} />
        <span className={styles.metric}>{worker?.active_tasks ?? 0}</span>
        <span className={styles.unit}>{worker?.is_alive ? "worker" : "offline"}</span>
      </div>

      <div className={`${styles.group} ${styles.signal}`} title={`Sinal de eventos: ${ws}`}>
        <Activity size={13} style={{ color: wsOnline ? "var(--cyan)" : "var(--text-lo)" }} />
        <span className={styles.unit} style={{ color: wsOnline ? "var(--cyan)" : "var(--text-lo)" }}>
          {wsOnline ? "sinal" : "sem sinal"}
        </span>
      </div>
    </div>
  );
}
