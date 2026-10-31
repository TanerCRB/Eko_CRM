import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

async function loadStatusBadge() {
  try {
    return (await import(/* @vite-ignore */ "../src/components/StatusBadge")).StatusBadge;
  } catch {
    return undefined;
  }
}

const states = [
  ["planned", "Zaplanowana", "visit"],
  ["held", "Odbyta", "visit"],
  ["cancelled", "Odwołana", "visit"],
  ["decision", "Oczekuje na decyzję", "visit"],
  ["todo", "Do zrobienia", "action"],
  ["progress", "W toku", "action"],
  ["done", "Wykonane", "action"],
  ["cancelled", "Anulowane", "action"],
  ["moved", "Przełożona", "flag"],
  ["unsynced", "Brak synchronizacji", "flag"],
] as const;

describe("K-03: StatusBadge communicates every state without relying on colour", () => {
  it.each(states)("%s in %s presentation exposes visible text and an icon", async (state, label, presentation) => {
    const StatusBadge = await loadStatusBadge();
    expect(StatusBadge, "StatusBadge must be implemented").toBeDefined();
    if (!StatusBadge) return;
    render(<StatusBadge state={state} presentation={presentation} />);
    const badge = screen.getByText(label);

    expect(badge).toBeVisible();
    expect(badge.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    badge.style.color = "transparent";
    badge.style.backgroundColor = "transparent";
    expect(badge).toHaveTextContent(label);
    expect(badge.querySelector("svg")).toBeInTheDocument();
  });

  it("a custom label replaces only the default and an empty label falls back to P2", async () => {
    const StatusBadge = await loadStatusBadge();
    expect(StatusBadge, "StatusBadge must be implemented").toBeDefined();
    if (!StatusBadge) return;
    const { rerender } = render(<StatusBadge state="planned" label="Własna etykieta" />);
    expect(screen.getByText("Własna etykieta")).toBeVisible();
    expect(screen.queryByText("Zaplanowana")).not.toBeInTheDocument();

    rerender(<StatusBadge state="planned" label="" />);
    expect(screen.getByText("Zaplanowana")).toBeVisible();
  });

  it.each([
    [false, false],
    [true, false],
    [false, true],
    [true, true],
  ])("moved=%s and unsynced=%s stay independent of a visit state", async (moved, unsynced) => {
    const StatusBadge = await loadStatusBadge();
    expect(StatusBadge, "StatusBadge must be implemented").toBeDefined();
    if (!StatusBadge) return;
    render(
      <>
        <StatusBadge state="planned" />
        {moved ? <StatusBadge state="moved" /> : null}
        {unsynced ? <StatusBadge state="unsynced" /> : null}
      </>,
    );

    expect(screen.getByText("Zaplanowana")).toBeVisible();
    expect(screen.queryByText("Przełożona")).toEqual(moved ? expect.any(HTMLElement) : null);
    expect(screen.queryByText("Brak synchronizacji")).toEqual(
      unsynced ? expect.any(HTMLElement) : null,
    );
  });

  it("a colour-only negative fixture does not convey the same state", () => {
    const { container } = render(<span className="badge badge-planned" />);
    expect(container.querySelector("svg")).not.toBeInTheDocument();
    expect(screen.queryByText("Zaplanowana")).not.toBeInTheDocument();
  });
});
