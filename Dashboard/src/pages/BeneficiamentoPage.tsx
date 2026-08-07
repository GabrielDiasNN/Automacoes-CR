import { useCallback, useMemo, useState } from "react";
import { Factory, RefreshCw } from "lucide-react";
import {
  orchestratorApi,
  type BeneficiamentoFaseCritica,
  type BeneficiamentoGargalo,
  type BeneficiamentoOverview,
  type BeneficiamentoProdutoPrincipal,
  type BeneficiamentoSetorRanking,
  type BeneficiamentoTurnoRanking,
} from "../api/orchestrator";
import {
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  Loading,
  Nameplate,
  Select,
  Sparkline,
  StatTile,
  StatusTag,
  TimeSeries,
  type Column,
  type SeriesLine,
  useToast,
} from "../components/ui";
import { DetailDrawer, type DetailDrawerRequest } from "../components/beneficiamento/DetailDrawer";
import { Treemap } from "../components/beneficiamento/Treemap";
import { TingimentoPanel } from "../components/beneficiamento/TingimentoPanel";
import {
  DEFAULT_BENEFICIAMENTO_FILTERS,
  FilterBar,
  type BeneficiamentoFiltersState,
} from "../components/beneficiamento/FilterBar";
import { usePolling } from "../hooks/usePolling";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { healthTone, healthLabel } from "../lib/status";
import { formatNumber, formatPercent } from "../lib/format";
import page from "./page.module.css";

const REFRESH_PERIODS: { value: "diario" | "mensal"; label: string }[] = [
  { value: "diario", label: "Diário" },
  { value: "mensal", label: "Mensal" },
];

const GARGALO_COLUMNS: Column<BeneficiamentoGargalo>[] = [
  { key: "maquina", header: "Máquina", render: (r) => r.maquina },
  { key: "fase", header: "Fase", render: (r) => r.fase },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  {
    key: "eficiencia_tempo_pct",
    header: "Efic. %",
    align: "right",
    render: (r) => formatPercent(r.eficiencia_tempo_pct, 1),
  },
  { key: "desvio_min", header: "Desvio (min)", align: "right", render: (r) => formatNumber(r.desvio_min), hideOnNarrow: true },
];

const FASE_CRITICA_COLUMNS: Column<BeneficiamentoFaseCritica>[] = [
  { key: "fase", header: "Fase", render: (r) => r.fase },
  {
    key: "fases_concluidas",
    header: "Fases",
    align: "right",
    render: (r) => formatNumber(r.fases_concluidas),
    hideOnNarrow: true,
  },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  {
    key: "eficiencia_tempo_pct",
    header: "Efic. %",
    align: "right",
    render: (r) => formatPercent(r.eficiencia_tempo_pct, 1),
  },
];

const PRODUTO_COLUMNS: Column<BeneficiamentoProdutoPrincipal>[] = [
  { key: "produto", header: "Produto", render: (r) => r.produto },
  { key: "artigo", header: "Artigo", render: (r) => r.artigo, hideOnNarrow: true },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  {
    key: "reprocesso_kg_pct",
    header: "Reproc. %",
    align: "right",
    render: (r) => formatPercent(r.reprocesso_kg_pct, 1),
  },
  {
    key: "produtividade_kg_h",
    header: "Kg/h",
    align: "right",
    render: (r) => formatNumber(r.produtividade_kg_h),
    hideOnNarrow: true,
  },
];

const SETOR_COLUMNS: Column<BeneficiamentoSetorRanking>[] = [
  { key: "setor", header: "Setor industrial", render: (r) => r.setor },
  { key: "ob_distintas", header: "OBs", align: "right", render: (r) => formatNumber(r.ob_distintas), hideOnNarrow: true },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  {
    key: "eficiencia_tempo_pct",
    header: "Efic. %",
    align: "right",
    render: (r) => formatPercent(r.eficiencia_tempo_pct, 1),
  },
];

const TURNO_COLUMNS: Column<BeneficiamentoTurnoRanking>[] = [
  { key: "turno_label", header: "Turno", render: (r) => r.turno_label },
  { key: "ob_distintas", header: "OBs", align: "right", render: (r) => formatNumber(r.ob_distintas), hideOnNarrow: true },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  {
    key: "eficiencia_tempo_pct",
    header: "Efic. %",
    align: "right",
    render: (r) => formatPercent(r.eficiencia_tempo_pct, 1),
  },
  {
    key: "produtividade_kg_h",
    header: "Kg/h",
    align: "right",
    render: (r) => formatNumber(r.produtividade_kg_h),
    hideOnNarrow: true,
  },
];

interface RankingSectionProps<T> {
  title: string;
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick: (row: T) => void;
}

function RankingSection<T>({ title, rows, columns, rowKey, onRowClick }: RankingSectionProps<T>) {
  return (
    <Card label={title} padded={rows.length === 0}>
      {rows.length === 0 ? (
        <EmptyState icon={<Factory size={20} />} title="Sem dados" hint="Ajuste os filtros para ver resultados." />
      ) : (
        <DataTable columns={columns} rows={rows.slice(0, 8)} rowKey={rowKey} onRowClick={onRowClick} />
      )}
    </Card>
  );
}

export function BeneficiamentoPage() {
  const toast = useToast();
  const [filters, setFilters] = useState<BeneficiamentoFiltersState>(DEFAULT_BENEFICIAMENTO_FILTERS);
  const debouncedQ = useDebouncedValue(filters.q, 350);
  const [refreshPeriod, setRefreshPeriod] = useState<"diario" | "mensal">("diario");
  const [refreshing, setRefreshing] = useState(false);
  const [detailRequest, setDetailRequest] = useState<DetailDrawerRequest | null>(null);

  const patchFilters = useCallback((patch: Partial<BeneficiamentoFiltersState>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
  }, []);
  const resetFilters = useCallback(() => setFilters(DEFAULT_BENEFICIAMENTO_FILTERS), []);

  const overviewParams = useMemo(
    () => ({
      dt_inicio: filters.dtInicio || undefined,
      dt_fim: filters.dtFim || undefined,
      maquina: filters.maquina || undefined,
      fase: filters.fase || undefined,
      turno: filters.turno || undefined,
      alternativo: filters.alternativo || undefined,
      q: debouncedQ || undefined,
      setor: filters.setor || undefined,
      grupo_fase: filters.grupoFase || undefined,
      tipo_maquina: filters.tipoMaquina || undefined,
      reprocesso: filters.reprocesso || undefined,
      status: filters.status || undefined,
    }),
    [
      filters.dtInicio,
      filters.dtFim,
      filters.maquina,
      filters.fase,
      filters.turno,
      filters.alternativo,
      filters.setor,
      filters.grupoFase,
      filters.tipoMaquina,
      filters.reprocesso,
      filters.status,
      debouncedQ,
    ],
  );

  const fetchOverview = useCallback(() => orchestratorApi.getBeneficiamentoOverview(overviewParams), [overviewParams]);
  const {
    data: overview,
    loading: overviewLoading,
    error: overviewError,
    refresh: reloadOverview,
  } = usePolling<BeneficiamentoOverview>(fetchOverview, 30_000, [overviewParams]);

  const { data: health, refresh: reloadHealth } = usePolling(orchestratorApi.getBeneficiamentoHealth, 60_000);

  const doRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await orchestratorApi.refreshBeneficiamento(refreshPeriod);
      await Promise.all([reloadOverview(), reloadHealth()]);
      toast("Snapshot atualizado.", "green");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "red");
    } finally {
      setRefreshing(false);
    }
  }, [refreshPeriod, reloadOverview, reloadHealth, toast]);

  const contextFilters = useMemo(
    () => ({ dt_inicio: overviewParams.dt_inicio, dt_fim: overviewParams.dt_fim, q: overviewParams.q }),
    [overviewParams],
  );

  if (overviewLoading && !overview) {
    return (
      <div className={page.page}>
        <Loading label="lendo histórico" />
      </div>
    );
  }
  if (overviewError && !overview) {
    return (
      <div className={page.page}>
        <ErrorState message={overviewError} />
      </div>
    );
  }
  if (!overview) return null;

  const { kpis } = overview;
  const volumeSeries = overview.series.volume_diario;
  const efficiencySeries = overview.series.eficiencia_diaria;
  const xLabels = volumeSeries.map((p) => p.date.slice(5));
  const kgSparkline = volumeSeries.map((p) => p.kg_total);
  const efficiencySparkline = efficiencySeries.map((p) => p.eficiencia_tempo_pct);
  const volumeLine: SeriesLine = { label: "kg/dia", values: kgSparkline, tone: "cyan" };
  const efficiencyLine: SeriesLine = { label: "eficiência %", values: efficiencySparkline, tone: "green" };

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// análise"
        title="Beneficiamento"
        actions={
          <div className={page.toolbar}>
            <Select
              value={refreshPeriod}
              onChange={(e) => setRefreshPeriod(e.target.value as "diario" | "mensal")}
              aria-label="Período do snapshot"
            >
              {REFRESH_PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </Select>
            <Button size="sm" icon={<RefreshCw size={13} />} onClick={doRefresh} disabled={refreshing}>
              {refreshing ? "Atualizando…" : "Atualizar snapshot"}
            </Button>
          </div>
        }
      />

      <TingimentoPanel />

      <FilterBar filters={filters} options={overview.filter_options} onChange={patchFilters} onReset={resetFilters} />

      {health && (
        <Card label="saúde do snapshot" alert={healthTone(health.status) === "red"}>
          <div style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap", alignItems: "center" }}>
            <StatusTag tone={healthTone(health.status)} dot>
              {healthLabel(health.status)}
            </StatusTag>
            {health.latest_period && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                último: {health.latest_period.label} · {health.latest_period.updated_at ?? "—"}
              </span>
            )}
          </div>
          {health.recommended_action && (
            <p style={{ marginTop: "var(--sp-3)", marginBottom: 0, fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
              {health.recommended_action}
            </p>
          )}
        </Card>
      )}

      {overview.health.status === "no_data" ? (
        <Card>
          <EmptyState
            icon={<Factory size={22} />}
            title="Nenhum registro para este recorte"
            hint="Ajuste os filtros de data, máquina, fase, turno ou produto."
          />
        </Card>
      ) : (
        <>
          <div className={page.tiles}>
            <StatTile label="OBs distintas" value={formatNumber(kpis.ob_distintas)} />
            <StatTile
              label="Fases concluídas"
              value={formatNumber(kpis.fases_concluidas)}
              hint={
                kpis.planejado_pct > 0 ? (
                  <span title={`${formatNumber(kpis.fases_planejadas)} fases ainda planejadas/programadas, não concluídas`}>
                    {formatPercent(kpis.planejado_pct, 1)} planejado
                  </span>
                ) : undefined
              }
              tone={kpis.planejado_pct > 20 ? "amber" : undefined}
            />
            <StatTile
              label="KG total"
              value={formatNumber(kpis.kg_total)}
              hint={kgSparkline.length > 1 ? <Sparkline data={kgSparkline} tone="cyan" width={96} height={24} /> : undefined}
            />
            <StatTile label="MT total" value={formatNumber(kpis.mt_total)} />
            <StatTile
              label="Eficiência de tempo"
              value={formatPercent(kpis.eficiencia_tempo_pct, 1)}
              hint={
                efficiencySparkline.length > 1 ? (
                  <Sparkline data={efficiencySparkline} tone="green" width={96} height={24} />
                ) : undefined
              }
            />
            <StatTile
              label="Reprocesso"
              value={formatPercent(kpis.reprocesso_kg_pct, 1)}
              tone={kpis.reprocesso_kg_pct > 10 ? "amber" : undefined}
            />
            <StatTile label="Desvio médio (min)" value={formatNumber(kpis.desvio_tempo_min)} />
            <StatTile label="Produtividade" value={`${formatNumber(kpis.produtividade_kg_h)} kg/h`} />
          </div>

          {(volumeSeries.length > 1 || efficiencySeries.length > 1) && (
            <div className={page.split}>
              {volumeSeries.length > 1 && (
                <Card label="volume diário (kg)">
                  <TimeSeries xLabels={xLabels} lines={[volumeLine]} height={180} />
                </Card>
              )}
              {efficiencySeries.length > 1 && (
                <Card label="eficiência diária (%)">
                  <TimeSeries xLabels={xLabels} lines={[efficiencyLine]} height={180} />
                </Card>
              )}
            </div>
          )}

          {overview.treemap.length > 0 && (
            <Card label="volume por setor → fase → máquina">
              <Treemap
                nodes={overview.treemap}
                onCellClick={({ setor, fase }) =>
                  setDetailRequest({ targetType: "fase", label: `${setor} / ${fase}`, setor, fase })
                }
              />
            </Card>
          )}

          <div className={page.split}>
            <RankingSection
              title="por setor industrial"
              rows={overview.rankings.setores}
              columns={SETOR_COLUMNS}
              rowKey={(r) => r.setor}
              onRowClick={(r) => setDetailRequest({ targetType: "setor", label: r.setor, setor: r.setor })}
            />
            <RankingSection
              title="fases críticas"
              rows={overview.rankings.fases_criticas}
              columns={FASE_CRITICA_COLUMNS}
              rowKey={(r) => r.fase}
              onRowClick={(r) => setDetailRequest({ targetType: "fase", label: r.fase, fase: r.fase })}
            />
            <RankingSection
              title="gargalos (máquina + fase)"
              rows={overview.rankings.gargalos}
              columns={GARGALO_COLUMNS}
              rowKey={(r) => `${r.maquina}-${r.fase}`}
              onRowClick={(r) =>
                setDetailRequest({
                  targetType: "maquina_fase",
                  label: `${r.maquina} / ${r.fase}`,
                  maquina: r.maquina,
                  fase: r.fase,
                })
              }
            />
            <RankingSection
              title="produtos principais"
              rows={overview.rankings.produtos_principais}
              columns={PRODUTO_COLUMNS}
              rowKey={(r) => r.codigo}
              onRowClick={(r) => setDetailRequest({ targetType: "produto", label: r.produto, alternativo: r.codigo })}
            />
            <RankingSection
              title="por turno"
              rows={overview.turnos}
              columns={TURNO_COLUMNS}
              rowKey={(r) => r.turno_label}
              onRowClick={(r) => setDetailRequest({ targetType: "turno", label: r.turno_label, turno: r.turno_label })}
            />
          </div>
        </>
      )}

      <DetailDrawer request={detailRequest} contextFilters={contextFilters} onClose={() => setDetailRequest(null)} />
    </div>
  );
}
