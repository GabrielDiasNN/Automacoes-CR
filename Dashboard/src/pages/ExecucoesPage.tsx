import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, RotateCw, Square, RefreshCw } from "lucide-react";
import { orchestratorApi, type ExecutionDetail, type ExecutionSummary, type Paginated } from "../api/orchestrator";
import {
  Button,
  Card,
  ConfirmModal,
  DataTable,
  Drawer,
  ErrorState,
  FreshnessTag,
  Loading,
  Nameplate,
  Select,
  StatusTag,
  useToast,
  type Column,
} from "../components/ui";
import { usePolling } from "../hooks/usePolling";
import { executionTone, severityTone, toneVar } from "../lib/status";
import { formatDuration, shortId } from "../lib/format";
import { ExecDetailBody } from "./ExecucoesPage.ExecDetailBody";
import page from "./page.module.css";

const STATUS_OPTIONS = ["", "PENDING", "RUNNING", "SUCCESS", "ERROR", "TIMEOUT", "TERMINATED", "EXPIRED"];
const PER_PAGE = 25;

export function ExecucoesPage() {
  const toast = useToast();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState(() => searchParams.get("status") ?? "");
  const [pageNum, setPageNum] = useState(1);

  const [detail, setDetail] = useState<(Partial<ExecutionDetail> & { id: string }) | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [confirmStop, setConfirmStop] = useState<string | null>(null);

  // Guarda de sequência + AbortController, mesmo padrão do `usePolling`: sem
  // isso, clicar em A e depois em B antes da resposta de A chegar podia fazer
  // `setDetail(dA)` rodar por último — o operador acabava confirmando "Parar" /
  // "Reenfileirar" sobre A tendo aberto B (ação em automação de produção).
  const detailSeqRef = useRef(0);
  const detailAbortRef = useRef<AbortController | null>(null);
  useEffect(() => () => detailAbortRef.current?.abort(), []);

  const fetchExecutions = useCallback(
    (signal?: AbortSignal) =>
      orchestratorApi.listExecutions(
        {
          page: pageNum,
          per_page: PER_PAGE,
          status: status || undefined,
        },
        signal,
      ),
    [pageNum, status],
  );
  const {
    data,
    loading,
    error: err,
    refresh: load,
    lastUpdated,
    rateLimitedUntil,
  } = usePolling<Paginated<ExecutionSummary>>(fetchExecutions, 8_000, [pageNum, status]);

  const openDetail = useCallback(
    async (id: string) => {
      const seq = ++detailSeqRef.current;
      const isLatest = () => detailSeqRef.current === seq;
      detailAbortRef.current?.abort();
      const controller = new AbortController();
      detailAbortRef.current = controller;

      setDetailLoading(true);
      setDetail({ id });
      try {
        const d = await orchestratorApi.getExecution(id, controller.signal);
        if (!isLatest()) return;
        setDetail(d);
      } catch (e) {
        if (controller.signal.aborted || (e instanceof Error && e.name === "AbortError")) return;
        if (!isLatest()) return;
        toast(e instanceof Error ? e.message : String(e), "red");
        setDetail(null);
      } finally {
        if (isLatest()) setDetailLoading(false);
      }
    },
    [toast],
  );

  const doStop = useCallback(
    async (id: string) => {
      setConfirmStop(null);
      try {
        await orchestratorApi.stopExecution(id);
        toast(`Parada solicitada para ${shortId(id)}`, "amber");
        load();
      } catch (e) {
        toast(e instanceof Error ? e.message : String(e), "red");
      }
    },
    [toast, load],
  );

  const doRequeue = useCallback(
    async (id: string) => {
      try {
        await orchestratorApi.requeueExecution(id, { reason: "Reenfileirado pelo operador" });
        toast(`Reenfileirado: ${shortId(id)}`, "cyan");
        load();
      } catch (e) {
        toast(e instanceof Error ? e.message : String(e), "red");
      }
    },
    [toast, load],
  );

  const columns: Column<ExecutionSummary>[] = [
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <StatusTag tone={executionTone(r.status)} dot pulse={r.status === "RUNNING"}>
          {r.status}
        </StatusTag>
      ),
    },
    {
      key: "id",
      header: "ID",
      render: (r) => <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-lo)" }}>{shortId(r.id)}</span>,
      hideOnNarrow: true,
    },
    {
      key: "auto",
      header: "Automação",
      render: (r) => <span style={{ color: "var(--text-hi)" }}>{r.automation_name ?? `#${r.automation_id}`}</span>,
    },
    {
      key: "sev",
      header: "Operador",
      render: (r) =>
        r.operator_attention_required && r.operator_severity ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <StatusTag tone={severityTone(r.operator_severity)}>{r.operator_severity}</StatusTag>
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-lo)", fontSize: "var(--fs-label)" }}>
              {r.operator_score}
            </span>
          </span>
        ) : (
          <span style={{ color: "var(--text-lo)" }}>—</span>
        ),
    },
    {
      key: "queue",
      header: "Fila",
      render: (r) => <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-mid)" }}>{r.queue_group ?? "—"}</span>,
      hideOnNarrow: true,
    },
    {
      key: "started",
      header: "Início",
      render: (r) => (
        <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-mid)", fontSize: "var(--fs-label)" }}>{r.started_at}</span>
      ),
      hideOnNarrow: true,
    },
    {
      key: "dur",
      header: "Duração",
      align: "right",
      hideOnNarrow: true,
      render: (r) => <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-mid)" }}>{formatDuration(r.duration_seconds)}</span>,
    },
    {
      key: "act",
      header: "Ação",
      align: "right",
      hideOnNarrow: true,
      render: (r) => (
        <span style={{ display: "inline-flex", gap: 6, justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
          {r.stop_allowed && (
            <Button size="sm" variant="danger" icon={<Square size={12} />} onClick={() => setConfirmStop(r.id)}>
              Parar
            </Button>
          )}
          {r.requeue_allowed && (
            <Button size="sm" variant="primary" icon={<RotateCw size={12} />} onClick={() => doRequeue(r.id)}>
              Reenfileirar
            </Button>
          )}
        </span>
      ),
    },
  ];

  const totalPages = data?.pages ?? 1;

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// operação"
        title="Execuções"
        actions={
          <div className={page.toolbar}>
            <Select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPageNum(1);
              }}
              aria-label="Filtrar por status"
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s || "todos os status"}
                </option>
              ))}
            </Select>
            <FreshnessTag lastUpdated={lastUpdated} error={data && err ? err : null} rateLimitedUntil={rateLimitedUntil} />
            <Button size="sm" icon={<RefreshCw size={13} />} onClick={load}>
              Atualizar
            </Button>
          </div>
        }
      />

      <Card padded={false}>
        {loading && !data ? (
          <Loading />
        ) : err && !data ? (
          <ErrorState message={err} />
        ) : (
          <DataTable
            columns={columns}
            rows={data?.items ?? []}
            rowKey={(r) => r.id}
            onRowClick={(r) => openDetail(r.id)}
            rowTone={(r) => (r.operator_attention_required ? toneVar[severityTone(r.operator_severity)] : undefined)}
          />
        )}
      </Card>

      <div className={page.toolbar}>
        <Button size="sm" variant="subtle" icon={<ChevronLeft size={14} />} disabled={pageNum <= 1} onClick={() => setPageNum((p) => p - 1)}>
          Anterior
        </Button>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--text-lo)" }}>
          página {data?.page ?? 1} / {totalPages} · {data?.total ?? 0} execuções
        </span>
        <Button size="sm" variant="subtle" onClick={() => setPageNum((p) => p + 1)} disabled={pageNum >= totalPages}>
          Próxima <ChevronRight size={14} />
        </Button>
      </div>

      <Drawer
        open={!!detail}
        onClose={() => setDetail(null)}
        eyebrow={detail ? shortId(detail.id, 22) : ""}
        title={detail?.automation_name ?? "Execução"}
        width={860}
      >
        {detail &&
          (detail.started_at ? (
            <ExecDetailBody
              detail={detail as ExecutionDetail}
              loading={detailLoading}
              onStop={() => setConfirmStop(detail.id)}
              onRequeue={() => doRequeue(detail.id)}
            />
          ) : (
            <div style={{ padding: "var(--sp-4)" }}>
              <Loading />
            </div>
          ))}
      </Drawer>

      <ConfirmModal
        open={!!confirmStop}
        title="Parar execução"
        message={`Solicitar término da execução ${confirmStop ? shortId(confirmStop) : ""}? O processo em andamento será encerrado.`}
        confirmLabel="Parar execução"
        danger
        onConfirm={() => confirmStop && doStop(confirmStop)}
        onCancel={() => setConfirmStop(null)}
      />
    </div>
  );
}
