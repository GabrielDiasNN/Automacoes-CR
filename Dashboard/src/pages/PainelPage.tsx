import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ClipboardList, Factory, Image as ImageIcon, ShieldCheck, Workflow } from "lucide-react";
import { usePolling } from "../hooks/usePolling";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { writeCache } from "../lib/resourceCache";
import {
  orchestratorApi,
  type BeneficiamentoOverview,
  type ExecutionSummary,
  type PromovidaResumo,
} from "../api/orchestrator";
import {
  BaselineAnnunciators,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FreshnessTag,
  ListRow,
  Loading,
  Nameplate,
  StatTile,
  StatusTag,
} from "../components/ui";
import { executionLabel, executionTone, healthLabel, healthTone, severityTone } from "../lib/status";
import { formatAge, formatDuration, formatNumber, formatPercent, shortId } from "../lib/format";
import page from "./page.module.css";

function ExecRow({ ex, onClick }: { ex: ExecutionSummary; onClick: () => void }) {
  const tone = ex.operator_attention_required ? severityTone(ex.operator_severity) : executionTone(ex.status);
  const label = ex.automation_name ?? `#${ex.automation_id}`;
  return (
    <ListRow
      onClick={onClick}
      tone={`var(--${tone === "grey" ? "graphite-600" : tone})`}
      aria-label={`Execução ${label}, status ${ex.status}`}
      leading={
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)", flexShrink: 0 }}>
          {shortId(ex.id, 12)}
        </span>
      }
      trailing={
        <>
          {ex.operator_attention_required && ex.operator_severity && (
            <StatusTag tone={severityTone(ex.operator_severity)}>{ex.operator_severity}</StatusTag>
          )}
          <StatusTag tone={executionTone(ex.status)} dot pulse={ex.status === "RUNNING"}>
            {executionLabel(ex.status)}
          </StatusTag>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)", flexShrink: 0 }}>
            {formatDuration(ex.duration_seconds)}
          </span>
        </>
      }
    >
      {label}
    </ListRow>
  );
}

function RadarRow({ item, onClick }: { item: PromovidaResumo; onClick: () => void }) {
  const hasAlerts = item.excecoes_count > 0;
  const tone = hasAlerts ? "var(--amber)" : item.has_snapshot ? "var(--cyan)" : undefined;
  return (
    <ListRow
      onClick={onClick}
      {...(tone ? { tone } : {})}
      leading={
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--cyan)", flexShrink: 0 }}>
          {item.codigo ?? item.slug.slice(0, 6).toUpperCase()}
        </span>
      }
      trailing={
        <>
          {(item.cards_count ?? 0) > 0 && (
            <StatusTag tone="blue">
              <ImageIcon size={11} style={{ marginRight: 4, verticalAlign: "-1px" }} />
              {item.cards_count} cards
            </StatusTag>
          )}
          <StatusTag tone={hasAlerts ? "amber" : item.has_snapshot ? "green" : "grey"} dot>
            {hasAlerts
              ? `${formatNumber(item.excecoes_count)} exceções`
              : item.has_snapshot
                ? `${formatNumber(item.total_rows)} reg.`
                : "sem snapshot"}
          </StatusTag>
          {item.age_minutes !== null && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)", flexShrink: 0 }}>
              {formatAge(item.age_minutes * 60)}
            </span>
          )}
        </>
      }
    >
      <div>
        <strong style={{ color: "var(--text-hi)" }}>{item.nome}</strong>
        {item.setor && (
          <span style={{ marginLeft: 8, fontSize: "var(--fs-label)", color: "var(--text-lo)" }}>
            {item.setor}
          </span>
        )}
      </div>
    </ListRow>
  );
}

export function PainelPage() {
  const navigate = useNavigate();
  const [onlyAlerts, setOnlyAlerts] = useState(false);
  const { data, loading, error, lastUpdated, rateLimitedUntil, refreshQueued } = usePolling(
    (signal) => orchestratorApi.getOverview(signal),
    15_000,
    [],
    { cacheKey: "overview", onData: (ov) => writeCache("health", ov.health) },
  );

  const radarRes = useAsyncResource<{ items: PromovidaResumo[] }>(
    (signal) => orchestratorApi.getPromovidas(signal).catch(() => ({ items: [] })),
    [],
  );

  const bnfRes = useAsyncResource<BeneficiamentoOverview | null>(
    (signal) => orchestratorApi.getBeneficiamentoOverview(undefined, signal).catch(() => null),
    [],
  );

  const radarItems = useMemo(() => {
    const all = radarRes.data?.items ?? [];
    const filtered = onlyAlerts ? all.filter((i) => i.excecoes_count > 0) : all;
    return [...filtered]
      .sort((a, b) => {
        if (b.excecoes_count !== a.excecoes_count) return b.excecoes_count - a.excecoes_count;
        if (Number(b.has_snapshot) !== Number(a.has_snapshot)) return Number(b.has_snapshot) - Number(a.has_snapshot);
        return b.total_rows - a.total_rows;
      })
      .slice(0, 8);
  }, [radarRes.data, onlyAlerts]);

  const radarSummary = useMemo(() => {
    const all = radarRes.data?.items ?? [];
    const comSnapshot = all.filter((i) => i.has_snapshot).length;
    const totalExcecoes = all.reduce((acc, i) => acc + i.excecoes_count, 0);
    const totalCards = all.reduce((acc, i) => acc + (i.cards_count ?? 0), 0);
    return { total: all.length, comSnapshot, totalExcecoes, totalCards };
  }, [radarRes.data]);

  if (loading && !data) {
    return (
      <div className={page.page}>
        <Loading label="carregando visão geral" />
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

  const { kpis, health, diagnostics } = data;
  const worker = health.worker;
  const baseline = diagnostics.operational_baseline;
  const running = worker.active_tasks > 0;
  const activeAlarms = baseline.metrics.filter((m) => m.status !== "healthy").length;
  const bnfKpis = bnfRes.data?.health.status !== "no_data" ? bnfRes.data?.kpis : null;

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="Gestão & BI · Command Center"
        title="Visão Geral"
        actions={
          <div className={page.toolbar}>
            <FreshnessTag
              lastUpdated={lastUpdated}
              error={data && error ? error : null}
              rateLimitedUntil={rateLimitedUntil}
              refreshQueued={refreshQueued}
            />
            <StatusTag tone={healthTone(health.status)} dot pulse={health.status === "unhealthy"}>
              sistema {healthLabel(health.status)}
            </StatusTag>
            <Button size="sm" variant="primary" icon={<ClipboardList size={14} />} onClick={() => void navigate("/pcp")}>
              Central de Consultas
            </Button>
          </div>
        }
      />

      {/* Bloco 1 — Produção & Beneficiamento (Bate-Pronto) */}
      <Card
        label="Produção & Beneficiamento · Último Snapshot"
        actions={
          <Button size="sm" variant="subtle" icon={<Factory size={13} />} onClick={() => void navigate("/beneficiamento")}>
            Abrir BI de Produção
          </Button>
        }
      >
        {bnfKpis ? (
          <div className={page.tiles}>
            <StatTile label="KG produzido" value={formatNumber(bnfKpis.kg_total)} tone="cyan" />
            <StatTile label="OBs distintas" value={formatNumber(bnfKpis.ob_distintas)} />
            <StatTile label="Eficiência de tempo" value={formatPercent(bnfKpis.eficiencia_tempo_pct, 1)} tone="green" />
            <StatTile
              label="Reprocesso"
              value={formatPercent(bnfKpis.reprocesso_kg_pct, 1)}
              tone={bnfKpis.reprocesso_kg_pct > 10 ? "amber" : undefined}
            />
            <StatTile label="Produtividade" value={`${formatNumber(bnfKpis.produtividade_kg_h)} kg/h`} big={false} />
          </div>
        ) : (
          <div className={page.tiles}>
            <StatTile label="Consultas e automações" value={radarSummary.total} />
            <StatTile label="Snapshots ativos" value={radarSummary.comSnapshot} tone="cyan" />
            <StatTile
              label="Exceções detectadas"
              value={formatNumber(radarSummary.totalExcecoes)}
              tone={radarSummary.totalExcecoes > 0 ? "amber" : "green"}
            />
            <StatTile label="Cards PNG prontos" value={radarSummary.totalCards} tone="blue" />
          </div>
        )}
      </Card>

      {/* Bloco 2 — Radar de PCP & Alertas + Orquestração */}
      <div className={page.two}>
        <Card
          label="Radar de PCP, Consultas & Alertas Ativos"
          padded={radarItems.length === 0}
          actions={
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Button
                size="sm"
                variant={onlyAlerts ? "primary" : "subtle"}
                aria-pressed={onlyAlerts}
                onClick={() => setOnlyAlerts((v) => !v)}
              >
                {onlyAlerts ? "Mostrar todos" : "Somente alertas"}
              </Button>
              <Button size="sm" variant="subtle" icon={<ArrowRight size={13} />} onClick={() => void navigate("/pcp")}>
                Ver todas ({radarSummary.total})
              </Button>
            </div>
          }
        >
          {radarItems.length === 0 ? (
            <EmptyState
              icon={<ClipboardList size={22} />}
              title={onlyAlerts ? "Nenhuma consulta com exceções ativas" : "Nenhum snapshot operacional encontrado"}
              hint={
                onlyAlerts
                  ? "Desative o filtro de alertas para ver todas as consultas."
                  : "Dispare uma automação ou consulta promovida para popular o radar."
              }
            />
          ) : (
            <div className={page.list}>
              {radarItems.map((item) => (
                <RadarRow
                  key={item.slug}
                  item={item}
                  onClick={() => void navigate(`/pcp?slug=${encodeURIComponent(item.slug)}`)}
                />
              ))}
            </div>
          )}
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          <Card
            label="Orquestração · 24h"
            actions={
              <Button size="sm" variant="subtle" icon={<Workflow size={13} />} onClick={() => void navigate("/automacoes")}>
                Gerenciar
              </Button>
            }
          >
            <div className={page.tiles}>
              <StatTile label="automações ativas" value={kpis.active_automations} />
              <StatTile label="sucesso 24h" value={kpis.success_24h} tone="green" />
              <StatTile label="erros 24h" value={kpis.errors_24h} tone={kpis.errors_24h > 0 ? "red" : undefined} />
              <StatTile label="fila pendente" value={kpis.pending_now} tone={kpis.pending_now > 0 ? "amber" : undefined} />
            </div>
            <div style={{ marginTop: "var(--sp-3)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <StatusTag tone={worker.is_alive ? "green" : "red"} dot pulse={running}>
                worker {worker.is_alive ? "online" : "offline"}
                {running ? ` · ${worker.active_tasks} em execução` : ""}
              </StatusTag>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)" }}>
                próxima janela: {kpis.next_window ?? "—"}
              </span>
            </div>
          </Card>

          <Card label="Saúde Operacional" alert={baseline.status === "incident"}>
            {activeAlarms === 0 ? (
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", color: "var(--green)" }}>
                <ShieldCheck size={16} />
                <span style={{ fontSize: "var(--fs-small)" }}>
                  Operação dentro da linha de base — sem alarmes críticos
                </span>
              </div>
            ) : (
              <BaselineAnnunciators metrics={baseline.metrics} />
            )}
          </Card>
        </div>
      </div>

      {/* Bloco 3 — Últimas execuções */}
      <Card
        label="últimas execuções"
        padded={data.recent.length === 0}
        actions={
          <Button size="sm" variant="subtle" icon={<ArrowRight size={14} />} onClick={() => void navigate("/execucoes")}>
            ver todas
          </Button>
        }
      >
        <div className={page.list}>
          {data.recent.slice(0, 6).map((ex) => (
            <ExecRow key={ex.id} ex={ex} onClick={() => void navigate(`/execucoes?exec_id=${encodeURIComponent(ex.id)}`)} />
          ))}
          {data.recent.length === 0 && (
            <div style={{ padding: "var(--sp-4)", textAlign: "center", fontFamily: "var(--font-mono)", color: "var(--text-lo)", fontSize: "var(--fs-small)" }}>
              nenhuma execução recente
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
