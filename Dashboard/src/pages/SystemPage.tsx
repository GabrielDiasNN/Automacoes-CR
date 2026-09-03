import { useMemo, useState } from "react";
import { DatabaseZap, RefreshCw, Trash2, LifeBuoy, RefreshCcw } from "lucide-react";
import { usePolling } from "../hooks/usePolling";
import { orchestratorApi } from "../api/orchestrator";
import {
  Annunciator,
  AnnunciatorGrid,
  Button,
  Card,
  ConfirmModal,
  DescriptionList,
  ErrorState,
  FreshnessTag,
  Gauge,
  KeyValue,
  Loading,
  Nameplate,
  StatTile,
  StatusTag,
} from "../components/ui";
import { TimeSeries, type SeriesLine } from "../components/ui/TimeSeries";
import { useAction } from "../hooks/useAction";
import { healthTone, healthLabel } from "../lib/status";
import { extractTimeBr, formatAge } from "../lib/format";
import page from "./page.module.css";

export function SystemPage() {
  const { data, loading, error, refresh, lastUpdated, rateLimitedUntil, refreshQueued } = usePolling(
    (signal) => orchestratorApi.getOverview(signal),
    15_000,
  );
  const {
    data: history,
    error: historyError,
    lastUpdated: historyUpdated,
  } = usePolling((signal) => orchestratorApi.getHistory(24, signal), 60_000);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const { busyKey: busy, run } = useAction<string>();

  const chart = useMemo(() => {
    const items = history?.items ?? [];
    const xLabels = items.map((p) => extractTimeBr(p.timestamp));
    const queueLines: SeriesLine[] = [
      { label: "pendentes", values: items.map((p) => p.pending_count), tone: "cyan" },
      { label: "em execução", values: items.map((p) => p.running_count), tone: "amber" },
    ];
    const walLine: SeriesLine[] = [{ label: "WAL (MB)", values: items.map((p) => p.wal_size_mb), tone: "cyan" }];
    return { xLabels, queueLines, walLine, count: items.length };
  }, [history]);

  if (loading && !data) {
    return (
      <div className={page.page}>
        <Loading />
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

  const { health } = data;
  const worker = health.worker;
  const baseline = data.diagnostics.operational_baseline;
  const portfolio = data.portfolio;
  const uptime = worker.uptime_seconds ? formatAge(worker.uptime_seconds) : "—";

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// administração"
        title="Sistema"
        actions={
          <div className={page.toolbar}>
            <FreshnessTag
              lastUpdated={lastUpdated}
              error={data && error ? error : null}
              rateLimitedUntil={rateLimitedUntil}
              refreshQueued={refreshQueued}
            />
            <StatusTag tone={healthTone(health.status)} dot pulse={health.status === "unhealthy"}>
              {healthLabel(health.status)}
            </StatusTag>
            <Button size="sm" icon={<RefreshCw size={13} />} onClick={() => void refresh()}>
              Atualizar
            </Button>
          </div>
        }
      />

      {/* Instrumentos */}
      <Card label="instrumentos">
        <div style={{ display: "flex", gap: "var(--sp-5)", flexWrap: "wrap", alignItems: "flex-start" }}>
          <Gauge value={health.cpu_usage} max={100} label="CPU" unit="%" tone={(health.cpu_usage ?? 0) > 85 ? "red" : "cyan"} />
          <Gauge
            value={health.ram_usage_percent}
            max={100}
            label="RAM"
            unit="%"
            tone={(health.ram_usage_percent ?? 0) > 85 ? "red" : "cyan"}
          />
          <div className={page.tiles} style={{ flex: 1, minWidth: 220 }}>
            <StatTile label="WAL SQLite" value={`${health.wal_size_mb?.toFixed(1) ?? "—"}`} hint="MB" />
            <StatTile label="disco" value={`${health.disk_usage_mb?.toFixed(0) ?? "—"}`} hint="MB" />
            <StatTile label="fila pendente" value={health.pending_tasks} tone={health.pending_tasks > 0 ? "amber" : undefined} />
            <StatTile label="banco / scheduler" value={<span style={{ fontSize: "var(--fs-body)", fontFamily: "var(--font-mono)" }}>{health.database} · {health.scheduler}</span>} big={false} />
          </div>
        </div>
      </Card>

      {/* Tendência */}
      <div className={page.split}>
        <Card
          label="tendência · fila (24h)"
          actions={<FreshnessTag lastUpdated={historyUpdated} error={history && historyError ? historyError : null} />}
        >
          {chart.count > 1 ? (
            <TimeSeries xLabels={chart.xLabels} lines={chart.queueLines} height={180} />
          ) : (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--text-lo)" }}>
              coletando histórico…
            </span>
          )}
        </Card>
        <Card
          label="tendência · WAL (24h)"
          actions={<FreshnessTag lastUpdated={historyUpdated} error={history && historyError ? historyError : null} />}
        >
          {chart.count > 1 ? (
            <TimeSeries xLabels={chart.xLabels} lines={chart.walLine} height={180} />
          ) : (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--text-lo)" }}>
              coletando histórico…
            </span>
          )}
        </Card>
      </div>

      {/* Baseline + Worker */}
      <div className={page.two}>
        <Card label="anunciador · baseline operacional" alert={baseline.status === "incident"}>
          <AnnunciatorGrid>
            {baseline.metrics.map((m) => (
              <Annunciator
                key={m.code}
                legend={m.label}
                value={m.current_value ?? undefined}
                tone={healthTone(m.status)}
                active={m.status !== "healthy"}
                blink={m.status === "incident"}
                statusLabel={healthLabel(m.status)}
              />
            ))}
          </AnnunciatorGrid>
        </Card>

        <Card label="worker">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
            <StatusTag tone={worker.is_alive ? "green" : "red"} dot pulse={worker.active_tasks > 0}>
              {worker.is_alive ? "online" : "offline"}
            </StatusTag>
            <DescriptionList>
              <KeyValue k="PID" v={String(worker.pid ?? "—")} />
              <KeyValue k="Uptime" v={uptime} />
              <KeyValue k="Concluídas" v={String(worker.tasks_completed)} />
              <KeyValue k="Falhas" v={String(worker.tasks_failed)} />
              <KeyValue k="Ativas" v={String(worker.active_tasks)} />
              <KeyValue k="Versão" v={worker.version} />
            </DescriptionList>
            {!worker.is_alive && (
              <Button
                variant="primary"
                icon={<LifeBuoy size={13} />}
                disabled={busy === "recover"}
                onClick={() => void run("recover", orchestratorApi.recoverWorker, { onDone: refresh })}
              >
                Recuperar worker
              </Button>
            )}
          </div>
        </Card>
      </div>

      {/* Portfólio */}
      {portfolio && (
        <Card label="portfólio · governança" alert={portfolio.status === "incident"}>
          <div className={page.tiles}>
            <StatTile label="itens" value={portfolio.total_items} big />
            <StatTile label="governados" value={portfolio.governed_items} tone="green" />
            <StatTile label="drift" value={portfolio.drift_items} tone={portfolio.drift_items > 0 ? "amber" : undefined} />
            <StatTile label="docs ausentes" value={portfolio.docs_missing_items} tone={portfolio.docs_missing_items > 0 ? "amber" : undefined} />
            <StatTile label="sla violado" value={portfolio.sla_breached_items} tone={portfolio.sla_breached_items > 0 ? "red" : undefined} />
          </div>
          {portfolio.top_issue && (
            <p style={{ marginTop: "var(--sp-3)", fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
              {portfolio.top_issue}
              {portfolio.recommended_action ? ` — ${portfolio.recommended_action}` : ""}
            </p>
          )}
        </Card>
      )}

      {/* Ações */}
      <Card label="manutenção">
        <div className={page.toolbar}>
          <Button icon={<DatabaseZap size={14} />} disabled={busy === "ckpt"} onClick={() => void run("ckpt", orchestratorApi.runCheckpoint, { onDone: refresh })}>
            WAL Checkpoint
          </Button>
          <Button icon={<RefreshCcw size={14} />} disabled={busy === "sched"} onClick={() => void run("sched", orchestratorApi.reloadScheduler, { onDone: refresh })}>
            Recarregar agendador
          </Button>
          <Button variant="danger" icon={<Trash2 size={14} />} onClick={() => setConfirmPurge(true)}>
            Purge execuções
          </Button>
        </div>
      </Card>

      <ConfirmModal
        open={confirmPurge}
        title="Purge de execuções"
        message="Remover execuções antigas conforme política de retenção? Esta ação não pode ser desfeita."
        confirmLabel="Executar purge"
        danger
        onConfirm={() => {
          setConfirmPurge(false);
          void run("purge", orchestratorApi.runPurge, { onDone: refresh });
        }}
        onCancel={() => setConfirmPurge(false)}
      />
    </div>
  );
}

