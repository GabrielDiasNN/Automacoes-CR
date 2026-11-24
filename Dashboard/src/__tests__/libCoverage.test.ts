import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useTheme } from "../context/ThemeContext";
import { formatDateTimeBr } from "../lib/format";
import { parseLine } from "../lib/logParser";
import { healthTone, operationalStateLabel, operationalTone } from "../lib/status";

describe("formatDateTimeBr", () => {
  it("retorna travessão para valores ausentes ou vazios", () => {
    expect(formatDateTimeBr(null)).toBe("—");
    expect(formatDateTimeBr(undefined)).toBe("—");
    expect(formatDateTimeBr("")).toBe("—");
  });

  it("formata ISO naive com separador T e segundos explícitos", () => {
    expect(formatDateTimeBr("2026-07-06T05:16:42")).toBe("06/07/2026 05:16:42");
  });

  it("formata ISO naive com espaço e preenche segundos ausentes com 00", () => {
    expect(formatDateTimeBr("2026-07-06 05:16")).toBe("06/07/2026 05:16:00");
  });

  it("devolve a string original quando não corresponde ao padrão ISO", () => {
    expect(formatDateTimeBr("06/07/2026")).toBe("06/07/2026");
  });
});

describe("status — healthTone, operationalTone e operationalStateLabel", () => {
  it("healthTone retorna grey para valores desconhecidos ou nulos", () => {
    expect(healthTone("desconhecido")).toBe("grey");
    expect(healthTone(null)).toBe("grey");
    expect(healthTone(undefined)).toBe("grey");
  });

  it("operationalTone mapeia todos os estados operacionais e fallback", () => {
    expect(operationalTone("healthy")).toBe("green");
    expect(operationalTone("in_progress")).toBe("cyan");
    expect(operationalTone("attention")).toBe("amber");
    expect(operationalTone("paused")).toBe("grey");
    expect(operationalTone("idle")).toBe("grey");
    expect(operationalTone("outro")).toBe("grey");
    expect(operationalTone(null)).toBe("grey");
  });

  it("operationalStateLabel traduz estados conhecidos, trata vazios e preserva desconhecidos", () => {
    expect(operationalStateLabel("healthy")).toBe("saudável");
    expect(operationalStateLabel("IN_PROGRESS")).toBe("em execução");
    expect(operationalStateLabel("attention")).toBe("atenção");
    expect(operationalStateLabel("paused")).toBe("pausada");
    expect(operationalStateLabel("idle")).toBe("ociosa");
    expect(operationalStateLabel(null)).toBe("—");
    expect(operationalStateLabel("")).toBe("—");
    expect(operationalStateLabel("custom_state")).toBe("custom_state");
  });
});

describe("logParser — eventos estruturados execution.start, step.start e retry.attempt", () => {
  const base = {
    ts: "2026-08-27T07:01:51Z",
    level: "INFO",
    component: "python_domain",
  };

  it("formata execution.start com mensagem e com fallback padrão", () => {
    const comMsg = parseLine(
      JSON.stringify({ ...base, event: "execution.start", message: "iniciando carga" }),
    );
    expect(comMsg.message).toBe("▶ iniciando carga");

    const semMsg = parseLine(
      JSON.stringify({ ...base, event: "execution.start", message: "" }),
    );
    expect(semMsg.message).toBe("▶ início da execução");
  });

  it("formata step.start com e sem mensagem complementar", () => {
    const comMsg = parseLine(
      JSON.stringify({ ...base, event: "step.start", step: "extract", message: "lendo Oracle" }),
    );
    expect(comMsg.message).toBe("▸ extract: lendo Oracle");

    const semMsg = parseLine(
      JSON.stringify({ ...base, event: "step.start", step: "extract", message: "" }),
    );
    expect(semMsg.message).toBe("▸ extract");
  });

  it("formata retry.attempt com e sem mensagem complementar", () => {
    const comMsg = parseLine(
      JSON.stringify({
        ...base,
        level: "WARN",
        event: "retry.attempt",
        step: "upload",
        attempt: 2,
        max_attempts: 3,
        message: "timeout HTTP",
      }),
    );
    expect(comMsg.level).toBe("warn");
    expect(comMsg.message).toBe("⇄ upload tentativa 2/3 — timeout HTTP");

    const semMsg = parseLine(
      JSON.stringify({
        ...base,
        level: "WARN",
        event: "retry.attempt",
        step: "upload",
        attempt: 1,
        max_attempts: 3,
        message: "",
      }),
    );
    expect(semMsg.message).toBe("⇄ upload tentativa 1/3");
  });
});

describe("ThemeContext — useTheme fora do provider", () => {
  it("lança erro quando useTheme é chamado fora de ThemeProvider", () => {
    expect(() => renderHook(() => useTheme())).toThrow(
      "useTheme deve ser usado dentro de ThemeProvider",
    );
  });
});
