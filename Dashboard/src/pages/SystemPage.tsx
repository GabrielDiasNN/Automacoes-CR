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
  ErrorState,
  Gauge,
  Loading,
  Nameplate,
  StatTile,
  StatusTag,
  TimeSeries,
  useToast,
  type SeriesLine,
} from "../components/ui";
import { healthTone, healthLabel } from "../lib/status";
import { formatAge } from "../lib/format";
import page from "./page.module.css";

export function SystemPage() {
  const toast = useToast();
  const { data, loading, error, refresh, lastUpdated } = usePolling(
    (signal) => orchestratorApi.getOverview(signal),
    15_000,
  );
  const { data: history } = usePolling((signal) => orchestratorApi.getHistory(24, signal), 60_000);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (kind: string, fn: () => Promise<{ message: string }>) => {
    setBusy(kind);
    try {
      const r = await fn();
      toast(r.message, "cyan");
      refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "red");
    } finally {
      setBusy(null);
    }
  };

  const chart = useMemo(() => {
    const items = history?.items ?? [];
    const xLabels = items.map((p) => (p.timestamp.split(" ")[1] ?? p.timestamp).slice(0, 5));
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
            {lastUpdated && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)" }}>
                {lastUpdated.toLocaleTimeString("pt-BR")}
              </span>
            )}
            <StatusTag tone={healthTone(health.status)} dot pulse={health.status === "critical"}>
              {healthLabel(health.status)}
            </StatusTag>
            <Button size="sm" icon={<RefreshCw size={13} />} onClick={refresh}>
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
        <Card label="tendência · fila (24h)">
          {chart.count > 1 ? (
            <TimeSeries xLabels={chart.xLabels} lines={chart.queueLines} height={180} />
          ) : (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--text-lo)" }}>
              coletando histórico…
            </span>
          )}
        </Card>
        <Card label="tendência · WAL (24h)">
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
              />
            ))}
          </AnnunciatorGrid>
        </Card>

        <Card label="worker">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
            <StatusTag tone={worker.is_alive ? "green" : "red"} dot pulse={worker.active_tasks > 0}>
              {worker.is_alive ? "online" : "offline"}
            </StatusTag>
            <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px var(--sp-3)", margin: 0 }}>
              <KV k="PID" v={String(worker.pid ?? "—")} />
              <KV k="Uptime" v={uptime} />
              <KV k="Concluídas" v={String(worker.tasks_completed)} />
              <KV k="Falhas" v={String(worker.tasks_failed)} />
              <KV k="Ativas" v={String(worker.active_tasks)} />
              <KV k="Versão" v={worker.version} />
            </dl>
            {!worker.is_alive && (
              <Button
                variant="primary"
                icon={<LifeBuoy size={13} />}
                disabled={busy === "recover"}
                onClick={() => run("recover", orchestratorApi.recoverWorker)}
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
          <Button icon={<DatabaseZap size={14} />} disabled={busy === "ckpt"} onClick={() => run("ckpt", orchestratorApi.runCheckpoint)}>
            WAL Checkpoint
          </Button>
          <Button icon={<RefreshCcw size={14} />} disabled={busy === "sched"} onClick={() => run("sched", orchestratorApi.reloadScheduler)}>
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
          run("purge", orchestratorApi.runPurge);
        }}
        onCancel={() => setConfirmPurge(false)}
      />
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--fs-label)",
          color: "var(--text-lo)",
          textTransform: "uppercase",
          letterSpacing: "var(--track-mid)",
        }}
      >
        {k}
      </dt>
      <dd style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>{v}</dd>
    </>
  );
}
