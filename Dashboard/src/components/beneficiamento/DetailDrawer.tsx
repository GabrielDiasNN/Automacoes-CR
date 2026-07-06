import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Factory } from "lucide-react";
import {
  orchestratorApi,
  type BeneficiamentoDetail,
  type BeneficiamentoDetailRecord,
  type BeneficiamentoOverviewParams,
  type BeneficiamentoTargetType,
  type BeneficiamentoTraceFase,
} from "../../api/orchestrator";
import { Card, DataTable, Drawer, EmptyState, ErrorState, Loading, StatTile, type Column } from "../ui";
import { formatNumber, formatPercent } from "../../lib/format";
import styles from "./DetailDrawer.module.css";

export interface DetailDrawerRequest {
  targetType: BeneficiamentoTargetType;
  label: string;
  maquina?: string;
  fase?: string;
  turno?: string;
  alternativo?: string;
  ob?: string;
}

interface DetailDrawerProps {
  request: DetailDrawerRequest | null;
  contextFilters: Pick<BeneficiamentoOverviewParams, "dt_inicio" | "dt_fim" | "q">;
  onClose: () => void;
}

const LIMIT = 20;

const RECORD_COLUMNS: Column<BeneficiamentoDetailRecord>[] = [
  { key: "ob", header: "OB", render: (r) => r.ob ?? "—" },
  { key: "data_fim", header: "Fim", render: (r) => r.data_fim ?? "—", hideOnNarrow: true },
  { key: "fase", header: "Fase", render: (r) => r.fase ?? "—" },
  { key: "maquina", header: "Máquina", render: (r) => r.maquina ?? "—", hideOnNarrow: true },
  { key: "turno", header: "Turno", render: (r) => r.turno },
  { key: "produto", header: "Produto", render: (r) => r.produto ?? r.reduz ?? "—" },
  { key: "kg", header: "KG", align: "right", render: (r) => formatNumber(r.kg) },
  {
    key: "desvio_min",
    header: "Desvio (min)",
    align: "right",
    render: (r) => formatNumber(r.desvio_min),
    hideOnNarrow: true,
  },
  { key: "reprocesso", header: "Reproc.", align: "center", render: (r) => (r.reprocesso ? "sim" : "não") },
];

const TRACE_COLUMNS: Column<BeneficiamentoTraceFase>[] = [
  { key: "seq", header: "Seq", render: (f) => f.seq },
  { key: "data_fim", header: "Fim", render: (f) => f.data_fim ?? "—" },
  { key: "fase", header: "Fase", render: (f) => f.fase ?? "—" },
  { key: "maquina", header: "Máquina", render: (f) => f.maquina ?? "—" },
  { key: "turno", header: "Turno", render: (f) => f.turno },
  { key: "kg", header: "KG", align: "right", render: (f) => formatNumber(f.kg) },
  { key: "reprocesso", header: "Reproc.", align: "center", render: (f) => (f.reprocesso ? "sim" : "não") },
];

function buildDetailParams(
  request: DetailDrawerRequest,
  contextFilters: DetailDrawerProps["contextFilters"],
  page: number,
) {
  return {
    target_type: request.targetType,
    maquina: request.maquina,
    fase: request.fase,
    turno: request.turno,
    alternativo: request.alternativo,
    ob: request.ob,
    dt_inicio: contextFilters.dt_inicio,
    dt_fim: contextFilters.dt_fim,
    q: contextFilters.q,
    page,
    limit: LIMIT,
  };
}

function TraceView({ trace }: { trace: BeneficiamentoDetail["trace"] }) {
  if (trace.length === 0) {
    return <EmptyState icon={<Factory size={20} />} title="Sem trace" hint="Nenhuma fase encontrada para esta OB." />;
  }
  return (
    <div className={styles.trace}>
      {trace.map((item) => (
        <Card key={item.ob} label={`OB ${item.ob}`} padded={false}>
          <DataTable columns={TRACE_COLUMNS} rows={item.fases} rowKey={(f) => `${item.ob}-${f.seq}`} />
        </Card>
      ))}
    </div>
  );
}

/** Painel de drill-down do Beneficiamento — consome /api/beneficiamento/detail sob demanda. */
export function DetailDrawer({ request, contextFilters, onClose }: DetailDrawerProps) {
  const [data, setData] = useState<BeneficiamentoDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
    setData(null);
  }, [request]);

  useEffect(() => {
    if (!request) return undefined;
    let cancelled = false;
    setLoading(true);
    orchestratorApi
      .getBeneficiamentoDetail(buildDetailParams(request, contextFilters, page))
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request, page]);

  return (
    <Drawer open={request != null} onClose={onClose} eyebrow="// drill-down" title={request?.label ?? ""} width={720}>
      {loading && !data && <Loading label="carregando detalhe" />}
      {error && <ErrorState message={error} />}
      {data && (
        <div className={styles.body}>
          <div className={styles.tiles}>
            <StatTile label="OBs distintas" value={formatNumber(data.summary.ob_distintas)} />
            <StatTile label="Fases" value={formatNumber(data.summary.fases_concluidas)} />
            <StatTile label="KG total" value={formatNumber(data.summary.kg_total)} />
            <StatTile label="Eficiência" value={formatPercent(data.summary.eficiencia_tempo_pct, 1)} />
            <StatTile label="Reprocesso" value={formatPercent(data.summary.reprocesso_kg_pct, 1)} />
            <StatTile label="Produtividade kg/h" value={formatNumber(data.summary.produtividade_kg_h)} />
          </div>

          {request?.targetType === "ob" ? (
            <TraceView trace={data.trace} />
          ) : data.records.length === 0 ? (
            <EmptyState icon={<Factory size={20} />} title="Sem registros" hint="Ajuste os filtros para ver o detalhe." />
          ) : (
            <Card padded={false}>
              <DataTable columns={RECORD_COLUMNS} rows={data.records} rowKey={(r) => `${r.ob}-${r.seq}`} />
            </Card>
          )}

          {data.pagination.pages > 1 && (
            <div className={styles.pager}>
              <button
                className={styles.pagerBtn}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                aria-label="Página anterior"
              >
                <ChevronLeft size={16} />
              </button>
              <span className={styles.pagerLabel}>
                página {data.pagination.page} de {data.pagination.pages} · {formatNumber(data.pagination.total)} registros
              </span>
              <button
                className={styles.pagerBtn}
                onClick={() => setPage((p) => Math.min(data.pagination.pages, p + 1))}
                disabled={page >= data.pagination.pages}
                aria-label="Próxima página"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
