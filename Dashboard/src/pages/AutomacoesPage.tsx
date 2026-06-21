import { useCallback, useEffect, useState } from "react";
import { Pause, Play, RefreshCw, Zap } from "lucide-react";
import { orchestratorApi, type Automation } from "../api/orchestrator";
import { Button, Card, ErrorState, Loading, Nameplate, RatioBar, StatusTag, useToast } from "../components/ui";
import { criticalityTone, executionTone } from "../lib/status";
import { formatDuration } from "../lib/format";
import page from "./page.module.css";
import styles from "./AutomacoesPage.module.css";

export function AutomacoesPage() {
  const toast = useToast();
  const [items, setItems] = useState<Automation[]>([]);
  const [crit, setCrit] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await orchestratorApi.listAllAutomations();
      setItems(list);
      setErr(null);
      // criticidade é do catálogo (portfólio) — best-effort
      orchestratorApi
        .getPortfolioHealth()
        .then((p) => {
          const m: Record<number, string> = {};
          for (const it of p.items) if (it.automation_id != null) m[it.automation_id] = it.criticality;
          setCrit(m);
        })
        .catch(() => {});
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, [load]);

  const act = useCallback(
    async (id: number, fn: () => Promise<{ message: string }>, okMsg: string) => {
      setBusy(id);
      try {
        await fn();
        toast(okMsg, "cyan");
        await load();
      } catch (e) {
        toast(e instanceof Error ? e.message : String(e), "red");
      } finally {
        setBusy(null);
      }
    },
    [toast, load],
  );

  if (loading && items.length === 0) {
    return (
      <div className={page.page}>
        <Loading />
      </div>
    );
  }

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// administração"
        title="Automações"
        actions={
          <Button size="sm" icon={<RefreshCw size={13} />} onClick={load}>
            Atualizar
          </Button>
        }
      />

      {err && items.length === 0 ? (
        <ErrorState message={err} />
      ) : (
        <div className={styles.grid}>
          {items.map((a) => {
            const total24h = a.success_24h + a.failures_24h;
            return (
              <Card key={a.id} alert={a.last_status === "ERROR" || a.last_status === "TIMEOUT"}>
                <div className={styles.card}>
                  <div className={styles.top}>
                    <span
                      className={styles.lamp}
                      style={{ background: `var(--${a.enabled ? "green" : "graphite-600"})` }}
                    />
                    <div className={styles.titleWrap}>
                      <span className={styles.name}>{a.name}</span>
                      {a.description && <span className={styles.desc}>{a.description}</span>}
                    </div>
                  </div>

                  <div className={styles.tags}>
                    {crit[a.id] && <StatusTag tone={criticalityTone(crit[a.id])}>{crit[a.id]}</StatusTag>}
                    {a.last_status && <StatusTag tone={executionTone(a.last_status)} dot>{a.last_status}</StatusTag>}
                    {!a.enabled && <StatusTag tone="grey">pausada</StatusTag>}
                    {a.test_mode && <StatusTag tone="blue">sandbox</StatusTag>}
                    {a.queue_group && <span className={styles.meta}>fila: {a.queue_group}</span>}
                  </div>

                  <dl className={styles.metrics}>
                    <div>
                      <dt className={styles.mLabel}>sucesso / falha 24h</dt>
                      <dd className={styles.mVal}>
                        <span style={{ color: "var(--green)" }}>{a.success_24h}</span>
                        <span className={styles.slash}>/</span>
                        <span style={{ color: a.failures_24h ? "var(--red)" : "var(--text-lo)" }}>{a.failures_24h}</span>
                      </dd>
                      {total24h > 0 && (
                        <div style={{ marginTop: 4 }}>
                          <RatioBar success={a.success_24h} failures={a.failures_24h} />
                        </div>
                      )}
                    </div>
                    <div>
                      <dt className={styles.mLabel}>sla</dt>
                      <dd className={styles.mVal}>{a.sla_minutes ? `${a.sla_minutes}min` : "—"}</dd>
                    </div>
                    <div>
                      <dt className={styles.mLabel}>última duração</dt>
                      <dd className={styles.mVal}>{formatDuration(a.last_execution_duration_seconds)}</dd>
                    </div>
                    <div>
                      <dt className={styles.mLabel}>próxima janela</dt>
                      <dd className={styles.mMeta}>{a.next_run ?? a.schedule_summary ?? "manual"}</dd>
                    </div>
                  </dl>

                  <div className={styles.actions}>
                    {a.enabled ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Pause size={13} />}
                        disabled={busy === a.id}
                        onClick={() => act(a.id, () => orchestratorApi.pauseAutomation(a.id), `${a.name} pausada`)}
                      >
                        Pausar
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Play size={13} />}
                        disabled={busy === a.id}
                        onClick={() => act(a.id, () => orchestratorApi.resumeAutomation(a.id), `${a.name} retomada`)}
                      >
                        Retomar
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<Zap size={13} />}
                      disabled={busy === a.id || !a.enabled}
                      onClick={() =>
                        act(a.id, () => orchestratorApi.startAutomation(a.id).then((r) => ({ message: r.message })), `${a.name} disparada`)
                      }
                    >
                      Disparar
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })}
          {items.length === 0 && (
            <span style={{ color: "var(--text-lo)", fontFamily: "var(--font-mono)" }}>nenhuma automação cadastrada.</span>
          )}
        </div>
      )}
    </div>
  );
}
