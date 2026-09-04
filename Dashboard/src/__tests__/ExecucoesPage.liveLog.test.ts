import { describe, expect, it } from "vitest";
import { appendCappedLog, MAX_LIVE_LOG_LINES, STATUS_OPTIONS } from "../pages/ExecucoesPage";

describe("appendCappedLog (achado nº 7 — log ao vivo sem teto)", () => {
  it("mantém o texto intacto enquanto não ultrapassa o teto de linhas", () => {
    let text = "";
    for (let i = 0; i < 10; i++) {
      text = appendCappedLog(text, `linha ${i}\n`);
    }
    // split("\n") de um texto terminado em "\n" sempre tem um elemento vazio
    // final — mesma contagem usada dentro de appendCappedLog.
    expect(text.split("\n")).toHaveLength(11);
    expect(text).toContain("linha 0");
    expect(text).toContain("linha 9");
  });

  it("empurrar 5000 linhas não deixa o estado acumulado crescer sem limite", () => {
    let text = "";
    for (let i = 0; i < 5_000; i++) {
      text = appendCappedLog(text, `linha ${i}\n`);
    }
    const lines = text.split("\n");
    // Asserta o TETO (não tempo de parse — flaky no CI, ver handoff item 7).
    expect(lines.length).toBeLessThanOrEqual(MAX_LIVE_LOG_LINES);
    expect(lines.length).toBe(MAX_LIVE_LOG_LINES);
  });

  it("descarta as linhas mais antigas e preserva as mais recentes ao ultrapassar o teto", () => {
    let text = "";
    for (let i = 0; i < 5_000; i++) {
      text = appendCappedLog(text, `linha ${i}\n`);
    }
    expect(text).not.toContain("linha 0\n");
    expect(text).toContain("linha 4999");
  });

  it("respeita o teto mesmo quando uma única mensagem chega com muitas linhas de uma vez", () => {
    const chunkComMuitasLinhas = Array.from({ length: 4_000 }, (_, i) => `bloco ${i}`).join("\n") + "\n";
    const text = appendCappedLog("", chunkComMuitasLinhas);
    const lines = text.split("\n").filter(Boolean);
    expect(lines.length).toBeLessThanOrEqual(MAX_LIVE_LOG_LINES);
  });
});

describe("STATUS_OPTIONS (achado nº 20 — filtro de status incompleto)", () => {
  it("inclui a opção 'todos os status' (vazia) e cada valor de ExecutionStatus", () => {
    expect(STATUS_OPTIONS[0]).toBe("");
    for (const status of [
      "PENDING",
      "RUNNING",
      "SUCCESS",
      "PARTIAL",
      "ERROR",
      "TIMEOUT",
      "TERMINATED",
      "FAILED_BY_REBOOT",
      "REQUEUED",
      "EXPIRED",
    ]) {
      expect(STATUS_OPTIONS).toContain(status);
    }
  });
});
