import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import "../src/styles/tokens.css";

async function loadButton() {
  try {
    return (await import(/* @vite-ignore */ "../src/components/Button")).Button;
  } catch {
    return undefined;
  }
}

async function loadIconButton() {
  try {
    return (await import(/* @vite-ignore */ "../src/components/IconButton")).IconButton;
  } catch {
    return undefined;
  }
}

async function loadField() {
  try {
    return (await import(/* @vite-ignore */ "../src/components/Field")).Field;
  } catch {
    return undefined;
  }
}

async function loadEmptyState() {
  try {
    return (await import(/* @vite-ignore */ "../src/components/EmptyState")).EmptyState;
  } catch {
    return undefined;
  }
}

async function loadToast() {
  try {
    return (await import(/* @vite-ignore */ "../src/components/Toast")).Toast;
  } catch {
    return undefined;
  }
}

describe("K-02: shared primitives render their supplied contracts", () => {
  it("Button exposes its label and action, and only disabled changes activation", async () => {
    const Button = await loadButton();
    expect(Button, "Button must be implemented").toBeDefined();
    if (!Button) return;
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { rerender } = render(<Button label="Zapisz" onClick={onClick} />);

    await user.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(onClick).toHaveBeenCalledOnce();
    rerender(<Button label="Zapisz źródło" onClick={onClick} />);
    expect(screen.getByRole("button", { name: "Zapisz źródło" })).toBeEnabled();
    rerender(<Button label="Zapisz źródło" onClick={onClick} disabled />);
    expect(screen.getByRole("button", { name: "Zapisz źródło" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Zapisz źródło" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("IconButton exposes its Polish label and action while hiding its decorative icon", async () => {
    const IconButton = await loadIconButton();
    expect(IconButton, "IconButton must be implemented").toBeDefined();
    if (!IconButton) return;
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <IconButton label="Zamknij okno" onClick={onClick} icon={<svg viewBox="0 0 24 24" />} />,
    );
    const button = screen.getByRole("button", { name: "Zamknij okno" });

    expect(button.querySelector("svg")?.parentElement).toHaveAttribute("aria-hidden", "true");
    await user.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("IconButton changes only its accessible name when only its label changes", async () => {
    const IconButton = await loadIconButton();
    expect(IconButton, "IconButton must be implemented").toBeDefined();
    if (!IconButton) return;
    const onClick = vi.fn();
    const icon = <svg viewBox="0 0 24 24" />;
    const { rerender } = render(<IconButton label="Zamknij okno" onClick={onClick} icon={icon} />);

    rerender(<IconButton label="Zamknij szczegóły" onClick={onClick} icon={icon} />);
    expect(screen.queryByRole("button", { name: "Zamknij okno" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zamknij szczegóły" })).toBeEnabled();
  });

  it("Field keeps an empty control labelled and exposes required and error feedback", async () => {
    const Field = await loadField();
    expect(Field, "Field must be implemented").toBeDefined();
    if (!Field) return;
    render(<Field label="Nazwa klienta" value="" readOnly required error="Podaj nazwę klienta." />);
    const control = screen.getByRole("textbox", { name: /Nazwa klienta/ });

    expect(control).toHaveValue("");
    expect(control).toBeRequired();
    expect(control).toHaveAttribute("aria-invalid", "true");
    expect(control).toHaveAccessibleDescription("Podaj nazwę klienta.");
    expect(screen.getByText("Podaj nazwę klienta.")).toBeVisible();
  });

  it("Field changes only the label association when only its label changes", async () => {
    const Field = await loadField();
    expect(Field, "Field must be implemented").toBeDefined();
    if (!Field) return;
    const { rerender } = render(<Field label="Nazwa klienta" value="" readOnly />);

    rerender(<Field label="Nazwa firmy" value="" readOnly />);
    expect(screen.queryByRole("textbox", { name: "Nazwa klienta" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Nazwa firmy" })).toHaveValue("");
  });

  it("EmptyState presents its content with zero or one optional action", async () => {
    const EmptyState = await loadEmptyState();
    expect(EmptyState, "EmptyState must be implemented").toBeDefined();
    if (!EmptyState) return;
    const content = {
      title: "Czas na rozmowę",
      explanation: "Nie ma zaplanowanych wizyt.",
    };
    const { rerender } = render(
      <EmptyState {...content} action={<button type="button">Zaplanuj wizytę</button>} />,
    );
    expect(screen.getByRole("heading", { name: content.title })).toBeVisible();
    expect(screen.getByText(content.explanation)).toBeVisible();
    expect(screen.getByRole("button", { name: "Zaplanuj wizytę" })).toBeVisible();

    rerender(<EmptyState {...content} />);
    expect(screen.getByRole("heading", { name: content.title })).toBeVisible();
    expect(screen.getByText(content.explanation)).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("EmptyState renders changed markup-like content literally while retaining its action", async () => {
    const EmptyState = await loadEmptyState();
    expect(EmptyState, "EmptyState must be implemented").toBeDefined();
    if (!EmptyState) return;
    const action = <button type="button">Zaplanuj wizytę</button>;
    const { rerender } = render(
      <EmptyState title="Czas na rozmowę" explanation="Wybierz klienta." action={action} />,
    );

    rerender(<EmptyState title="<b>Czas</b>" explanation="Wybierz klienta." action={action} />);
    expect(screen.queryByRole("heading", { name: "Czas na rozmowę" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "<b>Czas</b>" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Zaplanuj wizytę" })).toBeVisible();
    expect(document.querySelector("b")).not.toBeInTheDocument();
  });

  it("Toast announces its exact message through a polite status", async () => {
    const Toast = await loadToast();
    expect(Toast, "Toast must be implemented").toBeDefined();
    if (!Toast) return;
    render(<Toast message="Zapisano zmianę źródła." />);
    const status = screen.getByRole("status");

    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Zapisano zmianę źródła.");
  });

  it("Toast changes only its announced message when only the message changes", async () => {
    const Toast = await loadToast();
    expect(Toast, "Toast must be implemented").toBeDefined();
    if (!Toast) return;
    const { rerender } = render(<Toast message="Zapisano zmianę źródła." />);

    rerender(<Toast message="Zapisano nazwę klienta." />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Zapisano nazwę klienta.");
    expect(status).not.toHaveTextContent("Zapisano zmianę źródła.");
  });

  it("links a primary Button's computed background to the changeable P2 forest token", async () => {
    const Button = await loadButton();
    expect(Button, "Button must be implemented").toBeDefined();
    if (!Button) return;
    render(<Button label="Zapisz" variant="primary" />);
    const button = screen.getByRole("button", { name: "Zapisz" });
    const rootStyle = getComputedStyle(document.documentElement);

    expect(getComputedStyle(button).backgroundColor).toBe("var(--color-forest)");
    expect(rootStyle.getPropertyValue("--color-forest").trim()).toBe("#244b3b");
    document.documentElement.style.setProperty("--color-forest", "rgb(1, 2, 3)");
    expect(getComputedStyle(button).backgroundColor).toBe("var(--color-forest)");
    expect(
      getComputedStyle(document.documentElement).getPropertyValue("--color-forest").trim(),
    ).toBe("rgb(1, 2, 3)");
    document.documentElement.style.removeProperty("--color-forest");
  });
});
