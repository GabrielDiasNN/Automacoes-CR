import { useState } from "react";
import { act, render } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// uPlot toca <canvas>/DOM que o jsdom não implementa — stub mínimo com spies.
const { uplotCtor, setDataSpy } = vi.hoisted(() => {
  const setDataSpy = vi.fn();
  const uplotCtor = vi.fn(function UPlotMock() {
    return { setData: setDataSpy, setSize: vi.fn(), destroy: vi.fn() };
  });
  return { uplotCtor, setDataSpy };
});
vi.mock("uplot", () => ({ default: uplotCtor }));

import { TimeSeries, type SeriesLine } from "../components/ui/TimeSeries";
import { mountWithRerender } from "./helpers/renderCount";

beforeAll(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

beforeEach(() => {
  uplotCtor.mockClear();
  setDataSpy.mockClear();
});

// `label` é lido no corpo (structureSignature + legenda + resumo) — getter com
// spy conta quantas vezes o corpo do componente re-executou.
const labelReads = vi.fn();
const XLABELS = ["00:00", "00:01", "00:02"];
const makeLines = (last = 3): SeriesLine[] => [
  {
    get label() {
      labelReads();
      return "pendentes";
    },
    tone: "cyan",
    values: [1, 2, last],
  },
];
const LINES = makeLines();

describe("TimeSeries — React.memo (contagem de renders)", () => {
  it("é um componente memoizado", () => {
    expect((TimeSeries as unknown as { $$typeof: symbol }).$$typeof).toBe(Symbol.for("react.memo"));
  });

  it("NÃO re-executa o corpo nem recria o gráfico quando o pai re-renderiza com props estáveis", () => {
    labelReads.mockClear();
    const h = mountWithRerender(() => <TimeSeries xLabels={XLABELS} lines={LINES} height={160} />);

    expect(uplotCtor).toHaveBeenCalledTimes(1);
    const antes = labelReads.mock.calls.length;
    expect(antes).toBeGreaterThan(0);

    h.rerenderParent();
    h.rerenderParent();

    expect(labelReads.mock.calls.length).toBe(antes); // corpo não re-executou
    expect(uplotCtor).toHaveBeenCalledTimes(1); // gráfico não recriado
  });

  it("controle: `lines` instável → corpo RE-EXECUTA e só setData dispara (sem recriar)", () => {
    labelReads.mockClear();
    let bump: () => void = () => {};

    function Parent() {
      const [n, setN] = useState(0);
      bump = () => setN((v) => v + 1);
      const lines = makeLines(n); // getter novo a cada render → prop instável
      return <TimeSeries xLabels={XLABELS} lines={lines} height={160} />;
    }

    render(<Parent />);
    expect(uplotCtor).toHaveBeenCalledTimes(1);
    const antesCorpo = labelReads.mock.calls.length;
    const antesSetData = setDataSpy.mock.calls.length;

    act(() => bump());

    // sem memo efetivo (prop instável): o corpo re-executou...
    expect(labelReads.mock.calls.length).toBeGreaterThan(antesCorpo);
    // ...mas a estrutura (rótulos/tons/height/xLabels) é igual → só setData.
    expect(setDataSpy.mock.calls.length).toBeGreaterThan(antesSetData);
    expect(uplotCtor).toHaveBeenCalledTimes(1);
  });
});
