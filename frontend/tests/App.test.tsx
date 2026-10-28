import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../src/App";

describe("App (walking skeleton shell, P2 look)", () => {
  it("shows the placeholder workspace heading as the page's main heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Pulpit" })).toBeVisible();
  });

  it("names the product inside the labelled main navigation", () => {
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Nawigacja główna" });
    expect(within(nav).getByText("Eko CRM")).toBeInTheDocument();
  });

  it("offers only the one screen that exists, marked as the current page", () => {
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Nawigacja główna" });
    const links = within(nav).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName("Pulpit");
    expect(links[0]).toHaveAttribute("aria-current", "page");
  });

  it("lets keyboard users skip to the main content", () => {
    render(<App />);
    const skip = screen.getByRole("link", { name: "Przejdź do treści" });
    const main = screen.getByRole("main");
    expect(skip).toHaveAttribute("href", `#${main.id}`);
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("opens and closes the navigation from the header's menu button", async () => {
    const user = userEvent.setup();
    render(<App />);
    const button = screen.getByRole("button", { name: "Otwórz lub zamknij nawigację" });
    const nav = screen.getByRole("navigation", { name: "Nawigacja główna" });
    expect(button).toHaveAttribute("aria-controls", nav.id);
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("shows one welcome panel, named by its heading, that holds no customer data", () => {
    render(<App />);
    const panel = screen.getByRole("region", { name: "Eko CRM działa" });
    expect(within(panel).getByText(/nie zawiera jeszcze danych klientów/)).toBeVisible();
  });
});
