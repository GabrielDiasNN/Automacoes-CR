import type { KeyboardEvent } from "react";
import { describe, expect, it, vi } from "vitest";
import { onActivationKey } from "../lib/keyboard";

const evento = (key: string) => ({ key, preventDefault: vi.fn() }) as unknown as KeyboardEvent & {
  preventDefault: ReturnType<typeof vi.fn>;
};

describe("onActivationKey", () => {
  it("Enter ativa e cancela o comportamento padrão", () => {
    const onActivate = vi.fn();
    const e = evento("Enter");
    onActivationKey(onActivate)(e);
    expect(onActivate).toHaveBeenCalledTimes(1);
    expect(e.preventDefault).toHaveBeenCalledTimes(1);
  });

  it("Espaço ativa e cancela o scroll da página", () => {
    const onActivate = vi.fn();
    const e = evento(" ");
    onActivationKey(onActivate)(e);
    expect(onActivate).toHaveBeenCalledTimes(1);
    expect(e.preventDefault).toHaveBeenCalledTimes(1);
  });

  it("outras teclas não ativam e não cancelam o evento", () => {
    const onActivate = vi.fn();
    for (const key of ["a", "Tab", "Escape", "ArrowDown"]) {
      const e = evento(key);
      onActivationKey(onActivate)(e);
      expect(e.preventDefault).not.toHaveBeenCalled();
    }
    expect(onActivate).not.toHaveBeenCalled();
  });
});
