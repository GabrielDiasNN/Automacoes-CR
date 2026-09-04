import { describe, expect, it } from "vitest";
import type { ExecutionStatus } from "../api/orchestrator";
import {
  criticalityTone,
  executionTone,
  healthLabel,
  healthTone,
  severityTone,
  slaTone,
} from "../lib/status";

describe("executionTone", () => {
  it("mapeia SUCCESS para verde", () => {
    expect(executionTone("SUCCESS")).toBe("green");
  });

  it("mapeia ERROR e TIMEOUT para vermelho", () => {
    expect(executionTone("ERROR")).toBe("red");
    expect(executionTone("TIMEOUT")).toBe("red");
  });

  it("mapeia RUNNING e CLAIMED para âmbar", () => {
    expect(executionTone("RUNNING")).toBe("amber");
    // "CLAIMED" não existe em ExecutionStatus (ver comentário em orchestrator.ts)
    // mas o runtime ainda o tolera por segurança — cast explícito documenta a exceção.
    expect(executionTone("CLAIMED" as ExecutionStatus)).toBe("amber");
  });

  it("mapeia PENDING para ciano", () => {
    expect(executionTone("PENDING")).toBe("cyan");
  });

  it("é case-insensitive", () => {
    expect(executionTone("success" as ExecutionStatus)).toBe("green");
  });

  it("usa cinza para status desconhecidos (TERMINATED, REQUEUED, PARTIAL)", () => {
    expect(executionTone("TERMINATED")).toBe("grey");
    expect(executionTone("PARTIAL")).toBe("grey");
  });

  it("mapeia EXPIRED para um tom próprio, distinto do cinza de desconhecidos e do vermelho de erro", () => {
    const tone = executionTone("EXPIRED");
    expect(tone).not.toBe("grey");
    expect(tone).not.toBe("red");
  });

  it("mapeia FAILED_BY_REBOOT para vermelho (falha, não estado neutro)", () => {
    expect(executionTone("FAILED_BY_REBOOT")).toBe("red");
  });

  // Teste-guarda de contrato: cobre os 10 valores reais de `ExecutionStatus`
  // (`constants.py` EXECUTION_STATUS_*) para que a próxima adição ao union
  // seja obrigada a decidir um tom em vez de cair no cinza por omissão.
  it("cobre os 10 valores de ExecutionStatus com um tom definido", () => {
    const vocabularioBackend: Record<ExecutionStatus, ReturnType<typeof executionTone>> = {
      PENDING: "cyan",
      RUNNING: "amber",
      SUCCESS: "green",
      PARTIAL: "grey",
      ERROR: "red",
      TIMEOUT: "red",
      TERMINATED: "grey",
      FAILED_BY_REBOOT: "red",
      REQUEUED: "grey",
      EXPIRED: "blue",
    };
    for (const [status, esperado] of Object.entries(vocabularioBackend) as [ExecutionStatus, string][]) {
      expect(executionTone(status)).toBe(esperado);
    }
  });
});

describe("severityTone", () => {
  it("mapeia CRITICAL para vermelho", () => {
    expect(severityTone("CRITICAL")).toBe("red");
  });

  it("mapeia HIGH para âmbar", () => {
    expect(severityTone("HIGH")).toBe("amber");
  });

  it("mapeia MODERATE para ciano", () => {
    expect(severityTone("MODERATE")).toBe("cyan");
  });

  it("usa cinza para null/undefined/desconhecido", () => {
    expect(severityTone(null)).toBe("grey");
    expect(severityTone(undefined)).toBe("grey");
    expect(severityTone("LOW")).toBe("grey");
  });
});

describe("healthTone", () => {
  it("mapeia healthy/ok para verde", () => {
    expect(healthTone("healthy")).toBe("green");
    expect(healthTone("ok")).toBe("green");
  });

  it("mapeia warning/attention/at_risk/degraded para âmbar", () => {
    expect(healthTone("warning")).toBe("amber");
    expect(healthTone("attention")).toBe("amber");
    expect(healthTone("at_risk")).toBe("amber");
    expect(healthTone("degraded")).toBe("amber");
  });

  it("mapeia critical/incident/violated/unhealthy para vermelho", () => {
    expect(healthTone("critical")).toBe("red");
    expect(healthTone("incident")).toBe("red");
    expect(healthTone("violated")).toBe("red");
    expect(healthTone("unhealthy")).toBe("red");
  });

  it("é case-insensitive", () => {
    expect(healthTone("HEALTHY")).toBe("green");
  });

  // Teste-guarda de contrato: `GET /api/system/health/full` (schemas.SystemHealth,
  // Orchestrator/app/schemas/system.py) e `GET /api/system/health` (schemas.SystemLiveness)
  // usam o vocabulário healthy|ok|degraded|unhealthy — NÃO healthy|warning|critical, que
  // é só o vocabulário do baseline operacional. Consumido por StatusBar, SystemPage e
  // PainelPage via `getHealth()`/`getOverview().health`. Este teste existe porque esse
  // exato descompasso já causou bug em produção: o alarme piscante nunca disparava e o
  // sistema "degraded" aparecia cinza (nem verde, nem âmbar, nem vermelho).
  it("cobre o vocabulário real de SystemHealth/SystemLiveness sem cair no default cinza", () => {
    const vocabularioBackend = ["healthy", "ok", "degraded", "unhealthy"] as const;
    for (const status of vocabularioBackend) {
      expect(healthTone(status)).not.toBe("grey");
    }
  });

  it("healthLabel traduz degraded/unhealthy para pt-BR", () => {
    expect(healthLabel("degraded")).toBe("degradado");
    expect(healthLabel("unhealthy")).toBe("incidente");
  });
});

describe("slaTone", () => {
  // Vocabulário real de `portfolio_catalog._sla_state` (tipo `SlaState` em
  // orchestrator.ts): ok | breached | recovering | unknown. `at_risk`/`violated`
  // eram valores mortos (o backend nunca os emite) e foram removidos do switch.
  it("mapeia ok para verde", () => {
    expect(slaTone("ok")).toBe("green");
  });

  it("mapeia breached para vermelho (SLA rompido, não pode ser neutro)", () => {
    expect(slaTone("breached")).toBe("red");
  });

  it("mapeia recovering para âmbar", () => {
    expect(slaTone("recovering")).toBe("amber");
  });

  it("usa cinza para unknown", () => {
    expect(slaTone("unknown")).toBe("grey");
  });

  it("usa cinza para null/undefined", () => {
    expect(slaTone(null)).toBe("grey");
    expect(slaTone(undefined)).toBe("grey");
  });
});

describe("criticalityTone", () => {
  it("mapeia high para vermelho, medium para âmbar, low para ciano", () => {
    expect(criticalityTone("high")).toBe("red");
    expect(criticalityTone("medium")).toBe("amber");
    expect(criticalityTone("low")).toBe("cyan");
  });

  it("usa cinza para null/undefined", () => {
    expect(criticalityTone(null)).toBe("grey");
    expect(criticalityTone(undefined)).toBe("grey");
  });
});

describe("healthLabel", () => {
  it("traduz healthy/warning/critical para rótulos em português", () => {
    expect(healthLabel("healthy")).toBe("saudável");
    expect(healthLabel("warning")).toBe("atenção");
    expect(healthLabel("critical")).toBe("incidente");
  });

  it("retorna travessão para null/undefined/vazio", () => {
    expect(healthLabel(null)).toBe("—");
    expect(healthLabel(undefined)).toBe("—");
    expect(healthLabel("")).toBe("—");
  });

  it("retorna o próprio status quando não há tradução mapeada", () => {
    expect(healthLabel("custom_status")).toBe("custom_status");
  });
});
