import { useMemo, useState } from "react";
import { BellRing, DatabaseZap, PauseCircle, PlayCircle, RefreshCw, Trash2, LifeBuoy, RefreshCcw } from "lucide-react";
import { usePolling } from "../hooks/usePolling";
import { writeCache } from "../lib/resourceCache";
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
    [],
    { cacheKey: "overview", onData: (ov) => writeCache("health", ov.health) },
  );
  const {
    data: history,
    error: historyError,
    lastUpdated: historyUpdated,
  } = usePolling((signal) => orchestratorApi.getHistory(24, signal), 60_000);
  // Versão/uptime do processo Orchestrator (não do worker). Polling longo — o
  // rodapé global de versão fica para a Onda 4 (mudaria o chrome das 4 telas
  // de baseline de screenshot).
  const { data: version } = usePolling(orchestratorApi.getVersion, 60_000);
  const { data: orchestratorUptime } = usePolling(orchestratorApi.getUptime, 60_000);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [confirmRecover, setConfirmRecover] = useState(false);
  const [confirmEmergency, setConfirmEmergency] = useState<"pause" | "resume" | null>(null);
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
            <div className={page.toolbar}>
              <Button
                variant="ghost"
                size="sm"
                icon={<BellRing size={13} />}
                disabled={busy === "wakeup"}
                // Benigno: só cutuca o worker a checar a fila agora. Idempotente,
                // sem ConfirmModal.
                onClick={() =>
                  void run("wakeup", orchestratorApi.wakeupWorker, { onDone: refresh, invalidate: "overview" })
                }
              >
                Acordar worker
              </Button>
              {!worker.is_alive && (
                <Button
                  variant="primary"
                  size="sm"
                  icon={<LifeBuoy size={13} />}
                  disabled={busy === "recover"}
                  onClick={() => setConfirmRecover(true)}
                >
                  Recuperar worker
                </Button>
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* Runtime (versão/uptime do processo Orchestrator) */}
      <Card label="runtime">
        <DescriptionList>
          <KeyValue k="Versão" v={version?.version ?? "—"} />
          <KeyValue k="Schema" v={version?.schema_version ?? "—"} />
          <KeyValue k="Contrato" v={version?.contract_version ?? "—"} />
          <KeyValue k="Python" v={version?.python_version ?? "—"} />
          <KeyValue
            k="Uptime"
            v={orchestratorUptime?.uptime_human ?? (version ? formatAge(version.uptime_seconds) : "—")}
          />
          <KeyValue k="Iniciado" v={version?.started_at ?? "—"} />
          <KeyValue k="Workers" v={version ? String(version.max_workers) : "—"} />
        </DescriptionList>
      </Card>

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

      {/* Controle de emergência (alcance global) */}
      <Card label="controle de emergência" alert>
        <p style={{ margin: "0 0 var(--sp-3)", fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
          "Pausar todas" desliga o agendamento de todas as automações registradas. As execuções em andamento
          continuam; nenhuma nova é agendada até "Retomar todas".
        </p>
        <div className={page.toolbar}>
          <Button
            variant="danger"
            icon={<PauseCircle size={14} />}
            disabled={busy === "pause-all"}
            onClick={() => setConfirmEmergency("pause")}
          >
            Pausar todas as automações
          </Button>
          <Button
            variant="ghost"
            icon={<PlayCircle size={14} />}
            disabled={busy === "resume-all"}
            onClick={() => setConfirmEmergency("resume")}
          >
            Retomar todas
          </Button>
        </div>
      </Card>

      {/* Ações */}
      <Card label="manutenção">
        <div className={page.toolbar}>
          <Button icon={<DatabaseZap size={14} />} disabled={busy === "ckpt"} onClick={() => void run("ckpt", orchestratorApi.runCheckpoint, { onDone: refresh, invalidate: "overview" })}>
            WAL Checkpoint
          </Button>
          <Button icon={<RefreshCcw size={14} />} disabled={busy === "sched"} onClick={() => void run("sched", orchestratorApi.reloadScheduler, { onDone: refresh, invalidate: "overview" })}>
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
          void run("purge", orchestratorApi.runPurge, { onDone: refresh, invalidate: "overview" });
        }}
        onCancel={() => setConfirmPurge(false)}
      />

      <ConfirmModal
        open={confirmEmergency !== null}
        title={confirmEmergency === "pause" ? "Pausar todas as automações" : "Retomar todas as automações"}
        message={
          confirmEmergency === "pause"
            ? "Pausa TODAS as automações registradas. Execuções em andamento continuam; nenhuma nova é agendada até 'Retomar tudo'. Confirmar?"
            : "Reativa o agendamento de TODAS as automações registradas. Confirmar?"
        }
        confirmLabel={confirmEmergency === "pause" ? "Pausar tudo" : "Retomar tudo"}
        danger={confirmEmergency === "pause"}
        onConfirm={() => {
          const kind = confirmEmergency;
          setConfirmEmergency(null);
          if (kind === "pause") {
            void run("pause-all", orchestratorApi.pauseAll, { onDone: refresh, invalidate: "overview" });
          } else if (kind === "resume") {
            void run("resume-all", orchestratorApi.resumeAll, { onDone: refresh, invalidate: "overview" });
          }
        }}
        onCancel={() => setConfirmEmergency(null)}
      />

      <ConfirmModal
        open={confirmRecover}
        title="Recuperar worker"
        message="Recuperar o worker force-reseta o estado de execução do processo (relança a recuperação canônica do Orchestrator). Confirmar?"
        confirmLabel="Recuperar worker"
        danger
        onConfirm={() => {
          setConfirmRecover(false);
          void run("recover", orchestratorApi.recoverWorker, { onDone: refresh, invalidate: "overview" });
        }}
        onCancel={() => setConfirmRecover(false)}
      />
    </div>
  );
}

