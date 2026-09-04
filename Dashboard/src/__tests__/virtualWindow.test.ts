import { describe, expect, it } from "vitest";
import { computeWindow } from "../lib/virtualWindow";

// rowH 20, viewport 400 → 20 linhas cabem; overscan 5.
const ROW = 20;
const VH = 400;
const OVER = 5;

describe("computeWindow", () => {
  it("lista vazia → janela zerada", () => {
    expect(computeWindow(0, ROW, VH, 0, OVER)).toEqual({ start: 0, end: 0, topPad: 0, bottomPad: 0 });
  });

  it("rowH inválido (0) → janela zerada (evita divisão por zero)", () => {
    expect(computeWindow(100, 0, VH, 50, OVER)).toEqual({ start: 0, end: 0, topPad: 0, bottomPad: 0 });
  });

  it("lista menor que o viewport → renderiza tudo, sem espaçadores", () => {
    const w = computeWindow(0, ROW, VH, 3, OVER);
    expect(w).toEqual({ start: 0, end: 3, topPad: 0, bottomPad: 0 });
  });

  it("topo (scrollTop 0) → start 0, end = viewport + overscan, bottomPad cobre o resto", () => {
    const w = computeWindow(0, ROW, VH, 300, OVER);
    expect(w.start).toBe(0);
    expect(w.end).toBe(25); // ceil(400/20) + 5
    expect(w.topPad).toBe(0);
    expect(w.bottomPad).toBe((300 - 25) * ROW);
  });

  it("meio → start/end centrados no scroll, ambos os espaçadores > 0", () => {
    const w = computeWindow(1000, ROW, VH, 300, OVER);
    // firstVisible = 50, lastVisible = ceil(1400/20) = 70
    expect(w.start).toBe(45);
    expect(w.end).toBe(75);
    expect(w.topPad).toBe(45 * ROW);
    expect(w.bottomPad).toBe((300 - 75) * ROW);
  });

  it("fim (scroll no máximo) → end = total, bottomPad 0", () => {
    const maxScroll = 300 * ROW - VH; // 5600
    const w = computeWindow(maxScroll, ROW, VH, 300, OVER);
    expect(w.end).toBe(300);
    expect(w.bottomPad).toBe(0);
    expect(w.start).toBe(Math.floor(maxScroll / ROW) - OVER); // 275
    expect(w.topPad).toBe(w.start * ROW);
  });

  it("scroll além do conteúdo (lista encolheu) → clampa, sem start > end", () => {
    const w = computeWindow(999999, ROW, VH, 40, OVER);
    expect(w.start).toBeLessThanOrEqual(w.end);
    expect(w.end).toBe(40);
    expect(w.bottomPad).toBe(0);
    expect(w.start).toBeGreaterThanOrEqual(0);
  });

  it("invariante 0 <= start <= end <= total em vários pontos", () => {
    for (const st of [0, 37, 250, 1234, 5600, 99999]) {
      for (const total of [0, 1, 19, 20, 21, 300]) {
        const w = computeWindow(st, ROW, VH, total, OVER);
        expect(w.start).toBeGreaterThanOrEqual(0);
        expect(w.start).toBeLessThanOrEqual(w.end);
        expect(w.end).toBeLessThanOrEqual(total);
        expect(w.topPad).toBe(w.start * ROW);
        expect(w.bottomPad).toBe((total - w.end) * ROW);
      }
    }
  });
});
