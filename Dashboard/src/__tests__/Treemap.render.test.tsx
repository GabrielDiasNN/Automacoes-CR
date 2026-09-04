import { useState } from "react";
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// `formatNumber` é chamado no CORPO do Treemap (resumo + labels das células) —
// o spy conta quantas vezes o corpo re-executou.
const fmtCalls = vi.fn();
vi.mock("../lib/format", () => ({
  formatNumber: (n: number) => {
    fmtCalls(n);
    return String(n);
  },
}));

import { Treemap } from "../components/beneficiamento/Treemap";
import type { BeneficiamentoTreemapNode } from "../api/orchestrator";
import { mountWithRerender } from "./helpers/renderCount";

const NODES: BeneficiamentoTreemapNode[] = [
  { setor: "Tinturaria", fase: "Tingimento", maquina: "M1", fases_concluidas: 3, kg_total: 100 },
  { setor: "Tinturaria", fase: "Secagem", maquina: "M2", fases_concluidas: 2, kg_total: 40 },
  { setor: "Acabamento", fase: "Calandra", maquina: "M3", fases_concluidas: 1, kg_total: 30 },
];
const NOOP = () => {};

describe("Treemap — React.memo (contagem de renders)", () => {
  it("é um componente memoizado", () => {
    expect((Treemap as unknown as { $$typeof: symbol }).$$typeof).toBe(Symbol.for("react.memo"));
  });

  it("NÃO re-executa o corpo quando o pai re-renderiza com props estáveis", () => {
    const h = mountWithRerender(() => <Treemap nodes={NODES} onCellClick={NOOP} height={200} />);

    const antes = fmtCalls.mock.calls.length;
    expect(antes).toBeGreaterThan(0);

    h.rerenderParent();
    h.rerenderParent();

    expect(fmtCalls.mock.calls.length).toBe(antes); // slice-and-dice não rodou de novo
  });

  it("controle: re-executa quando `nodes` muda de referência a cada render do pai", () => {
    fmtCalls.mockClear();
    let bump: () => void = () => {};

    function Parent() {
      const [n, setN] = useState(0);
      bump = () => setN((v) => v + 1);
      const nodes = NODES.map((x) => ({ ...x, kg_total: x.kg_total + n })); // novo array
      return <Treemap nodes={nodes} onCellClick={NOOP} height={200} />;
    }

    render(<Parent />);
    const antes = fmtCalls.mock.calls.length;
    act(() => bump());
    expect(fmtCalls.mock.calls.length).toBeGreaterThan(antes);
  });
});
