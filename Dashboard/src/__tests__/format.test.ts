import { describe, expect, it } from "vitest";
import {
  formatAge,
  formatDuration,
  formatNumber,
  formatPercent,
  shortId,
  successRate,
} from "../lib/format";

describe("formatDuration", () => {
  it("retorna travessão para null/undefined", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });

  it("formata segundos com uma casa decimal abaixo de 1 minuto", () => {
    expect(formatDuration(12.34)).toBe("12.3s");
  });

  it("formata minutos e segundos entre 1 minuto e 1 hora", () => {
    expect(formatDuration(90)).toBe("1m 30s");
  });

  it("formata horas e minutos acima de 1 hora", () => {
    expect(formatDuration(3725)).toBe("1h 02m");
  });
});

describe("formatAge", () => {
  it("retorna travessão para null/undefined", () => {
    expect(formatAge(null)).toBe("—");
  });

  it("formata segundos abaixo de 1 minuto", () => {
    expect(formatAge(45)).toBe("45s");
  });

  it("formata minutos abaixo de 1 hora", () => {
    expect(formatAge(150)).toBe("2min");
  });

  it("formata horas e minutos abaixo de 1 dia", () => {
    expect(formatAge(3 * 3600 + 20 * 60)).toBe("3h 20min");
  });

  it("formata dias e horas acima de 1 dia", () => {
    expect(formatAge(2 * 86400 + 5 * 3600)).toBe("2d 5h");
  });
});

describe("formatNumber", () => {
  it("retorna travessão para null/undefined", () => {
    expect(formatNumber(null)).toBe("—");
  });

  it("formata com separador de milhar pt-BR", () => {
    expect(formatNumber(12345)).toBe("12.345");
  });
});

describe("formatPercent", () => {
  it("retorna travessão para null/undefined", () => {
    expect(formatPercent(null)).toBe("—");
  });

  it("formata sem casas decimais por padrão", () => {
    expect(formatPercent(87.6)).toBe("88%");
  });

  it("respeita o número de casas decimais informado", () => {
    expect(formatPercent(87.654, 1)).toBe("87.7%");
  });
});

describe("successRate", () => {
  it("retorna null quando não há execuções", () => {
    expect(successRate(0, 0)).toBeNull();
  });

  it("calcula a taxa de sucesso em percentual", () => {
    expect(successRate(9, 1)).toBe(90);
  });

  it("retorna 0 quando todas as execuções falharam", () => {
    expect(successRate(0, 5)).toBe(0);
  });
});

describe("shortId", () => {
  it("mantém IDs curtos inalterados", () => {
    expect(shortId("EXEC-1")).toBe("EXEC-1");
  });

  it("trunca IDs longos no comprimento padrão", () => {
    const id = "EXEC_1751500000_ABCD1234EXTRA";
    expect(shortId(id)).toBe(id.slice(0, 14));
  });

  it("respeita o comprimento customizado", () => {
    expect(shortId("EXEC_1234567890", 5)).toBe("EXEC_");
  });
});
