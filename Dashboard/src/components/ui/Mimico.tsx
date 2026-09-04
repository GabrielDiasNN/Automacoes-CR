import { Cpu, GitBranch, Inbox, ListChecks } from "lucide-react";
import { RatioBar } from "./MiniViz";
import { Lamp } from "./Lamp";
import styles from "./Mimico.module.css";

export interface QueueLane {
  group: string;
  active: number;
  pending: number;
}

interface MimicoProps {
  sources: number;
  lanes: QueueLane[];
  worker: { online: boolean; active: number };
  outcomes: { success: number; failures: number };
  running: boolean;
}

function Pipe({ running }: { running: boolean }) {
  return <div className={`${styles.pipe} ${running ? styles.flowing : ""}`} aria-hidden="true" />;
}

/** Mímico Operacional — painel sinótico vivo da orquestração.
 *  fontes → filas (serializadas) → worker → resultado 24h. */
export function Mimico({ sources, lanes, worker, outcomes, running }: MimicoProps) {
  // `role="group"` (não "img"): o painel É composto de texto/números reais
  // (fontes, filas, worker, resultado 24h) — "img" podaria tudo isso da
  // árvore de acessibilidade e o leitor de tela só ouviria o aria-label
  // genérico, perdendo exatamente os dados que o painel existe para mostrar.
  // "group" preserva os filhos e ainda nomeia o conjunto.
  return (
    <div className={styles.synoptic} role="group" aria-label="Mímico operacional da orquestração">
      {/* Fontes */}
      <div className={styles.node}>
        <div className={styles.nodeLabel}>
          <Inbox size={12} /> fontes
        </div>
        <div className={styles.reading}>{sources}</div>
        <div className={styles.unit}>automações ativas</div>
      </div>

      <Pipe running={running} />

      {/* Filas (lanes) */}
      <div className={`${styles.node} ${styles.nodeWide}`}>
        <div className={styles.nodeLabel}>
          <GitBranch size={12} /> filas
        </div>
        <div className={styles.lanes}>
          {lanes.length === 0 && <div className={styles.laneEmpty}>sem fila ativa</div>}
          {lanes.map((l) => {
            const busy = l.active > 0;
            return (
              <div key={l.group} className={styles.lane}>
                <Lamp size={8} shape="square" color={busy ? "var(--amber)" : "var(--track-strong)"} />
                <span className={styles.laneName}>{l.group}</span>
                <span className={styles.laneCount}>
                  {l.active}▸ <span className={styles.lanePending}>{l.pending}⏳</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <Pipe running={running} />

      {/* Worker */}
      <div className={styles.node}>
        <div className={styles.nodeLabel}>
          <Cpu size={12} /> worker
        </div>
        <div className={styles.workerRow}>
          {/* sem pulseGlow: preserva o fallback --amber-glow do keyframe
           *  pulse-ring, igual ao comportamento original. */}
          <Lamp size={10} color={worker.online ? "var(--green)" : "var(--red)"} pulse={running} />
          <span className={styles.reading} style={{ color: worker.online ? "var(--text-hi)" : "var(--red)" }}>
            {worker.active}
          </span>
        </div>
        <div className={styles.unit}>{worker.online ? "em execução" : "offline"}</div>
      </div>

      <Pipe running={running} />

      {/* Resultado */}
      <div className={styles.node}>
        <div className={styles.nodeLabel}>
          <ListChecks size={12} /> resultado 24h
        </div>
        <div className={styles.outcome}>
          <span style={{ color: "var(--green)" }}>{outcomes.success}</span>
          <span className={styles.slash}>/</span>
          <span style={{ color: outcomes.failures > 0 ? "var(--red)" : "var(--text-lo)" }}>{outcomes.failures}</span>
        </div>
        <div className={styles.ratio}>
          <RatioBar success={outcomes.success} failures={outcomes.failures} />
        </div>
      </div>
    </div>
  );
}
