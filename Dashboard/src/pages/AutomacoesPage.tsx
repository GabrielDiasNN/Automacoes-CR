import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BookOpen, Pause, Play, RefreshCw, Workflow, Zap } from "lucide-react";
import {
  orchestratorApi,
  type Automation,
  type PortfolioHealthItem,
} from "../api/orchestrator";
import {
  Button,
  Card,
  ConfirmModal,
  Drawer,
  EmptyState,
  ErrorState,
  FreshnessTag,
  Lamp,
  Loading,
  Nameplate,
  RatioBar,
  Skeleton,
  StatusTag,
} from "../components/ui";
import { useAction } from "../hooks/useAction";
import { usePolling } from "../hooks/usePolling";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { criticalityTone, executionTone, operationalStateLabel, operationalTone, slaTone, toneVar } from "../lib/status";
import { formatDuration } from "../lib/format";
import page from "./page.module.css";
import styles from "./AutomacoesPage.module.css";

interface AutomacoesData {
  items: Automation[];
  /** por `automation_id` — `null` quando o portfólio falhou (best-effort: a
   *  tela não perde os cards, só a camada de criticidade/SLA/runbook). */
  portfolio: Record<number, PortfolioHealthItem> | null;
}

async function fetchAutomacoesData(signal?: AbortSignal): Promise<AutomacoesData> {
  // As duas chamadas não dependem uma da outra — paralelizadas via Promise.all
  // em vez de sequenciais (a versão anterior esperava listAllAutomations
  // terminar antes de sequer iniciar getPortfolioHealth, dobrando a latência
  // de cada tick de polling à toa).
  const [items, portfolioResult] = await Promise.all([
    orchestratorApi.listAllAutomations(signal),
    orchestratorApi.getPortfolioHealth(signal).catch(() => null),
  ]);
  const portfolio = portfolioResult
    ? Object.fromEntries(
        portfolioResult.items
          .filter((it) => it.automation_id != null)
          .map((it) => [it.automation_id as number, it]),
      )
    : null;
  return { items, portfolio };
}

/** Ordena por atenção — quem precisa de olhar primeiro no topo — em vez da
 *  ordem alfabética que o backend devolve. Critério, em ordem de desempate:
 *  estado operacional "attention" > criticidade > nome.
 *
 *  Nota: as comparações `sla_state === "violated" | "at_risk"` que existiam aqui
 *  eram código morto — o backend (`portfolio_catalog._sla_state`) emite
 *  `ok | breached | recovering | unknown`, nunca esses valores, então o SLA
 *  nunca influenciou a ordenação. Removidas ao tipar `sla_state` como `SlaState`.
 *  Wiring correto de `breached`/`recovering` no rank fica para a Onda 4 (paleta
 *  e semântica de SLA), junto com `slaTone`. */
function attentionRank(a: Automation, p: PortfolioHealthItem | undefined): number {
  if (a.operational_state === "attention") return 0;
  if (p?.criticality === "high") return 1;
  if (p?.criticality === "medium") return 2;
  return 3;
}

/** Corpo interno: `useAsyncResource` (aborto real, guarda de sequência). O pai
 *  monta com `key={catalogId}` para o estado de loading reiniciar a cada alvo
 *  — o `.then/.catch/.finally` anterior não cancelava de verdade, só descartava
 *  o resultado. */
function RunbookBody({ catalogId }: { catalogId: string }) {
  const fetcher = useCallback(
    (signal?: AbortSignal) => orchestratorApi.getPortfolioRunbook(catalogId, signal),
    [catalogId],
  );
  const { data: content, loading, error } = useAsyncResource(fetcher, [catalogId]);

  return (
    <>
      {loading && <Loading label="lendo runbook" />}
      {error && <ErrorState message={error} />}
      {!loading && !error && content && (
        <pre
          style={{
            margin: 0,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--fs-small)",
            color: "var(--text-mid)",
            lineHeight: 1.6,
          }}
        >
          {content}
        </pre>
      )}
    </>
  );
}

function RunbookDrawer({
  target,
  onClose,
}: {
  target: { catalogId: string; name: string } | null;
  onClose: () => void;
}) {
  return (
    <Drawer open={!!target} onClose={onClose} eyebrow="// runbook" title={target?.name} width={720}>
      {target && <RunbookBody key={target.catalogId} catalogId={target.catalogId} />}
    </Drawer>
  );
}

export function AutomacoesPage() {
  const navigate = useNavigate();
  const {
    data,
    loading,
    error: err,
    refresh: load,
    lastUpdated,
    rateLimitedUntil,
    refreshQueued,
  } = usePolling(fetchAutomacoesData, 15_000);
  const items = useMemo(() => data?.items ?? [], [data]);
  const portfolio = data?.portfolio ?? null;
  const portfolioFailed = data !== null && data.portfolio === null;
  const { busyKey: busy, run } = useAction<number>();
  const [confirm, setConfirm] = useState<{ id: number; name: string; kind: "dispatch" | "pause" } | null>(null);
  const [runbookTarget, setRunbookTarget] = useState<{ catalogId: string; name: string } | null>(null);
  // Último exec_id disparado por automação nesta sessão — o backend devolve
  // no POST /start e antes era descartado (`.then((r) => ({ message: r.message }))`).
  const [lastExecId, setLastExecId] = useState<Record<number, string>>({});

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const pa = portfolio?.[a.id];
      const pb = portfolio?.[b.id];
      const diff = attentionRank(a, pa) - attentionRank(b, pb);
      return diff !== 0 ? diff : a.name.localeCompare(b.name, "pt-BR");
    });
  }, [items, portfolio]);

  // `?focus=<nome>` vem do Ctrl+K (CommandPalette): rola até o card e o destaca.
  const [searchParams, setSearchParams] = useSearchParams();
  const focusName = searchParams.get("focus");
  const focusedCardRef = useRef<HTMLDivElement>(null);
  const [highlightedId, setHighlightedId] = useState<number | null>(null);

  useEffect(() => {
    if (!focusName || items.length === 0) return;
    const alvo = items.find((a) => a.name === focusName);
    if (!alvo) return;
    focusedCardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedId(alvo.id);
    const limpar = setTimeout(() => setHighlightedId(null), 2400);
    setSearchParams({}, { replace: true }); // consome o parâmetro
    return () => clearTimeout(limpar);
  }, [focusName, items, setSearchParams]);

  const dispatch = useCallback(
    (a: Automation) => {
      setConfirm(null);
      void run(
        a.id,
        () =>
          orchestratorApi.startAutomation(a.id).then((r) => {
            if (r.exec_id) setLastExecId((prev) => ({ ...prev, [a.id]: r.exec_id }));
            return { message: r.exec_id ? `${r.message} (${r.exec_id})` : r.message };
          }),
        { fallbackMessage: `${a.name} disparada`, onDone: load, invalidate: "overview" },
      );
    },
    [run, load],
  );

  const pause = useCallback(
    (a: Automation) => {
      setConfirm(null);
      void run(a.id, () => orchestratorApi.pauseAutomation(a.id), { fallbackMessage: `${a.name} pausada`, onDone: load, invalidate: "overview" });
    },
    [run, load],
  );

  if (loading && items.length === 0) {
    return (
      <div className={page.page}>
        <Nameplate eyebrow="// administração" title="Automações" />
        <div className={styles.grid}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <div className={styles.card}>
                <Skeleton height={20} width="60%" />
                <Skeleton height={14} width="90%" />
                <Skeleton height={48} width="100%" />
                <Skeleton height={28} width="40%" />
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// administração"
        title="Automações"
        actions={
          <div className={page.toolbar}>
            <FreshnessTag
              lastUpdated={lastUpdated}
              error={data && err ? err : null}
              rateLimitedUntil={rateLimitedUntil}
              refreshQueued={refreshQueued}
            />
            {portfolioFailed && (
              <StatusTag tone="grey" dot>
                criticidade indisponível
              </StatusTag>
            )}
            <Button size="sm" icon={<RefreshCw size={13} />} onClick={() => void load()}>
              Atualizar
            </Button>
          </div>
        }
      />

      {err && items.length === 0 ? (
        <ErrorState message={err} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Workflow size={28} />}
          title="nenhuma automação cadastrada"
          hint="Use Tools/New-Automation.ps1 para criar uma automação com manifesto válido."
        />
      ) : (
        <div className={styles.grid}>
          {sortedItems.map((a) => {
            const p = portfolio?.[a.id];
            const total24h = a.success_24h + a.failures_24h;
            const focado = a.name === focusName || a.id === highlightedId;
            const emExecucao = a.active_execution_count > 0;
            const execId = lastExecId[a.id];

            return (
              <Card key={a.id} alert={a.last_status === "ERROR" || a.last_status === "TIMEOUT"}>
                <div
                  ref={focado ? focusedCardRef : undefined}
                  className={styles.card}
                  style={highlightedId === a.id ? { outline: "2px solid var(--cyan)", outlineOffset: 3, borderRadius: 4 } : undefined}
                >
                  <div className={styles.top}>
                    <Lamp
                      size={9}
                      role="img"
                      aria-label={`Estado operacional: ${operationalStateLabel(a.operational_state)}`}
                      // "grey" usa a trilha escura (--track-strong = --graphite-600), não
                      // --grey (mais claro) — preserva a lâmpada "apagada" original.
                      color={
                        operationalTone(a.operational_state) === "grey"
                          ? "var(--track-strong)"
                          : toneVar[operationalTone(a.operational_state)]
                      }
                      style={{ marginTop: 5 }}
                    />
                    <div className={styles.titleWrap}>
                      <span className={styles.name}>{a.name}</span>
                      {a.description && <span className={styles.desc}>{a.description}</span>}
                    </div>
                  </div>

                  <div className={styles.tags}>
                    {p?.criticality && <StatusTag tone={criticalityTone(p.criticality)}>{p.criticality}</StatusTag>}
                    {a.last_status && <StatusTag tone={executionTone(a.last_status)} dot>{a.last_status}</StatusTag>}
                    {emExecucao && (
                      <StatusTag tone="cyan" dot pulse>
                        em execução
                      </StatusTag>
                    )}
                    {!a.enabled && <StatusTag tone="grey">pausada</StatusTag>}
                    {a.test_mode && <StatusTag tone="blue">sandbox</StatusTag>}
                    {a.queue_group && <span className={styles.meta}>fila: {a.queue_group}</span>}
                  </div>

                  {(a.last_status === "ERROR" || a.last_status === "TIMEOUT") && a.last_failure_reason && (
                    <p className={styles.failureReason}>{a.last_failure_reason}</p>
                  )}

                  <dl className={styles.metrics}>
                    <div>
                      <dt className={styles.mLabel}>sucesso / falha 24h</dt>
                      <dd className={styles.mVal}>
                        <span style={{ color: "var(--green)" }}>{a.success_24h}</span>
                        <span className={styles.slash}>/</span>
                        <span style={{ color: a.failures_24h ? "var(--red)" : "var(--text-lo)" }}>{a.failures_24h}</span>
                        {/* Dentro do <dd> (não como <div> irmão) — um <dl> só aceita
                         *  <dt>/<dd> (ou <div> agrupando um par) como filho direto;
                         *  um terceiro <div> ali quebrava a estrutura (achado via
                         *  axe-core, Onda 4-3). */}
                        {total24h > 0 && (
                          <div style={{ marginTop: 4 }}>
                            <RatioBar success={a.success_24h} failures={a.failures_24h} />
                          </div>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className={styles.mLabel}>sla</dt>
                      <dd className={styles.mVal}>
                        {a.sla_minutes ? (
                          p?.sla_state ? (
                            <StatusTag tone={slaTone(p.sla_state)}>{`${a.sla_minutes}min`}</StatusTag>
                          ) : (
                            `${a.sla_minutes}min`
                          )
                        ) : (
                          "—"
                        )}
                        {p?.schedule_lag_minutes != null && p.schedule_lag_minutes > 0 && (
                          <span className={styles.mMeta}> · atraso {p.schedule_lag_minutes}min</span>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className={styles.mLabel}>
                        última duração{a.avg_duration_24h_seconds != null ? " / média 24h" : ""}
                      </dt>
                      <dd className={styles.mVal}>
                        {formatDuration(a.last_execution_duration_seconds)}
                        {a.avg_duration_24h_seconds != null && (
                          <span className={styles.mMeta}> / {formatDuration(a.avg_duration_24h_seconds)}</span>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className={styles.mLabel}>próxima janela</dt>
                      <dd className={styles.mMeta} title={a.next_runs_preview?.slice(0, 3).join(" · ") || undefined}>
                        {a.next_run ?? a.schedule_summary ?? "manual"}
                      </dd>
                    </div>
                  </dl>

                  <div className={styles.links}>
                    <button
                      type="button"
                      className={styles.linkBtn}
                      onClick={() => void navigate(`/execucoes?automation_id=${a.id}`)}
                    >
                      ver execuções
                    </button>
                    {execId && (
                      <button
                        type="button"
                        className={styles.linkBtn}
                        onClick={() => void navigate(`/execucoes?automation_id=${a.id}`)}
                      >
                        {execId}
                      </button>
                    )}
                    {p?.runbook_path && (
                      <button
                        type="button"
                        className={styles.linkBtn}
                        onClick={() => setRunbookTarget({ catalogId: p.catalog_id, name: a.name })}
                      >
                        <BookOpen size={11} style={{ verticalAlign: "-1px" }} /> runbook
                      </button>
                    )}
                  </div>

                  <div className={styles.actions}>
                    {/* aria-label único por card: com N automações, N botões
                     *  "Disparar" idênticos são indistinguíveis para leitor
                     *  de tela sem depender de navegação visual. */}
                    {a.enabled ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Pause size={13} />}
                        disabled={busy === a.id}
                        aria-label={`Pausar ${a.name}`}
                        onClick={() => setConfirm({ id: a.id, name: a.name, kind: "pause" })}
                      >
                        Pausar
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Play size={13} />}
                        disabled={busy === a.id}
                        aria-label={`Retomar ${a.name}`}
                        onClick={() =>
                          void run(a.id, () => orchestratorApi.resumeAutomation(a.id), {
                            fallbackMessage: `${a.name} retomada`,
                            onDone: load,
                            invalidate: "overview",
                          })
                        }
                      >
                        Retomar
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<Zap size={13} />}
                      disabled={busy === a.id || !a.enabled || emExecucao}
                      title={emExecucao ? "Já há uma execução em andamento" : undefined}
                      // O motivo de estar desabilitado só existia no `title`
                      // (hover) — invisível a teclado/toque/leitor de tela.
                      aria-label={emExecucao ? `Disparar ${a.name} — já há uma execução em andamento` : `Disparar ${a.name}`}
                      onClick={() => setConfirm({ id: a.id, name: a.name, kind: "dispatch" })}
                    >
                      Disparar
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <ConfirmModal
        open={!!confirm}
        title={confirm?.kind === "dispatch" ? "Disparar automação" : "Pausar automação"}
        message={
          confirm?.kind === "dispatch"
            ? `Disparar "${confirm.name}" agora? O script roda em produção fora da janela agendada.`
            : `Pausar "${confirm?.name}"? Nenhuma execução automática ocorrerá até retomar.`
        }
        confirmLabel={confirm?.kind === "dispatch" ? "Disparar" : "Pausar"}
        danger={confirm?.kind === "dispatch"}
        onConfirm={() => {
          if (!confirm) return;
          const a = items.find((it) => it.id === confirm.id);
          if (!a) return;
          if (confirm.kind === "dispatch") dispatch(a);
          else pause(a);
        }}
        onCancel={() => setConfirm(null)}
      />

      <RunbookDrawer target={runbookTarget} onClose={() => setRunbookTarget(null)} />
    </div>
  );
}
