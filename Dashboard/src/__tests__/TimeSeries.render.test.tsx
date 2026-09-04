import { useState, type ReactNode } from "react";
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
import { ThemeProvider, useTheme } from "../context/ThemeContext";
import { mountWithRerender } from "./helpers/renderCount";

// `TimeSeries` consome `useTheme()` (achado nº 1) — precisa de um `ThemeProvider`
// ancestral em todo teste, senão o hook lança fora do provider.
const withTheme = (children: ReactNode) => <ThemeProvider>{children}</ThemeProvider>;

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
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
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
    const h = mountWithRerender(() => <TimeSeries xLabels={XLABELS} lines={LINES} height={160} />, withTheme);

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

    render(withTheme(<Parent />));
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

// Achado nº 1: `readPalette()` só é chamado dentro do `useEffect` de recriação
// (deps = `structureKey`). Antes da correção, trocar o tema não mudava nada em
// `structureKey` — o `<canvas>` ficava com as cores lidas na criação. Este
// teste prova que `TimeSeries` agora consome `useTheme()` e que `theme` entra
// na assinatura de estrutura: `cycleTheme()` precisa recriar o plot (destroy +
// novo `new uPlot`), não só chamar `setData`.
describe("TimeSeries — recriação na troca de tema (achado nº 1)", () => {
  function Harness() {
    const { cycleTheme } = useTheme();
    return (
      <>
        <button onClick={cycleTheme}>trocar tema</button>
        <TimeSeries xLabels={XLABELS} lines={LINES} height={160} />
      </>
    );
  }

  it("recria o uPlot (não só setData) quando o tema muda", () => {
    const { getByText } = render(withTheme(<Harness />));
    expect(uplotCtor).toHaveBeenCalledTimes(1); // "system" na montagem

    act(() => {
      getByText("trocar tema").click(); // system -> light
    });
    expect(uplotCtor).toHaveBeenCalledTimes(2);

    act(() => {
      getByText("trocar tema").click(); // light -> dark
    });
    expect(uplotCtor).toHaveBeenCalledTimes(3);
  });
});

// Achado nº 18: `structureSignature` juntava as partes com "," — um `label`
// contendo vírgula pode reconstituir a mesma string que outra combinação de
// xLabels/lines, suprimindo uma recriação legítima. Este par de xLabels
// colide sob "," (["1,2","3"] e ["1","2,3"] produzem a mesma sequência
// concatenada nos dois casos) mas não sob o separador U+0000 usado após a
// correção.
describe("TimeSeries — separador de structureSignature (achado nº 18)", () => {
  it("xLabels que colidiriam sob vírgula ainda disparam recriação do uPlot", () => {
    function Parent({ xLabels }: { xLabels: string[] }) {
      return <TimeSeries xLabels={xLabels} lines={[]} height={100} />;
    }

    const { rerender } = render(withTheme(<Parent xLabels={["1,2", "3"]} />));
    expect(uplotCtor).toHaveBeenCalledTimes(1);

    rerender(withTheme(<Parent xLabels={["1", "2,3"]} />));

    // Com separador "," as duas assinaturas seriam idênticas e o plot NÃO
    // seria recriado — com U+0000 elas divergem e a recriação acontece.
    expect(uplotCtor).toHaveBeenCalledTimes(2);
  });
});
