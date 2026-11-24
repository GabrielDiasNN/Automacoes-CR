import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMediaQuery } from "../hooks/useMediaQuery";

describe("useMediaQuery", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("reflete estado inicial e reage ao evento change com cleanup no unmount", () => {
    let currentMatches = false;
    let listener: (() => void) | null = null;
    const removeEventListener = vi.fn();

    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return currentMatches;
      },
      media: query,
      addEventListener: (_event: string, cb: () => void) => {
        listener = cb;
      },
      removeEventListener,
    })) as typeof window.matchMedia;

    const { result, unmount } = renderHook(() => useMediaQuery("(max-width: 768px)"));
    expect(result.current).toBe(false);

    act(() => {
      currentMatches = true;
      listener?.();
    });
    expect(result.current).toBe(true);

    unmount();
    expect(removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });
});
