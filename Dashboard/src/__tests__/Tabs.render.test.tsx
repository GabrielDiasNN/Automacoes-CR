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
});
