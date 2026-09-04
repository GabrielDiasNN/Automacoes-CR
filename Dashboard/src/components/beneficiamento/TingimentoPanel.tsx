import { useCallback, useMemo, useState } from "react";
import { Droplet } from "lucide-react";
import {
  orchestratorApi,
  type BeneficiamentoTingimentoPorCor,
  type BeneficiamentoTingimentoPorMaquina,
  type BeneficiamentoTingimentoPorTurno,
} from "../../api/orchestrator";
import {
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  Loading,
  StatTile,
  type Column,
} from "../ui";
import { TimeSeries } from "../ui/TimeSeries";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { formatNumber, formatPercent } from "../../lib/format";
import styles from "./TingimentoPanel.module.css";

const PRESETS = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
];

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function presetRange(days: number): { dt_inicio: string; dt_fim: string } {
  const fim = new Date();
  const inicio = new Date();
  inicio.setDate(inicio.getDate() - (days - 1));
  return { dt_inicio: isoDate(inicio), dt_fim: isoDate(fim) };
}

function amostraLabel(insuficiente: boolean, value: string): string {
  return insuficiente ? `${value} (amostra baixa)` : value;
}

const MAQUINA_COLUMNS: Column<BeneficiamentoTingimentoPorMaquina>[] = [
  { key: "maquina", header: "Máquina", render: (r) => r.maquina },
  { key: "fases", header: "Lotes", align: "right", render: (r) => formatNumber(r.fases) },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  { key: "eficiencia_tempo_pct", header: "Efic. %", align: "right", render: (r) => formatPercent(r.eficiencia_tempo_pct, 1) },
  { key: "setup_medio_min", header: "Setup médio (min)", align: "right", render: (r) => formatNumber(r.setup_medio_min) },
  {
    key: "reprocesso_kg_pct",
    header: "Reproc. %",
    align: "right",
    render: (r) => (
      <span title={amostraLabel(r.amostra_insuficiente, `${r.fases} lotes`)}>
        {formatPercent(r.reprocesso_kg_pct, 1)}
        {r.amostra_insuficiente ? " ⚠" : ""}
      </span>
    ),
  },
];

const COR_COLUMNS: Column<BeneficiamentoTingimentoPorCor>[] = [
  { key: "cor", header: "Cor", render: (r) => r.cor },
  { key: "ob_distintas", header: "OBs", align: "right", render: (r) => formatNumber(r.ob_distintas), hideOnNarrow: true },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  {
    key: "reprocesso_kg_pct",
    header: "Reproc. %",
    align: "right",
    render: (r) => (
      <span title={amostraLabel(r.amostra_insuficiente, `${r.fases} lotes`)}>
        {formatPercent(r.reprocesso_kg_pct, 1)}
        {r.amostra_insuficiente ? " ⚠" : ""}
      </span>
    ),
  },
];

const TURNO_COLUMNS: Column<BeneficiamentoTingimentoPorTurno>[] = [
  { key: "turno", header: "Turno", render: (r) => r.turno },
  { key: "fases", header: "Lotes", align: "right", render: (r) => formatNumber(r.fases) },
  { key: "kg_total", header: "KG", align: "right", render: (r) => formatNumber(r.kg_total) },
  { key: "eficiencia_tempo_pct", header: "Efic. %", align: "right", render: (r) => formatPercent(r.eficiencia_tempo_pct, 1) },
  { key: "setup_medio_min", header: "Setup médio (min)", align: "right", render: (r) => formatNumber(r.setup_medio_min) },
];

/**
 * Painel dedicado de Tingimento — consome GET /api/beneficiamento/tingimento
 * (escopo fixo CODIGO_FASE=40, independente dos filtros gerais da aba).
 * Foco: reprocesso relativizado ao KG produzido, setup e eficiência de tempo.
 */
export function TingimentoPanel() {
  const [range, setRange] = useState(() => presetRange(30));
  const fetchTingimento = useCallback(
    (signal?: AbortSignal) => orchestratorApi.getBeneficiamentoTingimento(range, signal),
    [range],
  );
  const { data, loading, error } = useAsyncResource(fetchTingimento, [range]);

  // Teto defensivo — o backend deveria limitar o tamanho dos rankings, mas não
  // garante; `.slice` também memoiza a referência para o <DataTable memo>.
  const rankings = useMemo(() => {
    const r = data?.rankings;
    return {
      porMaquina: (r?.por_maquina ?? []).slice(0, 50),
      porCor: (r?.por_cor ?? []).slice(0, 50),
      porTurno: (r?.por_turno ?? []).slice(0, 50),
    };
  }, [data]);
  const rowKeys = useMemo(
    () => ({
      maquina: (r: BeneficiamentoTingimentoPorMaquina) => r.maquina,
      cor: (r: BeneficiamentoTingimentoPorCor) => r.cor,
      turno: (r: BeneficiamentoTingimentoPorTurno) => r.turno,
    }),
    [],
  );
  // Séries diárias memoizadas (xLabels + lines) p/ o <TimeSeries memo> ignorar
  // o re-render quando o pai (BeneficiamentoPage) re-renderiza por tecla.
  const diariaChart = useMemo(() => {
    const pts = data?.series.diaria ?? [];
    if (pts.length <= 1) return null;
    const xLabels = pts.map((p) => p.date.slice(5));
    return {
      xLabels,
      kgLines: [{ label: "kg/dia", values: pts.map((p) => p.kg_total), tone: "cyan" as const }],
      reprocessoLines: [
        { label: "reprocesso %", values: pts.map((p) => p.reprocesso_kg_pct), tone: "amber" as const },
      ],
    };
  }, [data]);

  return (
    <Card
      label="tingimento — reprocesso, setup e eficiência"
      actions={
        <div className={styles.presets}>
          {PRESETS.map((p) => (
            <Button key={p.label} size="sm" variant="subtle" onClick={() => setRange(presetRange(p.days))}>
              {p.label}
            </Button>
          ))}
        </div>
      }
    >
      {loading && !data && <Loading label="carregando tingimento" />}
      {error && <ErrorState message={error} />}
      {data && data.health.status === "no_data" && (
        <EmptyState icon={<Droplet size={20} />} title="Sem lotes de tingimento no recorte" hint="Ajuste o período." />
      )}
      {data && data.health.status !== "no_data" && (
        <div className={styles.body}>
          <div className={styles.tiles}>
            <StatTile label="OBs distintas" value={formatNumber(data.resumo.ob_distintas)} />
            <StatTile label="Lotes" value={formatNumber(data.resumo.fases)} />
            <StatTile label="KG total" value={formatNumber(data.resumo.kg_total)} />
            <StatTile label="Eficiência de tempo" value={formatPercent(data.resumo.eficiencia_tempo_pct, 1)} />
            <StatTile
              label="Reprocesso (% do KG)"
              value={formatPercent(data.resumo.reprocesso_kg_pct, 1)}
              tone={data.resumo.reprocesso_kg_pct > 5 ? "amber" : undefined}
            />
            <StatTile label="Setup médio (min)" value={formatNumber(data.resumo.setup_medio_min)} />
            <StatTile label="Desvio médio (min)" value={formatNumber(data.resumo.desvio_medio_min)} />
            <StatTile label="Produtividade" value={`${formatNumber(data.resumo.produtividade_kg_h)} kg/h`} />
          </div>

          {diariaChart && (
            <div className={styles.charts}>
              <Card label="volume diário (kg)" padded={false}>
                <TimeSeries xLabels={diariaChart.xLabels} lines={diariaChart.kgLines} height={160} />
              </Card>
              <Card label="reprocesso diário (%)" padded={false}>
                <TimeSeries xLabels={diariaChart.xLabels} lines={diariaChart.reprocessoLines} height={160} />
              </Card>
            </div>
          )}

          <div className={styles.rankings}>
            <Card label="por máquina" padded={rankings.porMaquina.length === 0}>
              {rankings.porMaquina.length === 0 ? (
                <EmptyState icon={<Droplet size={18} />} title="Sem dados" />
              ) : (
                <DataTable columns={MAQUINA_COLUMNS} rows={rankings.porMaquina} rowKey={rowKeys.maquina} />
              )}
            </Card>
            <Card label="por cor" padded={rankings.porCor.length === 0}>
              {rankings.porCor.length === 0 ? (
                <EmptyState icon={<Droplet size={18} />} title="Sem dados" />
              ) : (
                <DataTable columns={COR_COLUMNS} rows={rankings.porCor} rowKey={rowKeys.cor} />
              )}
            </Card>
            <Card label="por turno" padded={rankings.porTurno.length === 0}>
              {rankings.porTurno.length === 0 ? (
                <EmptyState icon={<Droplet size={18} />} title="Sem dados" />
              ) : (
                <DataTable columns={TURNO_COLUMNS} rows={rankings.porTurno} rowKey={rowKeys.turno} />
              )}
            </Card>
          </div>
        </div>
      )}
    </Card>
  );
}
