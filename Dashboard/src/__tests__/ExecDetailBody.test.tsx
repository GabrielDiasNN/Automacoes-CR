import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi, type ExecutionDetail } from "../api/orchestrator";
import { TableDensityProvider } from "../context/TableDensityContext";
import { ExecDetailBody } from "../pages/ExecucoesPage.ExecDetailBody";

const DETAIL: ExecutionDetail = {
  id: "EXEC_TEST_1",
  automation_id: 4,
  automation_name: "OBs Paradas Fase",
  status: "SUCCESS",
  priority: "HIGH",
  retry_count: 0,
  max_retries: 2,
  queue_group: "oracle",
  failure_reason: null,
  recovery_action: null,
  exit_code: 0,
  requested_by: "OPERATOR",
  started_at: "22/11/2026 14:00:00",
  finished_at: "22/11/2026 14:00:05",
  duration_seconds: 5,
  operator_attention_required: false,
  operator_severity: null,
  operator_score: 0,
  operator_reason_summary: null,
  operator_action_code: null,
  operator_action_label: null,
  operator_action_hint: null,
  requeue_allowed: true,
  requeue_block_reason: null,
  stop_allowed: false,
  related_execution_id: null,
  related_execution_status: null,
  related_queue_group: null,
  logs: "[INFO] 250 linhas",
  artifacts: null,
  claimed_at: null,
  worker_instance_id: null,
  worker_pid: null,
};

describe("ExecDetailBody — log técnico e resultado de negócio", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("alterna para a aba Resultado de Negócio & Cards PNG e carrega snapshot", async () => {
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
      items: [
        {
          slug: "obs-paradas-fase",
          nome: "OBs Paradas Fase",
          titulo: "OBs Paradas Fase",
          automation_name: "OBs Paradas Fase",
          modo: "producao",
          destinos: ["dashboard"],
          has_snapshot: true,
          generated_at: "2026-11-22T14:00:00Z",
          age_minutes: 5,
          total_rows: 1,
          excecoes_count: 1,
          kpis: { count: 1 },
        },
      ],
    });
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue({
      slug: "obs-paradas-fase",
      nome: "OBs Paradas Fase",
      titulo: "OBs Paradas Fase",
      modo: "producao",
      generated_at: "2026-11-22T14:00:00Z",
      age_minutes: 5,
      total_rows: 1,
      excecoes_count: 1,
      kpis: { count: 1 },
      columns: ["NUMERO_OB", "FASE_ATUAL"],
      rows: [{ NUMERO_OB: 192006, FASE_ATUAL: "FELPAGEM" }],
      cards: [],
    });

    render(
      <TableDensityProvider>
        <ExecDetailBody
          detail={DETAIL}
          loading={false}
          logsText="[INFO] 250 linhas"
          logsLive={false}
          artifacts={[]}
          artifactsLoading={false}
          onDownloadArtifact={vi.fn()}
          relatedExecutions={[]}
          relatedLoading={false}
          onSelectRelated={vi.fn()}
          onStop={vi.fn()}
          onRequeue={vi.fn()}
        />
      </TableDensityProvider>,
    );

    expect(screen.getByText("[INFO] 250 linhas")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Resultado de Negócio & Cards PNG/ }));
    expect(await screen.findByText("FELPAGEM")).toBeInTheDocument();
  });
});
