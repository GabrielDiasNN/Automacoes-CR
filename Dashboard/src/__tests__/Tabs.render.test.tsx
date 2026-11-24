import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Tabs, type TabItem } from "../components/ui";

describe("Tabs", () => {
  const ITEMS: TabItem<"a" | "b" | "c">[] = [
    { id: "a", label: "Visão A", badge: 12 },
    { id: "b", label: "Visão B", badge: 0 },
    { id: "c", label: "Visão C" },
  ];

  it("marca a aba ativa com aria-selected e exibe badges", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} activeId="a" onChange={onChange} />);

    const tabA = screen.getByRole("tab", { name: /Visão A/ });
    const tabB = screen.getByRole("tab", { name: /Visão B/ });
    expect(tabA).toHaveAttribute("aria-selected", "true");
    expect(tabB).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();

    fireEvent.click(tabB);
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("suporta navegação por setas, Home, End e roving tabIndex", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} activeId="a" onChange={onChange} />);

    const tabA = screen.getByRole("tab", { name: /Visão A/ });
    const tabB = screen.getByRole("tab", { name: /Visão B/ });
    const tabC = screen.getByRole("tab", { name: /Visão C/ });

    expect(tabA).toHaveAttribute("tabindex", "0");
    expect(tabB).toHaveAttribute("tabindex", "-1");
    expect(tabC).toHaveAttribute("tabindex", "-1");

    tabA.focus();
    fireEvent.keyDown(tabA, { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("b");
    expect(document.activeElement).toBe(tabB);

    fireEvent.keyDown(tabA, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith("c");
    expect(document.activeElement).toBe(tabC);

    fireEvent.keyDown(tabA, { key: "End" });
    expect(onChange).toHaveBeenLastCalledWith("c");
    fireEvent.keyDown(tabC, { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("a");
    expect(document.activeElement).toBe(tabA);
  });
});
