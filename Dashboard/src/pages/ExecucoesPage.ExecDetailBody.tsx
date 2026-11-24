import { useMemo, useState } from "react";
import { ClipboardList, Download, FileText, RotateCw, Square } from "lucide-react";
import {
  orchestratorApi,
  type ExecutionDetail,
  type ExecutionSummary,
  type PromovidaResumo,
  type PromovidaSnapshot,
} from "../api/orchestrator";
import {
  Button,
  Card,
  DataTable,
  DescriptionList,
  EmptyState,
  KeyValue,
  ListRow,
  Loading,
  LogViewer,
  StatTile,
  StatusTag,
  Tabs,
  type Column,
  type TabItem,
} from "../components/ui";
import { CardGallery } from "../components/CardGallery";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { executionTone, severityTone } from "../lib/status";
import { formatDuration, formatNumber, shortId } from "../lib/format";
import page from "./page.module.css";

type DrawerTab = "logs" | "resultado";

function formatCell(val: unknown): string {
  if (val === null || val === undefined || val === "") return "—";
  if (typeof val === "number") return formatNumber(val);
  return String(val);
}

export function ExecDetailBody({
  detail,
  loading,
  logsText,
  logsLive,
  artifacts,
  artifactsLoading,
  onDownloadArtifact,
  relatedExecutions,
  relatedLoading,
  onSelectRelated,
  onStop,
  onRequeue,
}: {
  detail: ExecutionDetail;
  loading: boolean;
  /** Texto a mostrar no LogViewer — REST (`detail.logs`) ou o acumulado do
   *  WebSocket `/ws/logs/{exec_id}` quando a execução está RUNNING. */
  logsText: string;
  /** WS de log ao vivo conectado e aberto agora. */
  logsLive: boolean;
  artifacts: string[];
  artifactsLoading: boolean;
  onDownloadArtifact: (filename: string) => void;
  /** Últimas execuções da MESMA automação (exclui a própria `detail`). */
  relatedExecutions: ExecutionSummary[];
  relatedLoading: boolean;
  onSelectRelated: (id: string) => void;
  onStop: () => void;
  onRequeue: () => void;
}) {
  const [tab, setTab] = useState<DrawerTab>("logs");

  const promovidasRes = useAsyncResource<{ items: PromovidaResumo[] } | null>(
    tab === "resultado"
      ? (signal) => orchestratorApi.getPromovidas(signal).catch(() => null)
      : null,
    [tab],
  );

  const matchedItem = useMemo(() => {
    const items = promovidasRes.data?.items ?? [];
    const autoName = (detail.automation_name ?? "").toLowerCase();
    if (!autoName) return null;
    return (
      items.find((i) => (i.automation_name ?? i.nome).toLowerCase() === autoName) ??
      items.find((i) => i.nome.toLowerCase() === autoName) ??
      null
    );
  }, [promovidasRes.data, detail.automation_name]);

  const snapRes = useAsyncResource<PromovidaSnapshot | null>(
    tab === "resultado" && matchedItem?.has_snapshot
      ? (signal) => orchestratorApi.getPromovidaLatest(matchedItem.slug, signal).catch(() => null)
      : null,
    [tab, matchedItem?.slug, matchedItem?.has_snapshot],
  );

  const previewRows = useMemo(() => (snapRes.data?.rows ?? []).slice(0, 15), [snapRes.data]);
  const previewRowKeys = useMemo(
    () => new Map(previewRows.map((row, idx) => [row, `${snapRes.data?.slug ?? "snap"}-${idx}`])),
    [previewRows, snapRes.data?.slug],
  );
  const previewCols = useMemo<Column<Record<string, unknown>>[]>(() => {
    const cols = (snapRes.data?.columns ?? []).slice(0, 6);
    return cols.map((col) => ({
      key: col,
      header: col.replace(/_/g, " "),
      render: (row) => formatCell(row[col]),
    }));
  }, [snapRes.data]);

  const tabItems: TabItem<DrawerTab>[] = [
    { id: "logs", label: "Log Técnico & Artefatos", icon: <FileText size={14} /> },
    { id: "resultado", label: "Resultado de Negócio & Cards PNG", icon: <ClipboardList size={14} /> },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <div style={{ display: "flex", gap: "var(--sp-2)", flexWrap: "wrap", alignItems: "center" }}>
        <StatusTag tone={executionTone(detail.status)} dot pulse={detail.status === "RUNNING"}>
          {detail.status}
        </StatusTag>
        {detail.operator_attention_required && detail.operator_severity && (
          <StatusTag tone={severityTone(detail.operator_severity)}>
            {detail.operator_severity} · {detail.operator_score}
          </StatusTag>
        )}
        {detail.priority && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)" }}>
            prio {detail.priority}
          </span>
        )}
      </div>

      {detail.operator_reason_summary && (
        <Card label="motivo da atenção" alert>
          <span style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
            {detail.operator_reason_summary.split("|").join(" · ")}
          </span>
        </Card>
      )}

      <DescriptionList>
        <KeyValue k="Início" v={detail.started_at} />
        <KeyValue k="Fim" v={detail.finished_at ?? "—"} />
        <KeyValue k="Duração" v={formatDuration(detail.duration_seconds)} />
        <KeyValue k="Fila" v={detail.queue_group ?? "—"} />
        <KeyValue k="Tentativas" v={`${detail.retry_count}/${detail.max_retries}`} />
        <KeyValue k="Solicitado por" v={detail.requested_by ?? "—"} />
        {detail.exit_code != null && <KeyValue k="Exit code" v={String(detail.exit_code)} />}
        {detail.failure_reason && <KeyValue k="Falha" v={detail.failure_reason} />}
      </DescriptionList>

      {(detail.stop_allowed || detail.requeue_allowed) && (
        <div style={{ display: "flex", gap: "var(--sp-2)" }}>
          {detail.stop_allowed && (
            <Button variant="danger" icon={<Square size={13} />} onClick={onStop}>
              Parar
            </Button>
          )}
          {detail.requeue_allowed && (
            <Button variant="primary" icon={<RotateCw size={13} />} onClick={onRequeue}>
              Reenfileirar
            </Button>
          )}
        </div>
      )}

      <Tabs
        items={tabItems}
        activeId={tab}
        onChange={setTab}
        ariaLabel="Visões do detalhe da execução"
      />

      {tab === "logs" ? (
        <>
          <div>
            <div className={page.sectionLabel}>artefatos</div>
            {artifactsLoading && artifacts.length === 0 ? (
              <span style={{ fontSize: "var(--fs-small)", color: "var(--text-lo)" }}>carregando…</span>
            ) : artifacts.length === 0 ? (
              <span style={{ fontSize: "var(--fs-small)", color: "var(--text-lo)" }}>nenhum artefato gerado</span>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "var(--sp-1)" }}>
                {artifacts.map((filename) => (
                  <Button
                    key={filename}
                    size="sm"
                    variant="ghost"
                    icon={<Download size={13} />}
                    onClick={() => onDownloadArtifact(filename)}
                  >
                    {filename}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {(relatedLoading || relatedExecutions.length > 0) && (
            <div>
              <div className={page.sectionLabel}>outras execuções desta automação</div>
              {relatedLoading && relatedExecutions.length === 0 ? (
                <span style={{ fontSize: "var(--fs-small)", color: "var(--text-lo)" }}>carregando…</span>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  {relatedExecutions.map((ex) => (
                    <ListRow
                      key={ex.id}
                      onClick={() => onSelectRelated(ex.id)}
                      aria-label={`Abrir execução ${shortId(ex.id)}, status ${ex.status}`}
                      leading={
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-lo)" }}>
                          {shortId(ex.id, 12)}
                        </span>
                      }
                      trailing={
                        <StatusTag tone={executionTone(ex.status)} dot pulse={ex.status === "RUNNING"}>
                          {ex.status}
                        </StatusTag>
                      }
                    >
                      {ex.started_at}
                    </ListRow>
                  ))}
                </div>
              )}
            </div>
          )}

          <div>
            <div className={page.toolbar} style={{ marginBottom: "var(--sp-1)" }}>
              <div className={page.sectionLabel} style={{ margin: 0 }}>
                logs
              </div>
              {logsLive && (
                <StatusTag tone="cyan" dot pulse>
                  ao vivo
                </StatusTag>
              )}
            </div>
            <LogViewer text={logsText} loading={loading} />
          </div>
        </>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          {(promovidasRes.loading || snapRes.loading) && !snapRes.data ? (
            <Loading label="Carregando resultado de negócio" />
          ) : !snapRes.data ? (
            <EmptyState
              icon={<ClipboardList size={24} />}
              title="Sem snapshot tabular vinculado"
              hint="Esta automação ainda não gerou snapshot local ou não possui extração tabular vinculada."
            />
          ) : (
            <>
              <div className={page.tiles}>
                <StatTile label="Registros" value={formatNumber(snapRes.data.total_rows)} />
                <StatTile
                  label="Exceções"
                  value={formatNumber(snapRes.data.excecoes_count)}
                  tone={snapRes.data.excecoes_count > 0 ? "amber" : "green"}
                />
                <StatTile label="Cards PNG" value={snapRes.data.cards?.length ?? 0} tone="blue" />
              </div>

              {(snapRes.data.cards ?? []).length > 0 && (
                <Card label="Cards PNG gerados">
                  <CardGallery slug={snapRes.data.slug} cards={snapRes.data.cards ?? []} />
                </Card>
              )}

              {previewRows.length > 0 && previewCols.length > 0 && (
                <Card label={`Amostra do último resultado (${previewRows.length} de ${snapRes.data.total_rows})`}>
                  <DataTable
                    columns={previewCols}
                    rows={previewRows}
                    rowKey={(row) => previewRowKeys.get(row) ?? ""}
                  />
                </Card>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
