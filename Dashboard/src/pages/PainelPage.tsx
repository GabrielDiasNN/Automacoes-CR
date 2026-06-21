import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { usePolling } from "../hooks/usePolling";
import { orchestratorApi, type ExecutionSummary } from "../api/orchestrator";
import {
  Annunciator,
  AnnunciatorGrid,
  Button,
  Card,
  ErrorState,
  Loading,
  Mimico,
  Nameplate,
  StatTile,
  StatusTag,
  type QueueLane,
} from "../components/ui";
import { executionTone, healthTone, severityTone, type Tone } from "../lib/status";
import { formatDuration, shortId } from "../lib/format";
import page from "./page.module.css";

function baselineTone(status: string): Tone {
  return healthTone(status);
}

function ExecRow({ ex, onClick }: { ex: ExecutionSummary; onClick: () => void }) {
  const tone = ex.operator_attention_required ? severityTone(ex.operator_severity) : executionTone(ex.status);
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-3)",
        width: "100%",
        textAlign: "left",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        padding: "var(--sp-2) var(--sp-3)",
        cursor: "pointer",
        color: "inherit",
        font: "inherit",
        boxShadow: `inset 3px 0 0 var(--${tone === "grey" ? "graphite-600" : tone})`,
      }}
    >
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)", flexShrink: 0 }}>
        {shortId(ex.id, 12)}
      </span>
      <span
        style={{
          flex: 1,
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontSize: "var(--fs-small)",
          color: "var(--text-hi)",
        }}
      >
        {ex.automation_name ?? `#${ex.automation_id}`}
      </span>
      {ex.operator_attention_required && ex.operator_severity && (
        <StatusTag tone={severityTone(ex.operator_severity)}>{ex.operator_severity}</StatusTag>
      )}
      <StatusTag tone={executionTone(ex.status)} dot pulse={ex.status === "RUNNING"}>
        {ex.status}
      </StatusTag>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)", flexShrink: 0 }}>
        {formatDuration(ex.duration_seconds)}
      </span>
    </button>
  );
}

export function PainelPage() {
  const navigate = useNavigate();
  const { data, loading, error } = usePolling(() => orchestratorApi.getOverview(), 10_000);

  const lanes: QueueLane[] = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, QueueLane>();
    for (const a of data.automations) {
      const group = a.queue_group || "geral";
      const cur = map.get(group) ?? { group, active: 0, pending: 0 };
      cur.active += a.active_execution_count;
      cur.pending += a.pending_count;
      map.set(group, cur);
    }
    return [...map.values()].sort((x, y) => y.active - x.active || y.pending - x.pending).slice(0, 5);
  }, [data]);

  if (loading && !data) {
    return (
      <div className={page.page}>
        <Loading label="lendo telemetria" />
      </div>
    );
  }
  if (error && !data) {
    return (
      <div className={page.page}>
        <ErrorState message={error} />
      </div>
    );
  }
  if (!data) return null;

  const { kpis, worker, health, diagnostics } = {
    kpis: data.kpis,
    worker: data.health.worker,
    health: data.health,
    diagnostics: data.diagnostics,
  };
  const baseline = diagnostics.operational_baseline;
  const running = worker.active_tasks > 0;
  const activeAlarms = baseline.metrics.filter((m) => m.status !== "healthy").length;

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// operação"
        title="Painel"
        actions={
          <StatusTag tone={healthTone(health.status)} dot pulse={health.status === "critical"}>
            sistema {health.status}
          </StatusTag>
        }
      />

      {/* Signature — Mímico Operacional */}
      <Mimico
        sources={kpis.active_automations}
        lanes={lanes}
        worker={{ online: worker.is_alive, active: worker.active_tasks }}
        outcomes={{ success: kpis.success_24h, failures: kpis.errors_24h }}
        running={running}
      />

      {/* Leituras */}
      <div className={page.tiles}>
        <StatTile label="automações ativas" value={kpis.active_automations} />
        <StatTile label="sucesso 24h" value={kpis.success_24h} tone="green" />
        <StatTile label="erros 24h" value={kpis.errors_24h} tone={kpis.errors_24h > 0 ? "red" : undefined} />
        <StatTile label="fila pendente" value={kpis.pending_now} tone={kpis.pending_now > 0 ? "amber" : undefined} />
        <StatTile
          label="próxima janela"
          value={<span style={{ fontSize: "var(--fs-body)" }}>{kpis.next_window ?? "—"}</span>}
          big={false}
        />
      </div>

      <div className={page.two}>
        {/* Anunciador — baseline operacional */}
        <Card label={`anunciador · baseline operacional`} alert={baseline.status === "incident"}>
          {activeAlarms === 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", color: "var(--green)" }}>
              <ShieldCheck size={16} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)" }}>
                nenhum alarme — operação dentro da linha de base
              </span>
            </div>
          ) : (
            <AnnunciatorGrid>
              {baseline.metrics.map((m) => (
                <Annunciator
                  key={m.code}
                  legend={m.label}
                  value={m.current_value ?? undefined}
                  tone={baselineTone(m.status)}
                  active={m.status !== "healthy"}
                  blink={m.status === "incident"}
                />
              ))}
            </AnnunciatorGrid>
          )}
        </Card>

        {/* Worker */}
        <Card label="worker">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
            <StatusTag tone={worker.is_alive ? "green" : "red"} dot pulse={running}>
              {worker.is_alive ? "online" : "offline"}
            </StatusTag>
            <div className={page.tiles}>
              <StatTile label="concluídas" value={worker.tasks_completed} tone="green" />
              <StatTile label="falhas" value={worker.tasks_failed} tone={worker.tasks_failed > 0 ? "red" : undefined} />
            </div>
          </div>
        </Card>
      </div>

      {/* Últimas execuções */}
      <div>
        <div className={page.toolbar} style={{ marginBottom: "var(--sp-2)" }}>
          <span className={page.sectionLabel} style={{ margin: 0 }}>
            últimas execuções
          </span>
          <span className={page.filler} />
          <Button size="sm" variant="subtle" icon={<ArrowRight size={14} />} onClick={() => navigate("/execucoes")}>
            ver todas
          </Button>
        </div>
        <div className={page.list}>
          {data.recent.slice(0, 8).map((ex) => (
            <ExecRow key={ex.id} ex={ex} onClick={() => navigate("/execucoes")} />
          ))}
          {data.recent.length === 0 && (
            <div style={{ padding: "var(--sp-5)", textAlign: "center", fontFamily: "var(--font-mono)", color: "var(--text-lo)", fontSize: "var(--fs-small)" }}>
              nenhuma execução recente
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
