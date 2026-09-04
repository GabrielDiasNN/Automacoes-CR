import { useState } from "react";
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// `toneVar[tone]` é lido no CORPO do StatTile — um Proxy com spy no `get`
// permite contar quantas vezes o corpo re-executou.
const toneReads = vi.fn();
vi.mock("../lib/status", () => ({
  toneVar: new Proxy(
    {},
    {
      get: (_t, prop) => {
        toneReads(prop);
        return "var(--x)";
      },
    },
  ),
}));

import { StatTile } from "../components/ui/StatTile";
import { mountWithRerender } from "./helpers/renderCount";

describe("StatTile — React.memo (contagem de renders)", () => {
  it("é um componente memoizado", () => {
    expect((StatTile as unknown as { $$typeof: symbol }).$$typeof).toBe(Symbol.for("react.memo"));
  });

  it("NÃO re-executa o corpo quando o pai re-renderiza com props estáveis", () => {
    const h = mountWithRerender(() => <StatTile label="pendentes" value={7} tone="amber" />);

    const antes = toneReads.mock.calls.length;
    expect(antes).toBeGreaterThan(0);

    h.rerenderParent();
    h.rerenderParent();

    expect(toneReads.mock.calls.length).toBe(antes); // memo segurou
  });

  it("controle: re-executa quando `value` muda a cada render do pai", () => {
    toneReads.mockClear();
    let bump: () => void = () => {};

    function Parent() {
      const [n, setN] = useState(0);
      bump = () => setN((v) => v + 1);
      return <StatTile label="pendentes" value={n} tone="amber" />;
    }

    render(<Parent />);
    const antes = toneReads.mock.calls.length;
    act(() => bump());
    expect(toneReads.mock.calls.length).toBeGreaterThan(antes);
  });
});
