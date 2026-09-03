import { describe, expect, it } from "vitest";
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
    expect(executionTone("CLAIMED")).toBe("amber");
  });

  it("mapeia PENDING para ciano", () => {
    expect(executionTone("PENDING")).toBe("cyan");
  });

  it("é case-insensitive", () => {
    expect(executionTone("success")).toBe("green");
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
  it("mapeia ok para verde, at_risk para âmbar, violated para vermelho", () => {
    expect(slaTone("ok")).toBe("green");
    expect(slaTone("at_risk")).toBe("amber");
    expect(slaTone("violated")).toBe("red");
  });

  it("usa cinza para estado desconhecido", () => {
    expect(slaTone("unknown")).toBe("grey");
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
