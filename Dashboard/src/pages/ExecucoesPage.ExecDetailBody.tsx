import { RotateCw, Square } from "lucide-react";
import type { ExecutionDetail } from "../api/orchestrator";
import { Button, Card, DescriptionList, KeyValue, LogViewer, StatusTag } from "../components/ui";
import { executionTone, severityTone } from "../lib/status";
import { formatDuration } from "../lib/format";
import page from "./page.module.css";

export function ExecDetailBody({
  detail,
  loading,
  onStop,
  onRequeue,
}: {
  detail: ExecutionDetail;
  loading: boolean;
  onStop: () => void;
  onRequeue: () => void;
}) {
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

      <div>
        <div className={page.sectionLabel}>logs</div>
        <LogViewer text={detail.logs ?? ""} loading={loading} />
      </div>
    </div>
  );
}
