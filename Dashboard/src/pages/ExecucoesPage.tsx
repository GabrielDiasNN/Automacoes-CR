import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { RotateCw, Square, RefreshCw } from "lucide-react";
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
  Pager,
  Select,
  StatusTag,
  useToast,
  type Column,
} from "../components/ui";
import { useAction } from "../hooks/useAction";
import { usePolling } from "../hooks/usePolling";
import { executionTone, severityTone, toneVar } from "../lib/status";
import { formatDuration, shortId } from "../lib/format";
import { ExecDetailBody } from "./ExecucoesPage.ExecDetailBody";
import page from "./page.module.css";
import { errMessage } from "../lib/errors";

const STATUS_OPTIONS = ["", "PENDING", "RUNNING", "SUCCESS", "ERROR", "TIMEOUT", "TERMINATED", "EXPIRED"];
const PER_PAGE = 25;

export function ExecucoesPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState(() => searchParams.get("status") ?? "");
  // Vem do card de Automações ("ver execuções") — filtra sem exigir que o
  // operador conheça o nome exato para digitar em algum campo de busca.
  // `setAutomationId` (não só o valor inicial) é necessário para o botão
  // "Limpar filtro" funcionar: `navigate()` sozinho muda a URL, mas não
  // remonta este componente (mesma rota), então um automationId lido só
  // uma vez no initializer nunca seria atualizado.
  const [automationId, setAutomationId] = useState<number | undefined>(() => {
    const raw = searchParams.get("automation_id");
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) ? n : undefined;
  });
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
          automation_id: automationId,
        },
        signal,
      ),
    [pageNum, status, automationId],
  );
  const {
    data,
    loading,
    error: err,
    refresh: load,
    lastUpdated,
    rateLimitedUntil,
    refreshQueued,
  } = usePolling<Paginated<ExecutionSummary>>(fetchExecutions, 8_000, [pageNum, status, automationId]);

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
        toast(errMessage(e), "red");
        setDetail(null);
      } finally {
        if (isLatest()) setDetailLoading(false);
      }
    },
    [toast],
  );

  const { run: runExecAction } = useAction<string>();

  const doStop = useCallback(
    (id: string) => {
      setConfirmStop(null);
      void runExecAction(id, () => orchestratorApi.stopExecution(id), {
        overrideMessage: `Parada solicitada para ${shortId(id)}`,
        successTone: "amber",
        onDone: load,
      });
    },
    [runExecAction, load],
  );

  const doRequeue = useCallback(
    (id: string) => {
      void runExecAction(id, () => orchestratorApi.requeueExecution(id, { reason: "Reenfileirado pelo operador" }), {
        overrideMessage: `Reenfileirado: ${shortId(id)}`,
        onDone: load,
      });
    },
    [runExecAction, load],
  );

  // useMemo: sem isso, 8 colunas (cada uma com uma closure de render) eram
  // recriadas a cada render — a página faz polling a cada 8s, então isso
  // reconstruía o array inteiro a cada tick sem necessidade (achado nº 31,
  // Onda 5).
  const columns: Column<ExecutionSummary>[] = useMemo(
    () => [
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
      // O stopPropagation manual que existia aqui foi removido: DataTable
      // agora ignora clique/Enter cujo alvo esteja dentro de um controle
      // interativo (ver components/ui/DataTable.tsx) — a correção mora na
      // origem, não em cada consumidor lembrar de tratar o próprio caso.
      render: (r) => (
        <span style={{ display: "inline-flex", gap: 6, justifyContent: "flex-end" }}>
          {/* aria-label com o id da execução: sem isso, N linhas produzem N
           *  botões "Parar"/"Reenfileirar" idênticos para leitor de tela, numa
           *  ação destrutiva em produção que precisa ser inequívoca. */}
          {r.stop_allowed && (
            <Button
              size="sm"
              variant="danger"
              icon={<Square size={12} />}
              aria-label={`Parar execução ${shortId(r.id)}`}
              onClick={() => setConfirmStop(r.id)}
            >
              Parar
            </Button>
          )}
          {r.requeue_allowed && (
            <Button
              size="sm"
              variant="primary"
              icon={<RotateCw size={12} />}
              aria-label={`Reenfileirar execução ${shortId(r.id)}`}
              onClick={() => doRequeue(r.id)}
            >
              Reenfileirar
            </Button>
          )}
        </span>
      ),
    },
    ],
    [doRequeue],
  );

  const totalPages = data?.pages ?? 1;

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="// operação"
        title="Execuções"
        actions={
          <div className={page.toolbar}>
            {automationId != null && (
              <StatusTag tone="cyan" dot>
                {data?.items[0]?.automation_name ?? `automação #${automationId}`}
                <button
                  type="button"
                  onClick={() => {
                    setAutomationId(undefined);
                    setPageNum(1);
                    void navigate("/execucoes");
                  }}
                  aria-label="Limpar filtro de automação"
                  style={{
                    marginLeft: 6,
                    border: "none",
                    background: "none",
                    color: "inherit",
                    cursor: "pointer",
                    font: "inherit",
                    padding: 0,
                  }}
                >
                  ✕
                </button>
              </StatusTag>
            )}
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
            <FreshnessTag
              lastUpdated={lastUpdated}
              error={data && err ? err : null}
              rateLimitedUntil={rateLimitedUntil}
              refreshQueued={refreshQueued}
            />
            <Button size="sm" icon={<RefreshCw size={13} />} onClick={() => void load()}>
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
            onRowClick={(r) => void openDetail(r.id)}
            rowTone={(r) => (r.operator_attention_required ? toneVar[severityTone(r.operator_severity)] : undefined)}
          />
        )}
      </Card>

      <Pager
        page={data?.page ?? 1}
        pages={totalPages}
        currentPage={pageNum}
        total={data?.total ?? 0}
        itemLabel="execuções"
        onPrev={() => setPageNum((p) => p - 1)}
        onNext={() => setPageNum((p) => p + 1)}
      />

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
