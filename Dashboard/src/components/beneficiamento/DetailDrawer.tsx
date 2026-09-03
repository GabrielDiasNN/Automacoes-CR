import { useCallback, useEffect, useRef, useState } from "react";
import { Factory } from "lucide-react";
import {
  orchestratorApi,
  type BeneficiamentoDetail,
  type BeneficiamentoDetailRecord,
  type BeneficiamentoOverviewParams,
  type BeneficiamentoTargetType,
  type BeneficiamentoTraceFase,
} from "../../api/orchestrator";
import { Card, DataTable, Drawer, EmptyState, ErrorState, Loading, Pager, StatTile, type Column } from "../ui";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { formatDateTimeBr, formatNumber, formatPercent } from "../../lib/format";
import styles from "./DetailDrawer.module.css";

/** Desvio relativo ao tempo previsto — normaliza fases curtas vs longas (ver análise em conversa). */
function desvioPct(minReal: number, minPrev: number): number | null {
  if (!minPrev) return null;
  return ((minReal - minPrev) / minPrev) * 100;
}

function DesvioCell({ minReal, minPrev }: { minReal: number; minPrev: number }) {
  const pct = desvioPct(minReal, minPrev);
  if (pct == null) return <span>—</span>;
  const abs = Math.abs(pct);
  const tone = abs > 30 ? styles.desvioRed : abs > 15 ? styles.desvioAmber : undefined;
  return (
    <span className={tone} title={`${formatNumber(minReal)} min reais vs ${formatNumber(minPrev)} min previstos`}>
      {pct > 0 ? "+" : ""}
      {pct.toFixed(0)}%
    </span>
  );
}

export interface DetailDrawerRequest {
  targetType: BeneficiamentoTargetType;
  label: string;
  maquina?: string;
  fase?: string;
  turno?: string;
  alternativo?: string;
  ob?: string;
  setor?: string;
  grupoFase?: string;
  tipoMaquina?: string;
}

interface DetailDrawerProps {
  request: DetailDrawerRequest | null;
  contextFilters: Pick<BeneficiamentoOverviewParams, "dt_inicio" | "dt_fim" | "q">;
  onClose: () => void;
}

const LIMIT = 20;

const RECORD_COLUMNS: Column<BeneficiamentoDetailRecord>[] = [
  { key: "ob", header: "OB", render: (r) => r.ob ?? "—" },
  { key: "data_fim", header: "Fim", render: (r) => formatDateTimeBr(r.data_fim), hideOnNarrow: true },
  { key: "fase", header: "Fase", render: (r) => r.fase ?? "—" },
  { key: "maquina", header: "Máquina", render: (r) => r.maquina ?? "—", hideOnNarrow: true },
  { key: "turno", header: "Turno", render: (r) => r.turno },
  { key: "produto", header: "Produto", render: (r) => r.produto ?? r.reduz ?? "—" },
  { key: "kg", header: "KG", align: "right", render: (r) => formatNumber(r.kg) },
  { key: "mt", header: "MT", align: "right", render: (r) => formatNumber(r.mt), hideOnNarrow: true },
  {
    key: "pecas",
    header: "Peças (OB)",
    align: "right",
    render: (r) => {
      const pecas = r.pecas_destino ?? r.pecas_origem;
      if (pecas == null) return "—";
      return (
        <span title={`Origem: ${r.pecas_origem ?? "—"} peças / ${formatNumber(r.kg_origem_real)} kg · Destino: ${r.pecas_destino ?? "—"} peças / ${formatNumber(r.kg_destino_real)} kg`}>
          {formatNumber(pecas)}
        </span>
      );
    },
    hideOnNarrow: true,
  },
  {
    key: "desvio_pct",
    header: "Desvio",
    align: "right",
    render: (r) => <DesvioCell minReal={r.min_real} minPrev={r.min_prev} />,
    hideOnNarrow: true,
  },
  { key: "reprocesso", header: "Reproc.", align: "center", render: (r) => (r.reprocesso ? "sim" : "não") },
];

const TRACE_COLUMNS: Column<BeneficiamentoTraceFase>[] = [
  { key: "seq", header: "Seq", render: (f) => f.seq },
  { key: "data_fim", header: "Fim", render: (f) => formatDateTimeBr(f.data_fim) },
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
    setor: request.setor,
    grupo_fase: request.grupoFase,
    tipo_maquina: request.tipoMaquina,
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
  const [page, setPage] = useState(1);

  // Instante da última troca de ALVO (não de página/filtro) — usado abaixo
  // para não exibir `data` que ainda pertence ao alvo anterior. Necessário
  // porque `useAsyncResource` reaproveita `usePolling`, que mantém o último
  // dado válido em tela durante um refresh (proposital, evita flicker) e
  // pula a requisição inteira — inclusive a de `fetcher: null` disparada ao
  // fechar/trocar o drawer — enquanto uma janela de backoff de 429 estiver
  // ativa (`blockedUntilRef` em usePolling.ts). Sem isso, trocar de alvo
  // durante essa janela deixava os registros do alvo ANTERIOR visíveis sob
  // o título do alvo NOVO (achado de revisão de código).
  const requestChangedAtRef = useRef(Date.now());

  useEffect(() => {
    setPage(1);
    requestChangedAtRef.current = Date.now();
  }, [request]);

  const fetchDetail = useCallback(
    (signal?: AbortSignal) => orchestratorApi.getBeneficiamentoDetail(buildDetailParams(request!, contextFilters, page), signal),
    [request, contextFilters, page],
  );
  // `contextFilters` agora entra nas deps — antes (eslint-disable manual)
  // mudar o filtro de contexto com o drawer aberto não refazia o fetch
  // (achado nº 14, Onda 4). `fetcher: null` (não `request` como argumento)
  // é o que desliga o fetch quando o drawer está fechado.
  const { data, loading, error, lastUpdated } = useAsyncResource(request ? fetchDetail : null, [request, contextFilters, page]);

  // `data` só corresponde ao `request` atual se a última resposta chegou
  // DEPOIS da troca de alvo — do contrário é resultado do alvo anterior,
  // ainda não invalidado (ver comentário no ref acima).
  const isStale = data != null && (lastUpdated == null || lastUpdated.getTime() < requestChangedAtRef.current);
  const visibleData = isStale ? null : data;

  return (
    <Drawer open={request != null} onClose={onClose} eyebrow="// drill-down" title={request?.label ?? ""} width={1080}>
      {loading && !visibleData && <Loading label="carregando detalhe" />}
      {error && <ErrorState message={error} />}
      {visibleData && (
        <div className={styles.body}>
          <div className={styles.tiles}>
            <StatTile label="OBs distintas" value={formatNumber(visibleData.summary.ob_distintas)} />
            <StatTile label="Fases" value={formatNumber(visibleData.summary.fases_concluidas)} />
            <StatTile label="KG total" value={formatNumber(visibleData.summary.kg_total)} />
            <StatTile label="Eficiência" value={formatPercent(visibleData.summary.eficiencia_tempo_pct, 1)} />
            <StatTile label="Reprocesso" value={formatPercent(visibleData.summary.reprocesso_kg_pct, 1)} />
            <StatTile label="Produtividade kg/h" value={formatNumber(visibleData.summary.produtividade_kg_h)} />
          </div>

          {request?.targetType === "ob" ? (
            <TraceView trace={visibleData.trace} />
          ) : visibleData.records.length === 0 ? (
            <EmptyState icon={<Factory size={20} />} title="Sem registros" hint="Ajuste os filtros para ver o detalhe." />
          ) : (
            <Card padded={false}>
              <DataTable columns={RECORD_COLUMNS} rows={visibleData.records} rowKey={(r) => `${r.ob}-${r.seq}`} />
            </Card>
          )}

          {visibleData.pagination.pages > 1 && (
            <Pager
              page={visibleData.pagination.page}
              pages={visibleData.pagination.pages}
              currentPage={page}
              total={visibleData.pagination.total}
              itemLabel="registros"
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => Math.min(visibleData.pagination.pages, p + 1))}
            />
          )}
        </div>
      )}
    </Drawer>
  );
}
