import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "../src/components/AppShell";

const items = [
  { href: "/", label: "Pulpit", current: true },
  { href: "/wizyty", label: "Wizyty" },
];

describe("K-01: accessible supplied shell navigation", () => {
  it("renders the supplied section and marks only the active destination", () => {
    render(
      <AppShell section="Wizyty" navigationItems={items}>
        <p>Treść</p>
      </AppShell>,
    );

    expect(screen.getByRole("banner")).toHaveTextContent("Wizyty");
    const navigation = screen.getByRole("navigation", { name: "Nawigacja główna" });
    const links = within(navigation).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Pulpit", "Wizyty"]);
    expect(links[0]).toHaveAttribute("aria-current", "page");
    expect(links[1]).not.toHaveAttribute("aria-current");
    expect(within(navigation).getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("closes on Escape and returns focus to the menu control", async () => {
    const user = userEvent.setup();
    render(
      <AppShell section="Pulpit" navigationItems={[{ href: "/", label: "Pulpit", current: true }]}>
        <p>Treść</p>
      </AppShell>,
    );
    const menu = screen.getByRole("button", { name: "Otwórz lub zamknij nawigację" });
    const destination = screen.getByRole("link", { name: "Pulpit" });

    await user.click(menu);
    destination.focus();
    await user.keyboard("{Escape}");

    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveFocus();
  });

  it("closes after destination activation and reports the selected href", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn<(href: string) => void>();
    render(
      <AppShell section="Pulpit" navigationItems={items} onNavigate={onNavigate}>
        <p>Treść</p>
      </AppShell>,
    );
    const menu = screen.getByRole("button", { name: "Otwórz lub zamknij nawigację" });

    await user.click(menu);
    await user.click(screen.getByRole("link", { name: "Wizyty" }));

    expect(onNavigate).toHaveBeenCalledExactlyOnceWith("/wizyty");
    expect(menu).toHaveAttribute("aria-expanded", "false");
  });
});
