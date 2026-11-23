import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Bell, ClipboardList, ServerCrash, X } from "lucide-react";
import {
  orchestratorApi,
  type ExecutionStatus,
  type ExecutionSummary,
  type PromovidaResumo,
} from "../api/orchestrator";
import { IconButton } from "./ui";
import styles from "./AlertsBellPopover.module.css";

const FAILURE_STATUSES = new Set<ExecutionStatus>(["ERROR", "TIMEOUT", "FAILED_BY_REBOOT"]);
const POLL_INTERVAL_MS = 60_000;

interface SystemAlertItem {
  id: string;
  title: string;
  detail: string;
  severity: "danger" | "warn";
}

interface AlertsSnapshot {
  failures: ExecutionSummary[];
  pcpExceptions: PromovidaResumo[];
  systemAlerts: SystemAlertItem[];
}

const EMPTY_SNAPSHOT: AlertsSnapshot = {
  failures: [],
  pcpExceptions: [],
  systemAlerts: [],
};

function isFailureAlert(exec: ExecutionSummary): boolean {
  return FAILURE_STATUSES.has(exec.status) || Boolean(exec.operator_attention_required);
}

export function AlertsBellPopover() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [snapshot, setSnapshot] = useState<AlertsSnapshot>(EMPTY_SNAPSHOT);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestSeqRef = useRef(0);
  const navigate = useNavigate();

  const fetchAlerts = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    const seq = ++requestSeqRef.current;

    setLoading(true);
    try {
      const [overviewRes, promovidasRes] = await Promise.allSettled([
        orchestratorApi.getOverview(ac.signal),
        orchestratorApi.getPromovidas(ac.signal),
      ]);
      if (ac.signal.aborted || seq !== requestSeqRef.current) return;

      setSnapshot((prev) => {
        let failures = prev.failures;
        let systemAlerts = prev.systemAlerts;

        if (overviewRes.status === "fulfilled" && overviewRes.value) {
          const overview = overviewRes.value;
          const recent = Array.isArray(overview.recent) ? overview.recent : [];
          failures = recent.filter(isFailureAlert);

          const nextSystemAlerts: SystemAlertItem[] = [];
          const healthStatus = overview.health?.status;
          if (healthStatus && healthStatus !== "healthy" && healthStatus !== "ok") {
            nextSystemAlerts.push({
              id: `health-${healthStatus}`,
              title: `Saúde do sistema: ${healthStatus}`,
              detail: "Verificar diagnóstico e serviços em Saúde & Manutenção",
              severity: healthStatus === "unhealthy" ? "danger" : "warn",
            });
          }

          const baseline = overview.diagnostics?.operational_baseline;
          if (baseline && baseline.status && baseline.status !== "healthy") {
            nextSystemAlerts.push({
              id: `baseline-${baseline.status}`,
              title: `Baseline operacional: ${baseline.status}`,
              detail:
                baseline.recommended_action ??
                `${baseline.incident_count} incidente(s), ${baseline.attention_count} ponto(s) de atenção`,
              severity: baseline.status === "incident" ? "danger" : "warn",
            });
          }
          systemAlerts = nextSystemAlerts;
        }

        let pcpExceptions = prev.pcpExceptions;
        if (promovidasRes.status === "fulfilled" && Array.isArray(promovidasRes.value?.items)) {
          pcpExceptions = promovidasRes.value.items.filter(
            (item) => typeof item.excecoes_count === "number" && item.excecoes_count > 0,
          );
        }

        return { failures, pcpExceptions, systemAlerts };
      });
    } finally {
      if (!ac.signal.aborted && seq === requestSeqRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void fetchAlerts();
    const timer = window.setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      void fetchAlerts();
    }, POLL_INTERVAL_MS);
    return () => {
      abortRef.current?.abort();
      window.clearInterval(timer);
    };
  }, [fetchAlerts]);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        wrapperRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
      }
    };

    const onMouseDown = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [open]);

  const totalAlerts = useMemo(
    () => snapshot.failures.length + snapshot.pcpExceptions.length + snapshot.systemAlerts.length,
    [snapshot],
  );

  const badgeLabel = totalAlerts > 99 ? "99+" : String(totalAlerts);

  const handleToggle = () => {
    const next = !open;
    setOpen(next);
    if (next) void fetchAlerts();
  };

  const handleNavigate = (to: string) => {
    setOpen(false);
    void navigate(to);
  };

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <IconButton
        className={styles.trigger}
        onClick={handleToggle}
        aria-label="Central de alertas"
        aria-expanded={open}
        aria-haspopup="dialog"
        title={totalAlerts > 0 ? `Central de alertas (${totalAlerts} ativo${totalAlerts === 1 ? "" : "s"})` : "Central de alertas"}
        active={open}
      >
        <Bell size={16} aria-hidden="true" />
        {totalAlerts > 0 && (
          <span className={styles.badge} aria-hidden="true" data-testid="alerts-bell-badge">
            {badgeLabel}
          </span>
        )}
      </IconButton>

      {open && (
        <div
          className={styles.popover}
          role="dialog"
          aria-label="Central de alertas"
        >
          <div className={styles.header}>
            <div className={styles.titleGroup}>
              <h2 className={styles.title}>
                Central de alertas
              </h2>
              <span className={styles.countPill}>{totalAlerts}</span>
            </div>
            <button
              type="button"
              className={styles.closeBtn}
              onClick={() => setOpen(false)}
              aria-label="Fechar central de alertas"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>

          <div className={styles.body}>
            {totalAlerts === 0 ? (
              <div className={styles.empty}>
                {loading ? "Verificando alertas..." : "Nenhum alerta ativo no momento."}
              </div>
            ) : (
              <>
                {snapshot.systemAlerts.length > 0 && (
                  <section className={styles.section} aria-label="Saúde e baseline">
                    <h3 className={styles.sectionTitle}>Saúde & Baseline</h3>
                    <ul className={styles.list}>
                      {snapshot.systemAlerts.map((alert) => (
                        <li key={alert.id}>
                          <button
                            type="button"
                            className={styles.itemBtn}
                            onClick={() => handleNavigate("/sistema")}
                          >
                            <span
                              className={`${styles.itemIcon} ${
                                alert.severity === "danger" ? styles.toneDanger : styles.toneWarn
                              }`}
                              aria-hidden="true"
                            >
                              <ServerCrash size={15} />
                            </span>
                            <span className={styles.itemContent}>
                              <span className={styles.itemTitle}>{alert.title}</span>
                              <span className={styles.itemMeta}>{alert.detail}</span>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {snapshot.failures.length > 0 && (
                  <section className={styles.section} aria-label="Falhas recentes">
                    <h3 className={styles.sectionTitle}>Falhas recentes ({snapshot.failures.length})</h3>
                    <ul className={styles.list}>
                      {snapshot.failures.map((exec) => (
                        <li key={exec.id}>
                          <button
                            type="button"
                            className={styles.itemBtn}
                            onClick={() => handleNavigate(`/execucoes?exec_id=${encodeURIComponent(exec.id)}`)}
                          >
                            <span className={`${styles.itemIcon} ${styles.toneDanger}`} aria-hidden="true">
                              <AlertTriangle size={15} />
                            </span>
                            <span className={styles.itemContent}>
                              <span className={styles.itemTitle}>
                                {exec.automation_name ?? `Automação #${exec.automation_id}`}
                              </span>
                              <span className={styles.itemMeta}>
                                {exec.status}
                                {exec.operator_reason_summary
                                  ? ` · ${exec.operator_reason_summary}`
                                  : exec.failure_reason
                                    ? ` · ${exec.failure_reason}`
                                    : ""}
                              </span>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {snapshot.pcpExceptions.length > 0 && (
                  <section className={styles.section} aria-label="Consultas PCP com exceções">
                    <h3 className={styles.sectionTitle}>
                      Consultas PCP com exceções ({snapshot.pcpExceptions.length})
                    </h3>
                    <ul className={styles.list}>
                      {snapshot.pcpExceptions.map((item) => (
                        <li key={item.slug}>
                          <button
                            type="button"
                            className={styles.itemBtn}
                            onClick={() => handleNavigate(`/pcp?slug=${encodeURIComponent(item.slug)}`)}
                          >
                            <span className={`${styles.itemIcon} ${styles.toneWarn}`} aria-hidden="true">
                              <ClipboardList size={15} />
                            </span>
                            <span className={styles.itemContent}>
                              <span className={styles.itemTitle}>
                                {item.codigo ? `${item.codigo} · ${item.titulo}` : item.titulo}
                              </span>
                              <span className={styles.itemMeta}>
                                {item.excecoes_count}{" "}
                                {item.excecoes_count === 1 ? "exceção ativa" : "exceções ativas"}
                                {item.setor ? ` · ${item.setor}` : ""}
                              </span>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
