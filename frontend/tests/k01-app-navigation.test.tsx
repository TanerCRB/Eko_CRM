import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("K-01: application navigation state", () => {
  it("keeps Pulpit current after activating it from the open mobile navigation", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: query === "(max-width: 700px)",
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    window.history.replaceState(null, "", "/");
    const user = userEvent.setup();
    render(<App />);
    const menu = screen.getByRole("button", { name: "Otwórz lub zamknij nawigację" });
    const navigation = screen.getByRole("navigation", { name: "Nawigacja główna" });
    const destination = within(navigation).getByRole("link", { name: "Pulpit" });

    expect(navigation).toHaveAttribute("inert");
    await user.click(menu);
    expect(navigation).not.toHaveAttribute("inert");
    await user.click(destination);

    expect(window.location.pathname).toBe("/");
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(navigation).toHaveAttribute("inert");
    expect(destination).toHaveAttribute("aria-current", "page");
    expect(within(navigation).getByRole("link", { current: "page" })).toBe(destination);
    expect(document.querySelectorAll("[aria-current='page']")).toHaveLength(1);
  });
});
