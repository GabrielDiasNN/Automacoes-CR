import { useCallback, useEffect, useMemo, useState } from "react";
import { Factory, RefreshCw } from "lucide-react";
import { orchestratorApi, type BeneficiamentoDashboard } from "../api/orchestrator";
import { Button, Card, EmptyState, ErrorState, Loading, Nameplate, StatTile, StatusTag } from "../components/ui";
import { healthTone, healthLabel } from "../lib/status";
import { formatNumber } from "../lib/format";
import page from "./page.module.css";

function humanize(key: string): string {
  return key.replace(/[_-]+/g, " ").trim();
}

function isPrimitive(v: unknown): v is number | string {
  return typeof v === "number" || typeof v === "string";
}

function renderValue(v: unknown): string {
  if (typeof v === "number") return formatNumber(v);
  if (typeof v === "string") return v;
  return "—";
}

/** Extrai entradas primitivas de um dicionário para mostradores. */
function primitiveEntries(obj: Record<string, unknown> | undefined): [string, number | string][] {
  if (!obj) return [];
  return Object.entries(obj).filter(([, v]) => isPrimitive(v)) as [string, number | string][];
}

export function BeneficiamentoPage() {
  const [data, setData] = useState<BeneficiamentoDashboard | null>(null);
  const [period, setPeriod] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await orchestratorApi.getBeneficiamentoDashboard();
      setData(d);
      setPeriod((p) => p || d.default_period);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const periodKeys = useMemo(() => (data ? Object.keys(data.periods) : []), [data]);
  const current = data && period ? data.periods[period] : undefined;

  const doRefresh = async () => {
    if (!period) return;
    setRefreshing(true);
    try {
      await orchestratorApi.refreshBeneficiamento(period);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  if (loading && !data) {
    return (
      <div className={page.page}>
        <Loading label="lendo snapshot" />
      </div>
    );
  }
  if (err && !data) {
    return (
      <div className={page.page}>
        <ErrorState message={err} />
      </div>
    );
  }
  if (!data) return null;

  const health = data.health;
  const metricEntries = primitiveEntries(current?.metrics);
  const highlightEntries = primitiveEntries(current?.highlights);
  const rankings = current?.rankings ?? {};

  const selectStyle: React.CSSProperties = {
    background: "var(--surface-up)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    color: "var(--text-mid)",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--fs-small)",
    padding: "6px var(--sp-3)",
  };

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// análise"
        title="Beneficiamento"
        actions={
          <div className={page.toolbar}>
            <select style={selectStyle} value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Período">
              {periodKeys.map((k) => (
                <option key={k} value={k}>
                  {data.periods[k]?.label ?? k}
                </option>
              ))}
            </select>
            <Button size="sm" icon={<RefreshCw size={13} />} onClick={doRefresh} disabled={refreshing}>
              {refreshing ? "Atualizando…" : "Atualizar snapshot"}
            </Button>
          </div>
        }
      />

      {/* Saúde do snapshot */}
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
          {current && <StatusTag tone={healthTone(current.status)}>{current.status}</StatusTag>}
        </div>
        {(health.recommended_action || current?.reason_message) && (
          <p style={{ marginTop: "var(--sp-3)", marginBottom: 0, fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
            {current?.reason_message ?? health.recommended_action}
          </p>
        )}
      </Card>

      {/* KPIs */}
      {metricEntries.length > 0 ? (
        <div className={page.tiles}>
          {metricEntries.map(([k, v]) => (
            <StatTile key={k} label={humanize(k)} value={renderValue(v)} big={typeof v === "number"} />
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState icon={<Factory size={22} />} title="Sem métricas para este período" hint="Atualize o snapshot ou selecione outro período." />
        </Card>
      )}

      {/* Destaques */}
      {highlightEntries.length > 0 && (
        <Card label="destaques">
          <div className={page.tiles}>
            {highlightEntries.map(([k, v]) => (
              <StatTile key={k} label={humanize(k)} value={renderValue(v)} big={false} />
            ))}
          </div>
        </Card>
      )}

      {/* Rankings (arrays de objetos) */}
      <div className={page.split}>
        {Object.entries(rankings)
          .filter(([, v]) => Array.isArray(v) && (v as unknown[]).length > 0)
          .map(([key, v]) => (
            <RankingCard key={key} title={humanize(key)} rows={v as Record<string, unknown>[]} />
          ))}
      </div>
    </div>
  );
}

function RankingCard({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  const cols = Object.keys(rows[0] ?? {}).slice(0, 4);
  return (
    <Card label={title} padded={false}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--fs-small)" }}>
          <thead>
            <tr>
              {cols.map((c) => (
                <th
                  key={c}
                  style={{
                    textAlign: "left",
                    padding: "var(--sp-2) var(--sp-3)",
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--fs-label)",
                    textTransform: "uppercase",
                    letterSpacing: "var(--track-mid)",
                    color: "var(--text-lo)",
                    borderBottom: "1px solid var(--border-strong)",
                  }}
                >
                  {humanize(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 6).map((r, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td
                    key={c}
                    style={{
                      padding: "var(--sp-2) var(--sp-3)",
                      borderBottom: "1px solid var(--border)",
                      color: "var(--text-mid)",
                      fontFamily: typeof r[c] === "number" ? "var(--font-mono)" : "inherit",
                    }}
                  >
                    {renderValue(r[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
