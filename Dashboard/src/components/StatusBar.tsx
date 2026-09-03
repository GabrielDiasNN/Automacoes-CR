import { Activity, Cpu, Layers } from "lucide-react";
import { useLiveStatus } from "../context/LiveStatusContext";
import { healthTone, healthLabel, toneVar } from "../lib/status";
import styles from "./StatusBar.module.css";

/** Barra de status global ao vivo — estado do sistema, fila, worker, sinal.
 *  Lê tudo do `LiveStatusProvider`: uma só conexão / um só polling (achado nº 15). */
export function StatusBar() {
  const { health, worker, wsStatus } = useLiveStatus();

  const tone = healthTone(health?.status);
  const wsOnline = wsStatus === "open";

  return (
    <div className={styles.bar}>
      <div className={styles.group}>
        <span
          className={styles.lamp}
          style={{
            background: toneVar[tone],
            animation: health?.status === "unhealthy" ? "blink-alarm 1s steps(1,end) infinite" : undefined,
          }}
        />
        {/* aria-live só neste texto (não na barra inteira, que teria o
         *  leitor de tela repetindo os 4 grupos a cada tick de 10s): o que
         *  importa anunciar é a MUDANÇA de estado do sistema, não o polling. */}
        <span className={styles.state} style={{ color: toneVar[tone] }} aria-live="polite">
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

      <div className={`${styles.group} ${styles.signal}`} title={`Sinal de eventos: ${wsStatus}`}>
        <Activity size={13} style={{ color: wsOnline ? "var(--cyan)" : "var(--text-lo)" }} />
        <span className={styles.unit} style={{ color: wsOnline ? "var(--cyan)" : "var(--text-lo)" }}>
          {wsOnline ? "sinal" : "sem sinal"}
        </span>
      </div>
    </div>
  );
}
