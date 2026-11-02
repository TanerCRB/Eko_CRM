import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

async function loadConfirmDialog() {
  try {
    return (await import(/* @vite-ignore */ "../src/components/ConfirmDialog")).ConfirmDialog;
  } catch {
    return undefined;
  }
}

function requireComponent<T>(component: T | undefined): T {
  expect(component, "ConfirmDialog must be implemented").toBeDefined();
  if (component === undefined) {
    throw new Error("ConfirmDialog must be implemented");
  }
  return component;
}

const consequence = "Usunąć  <b>wszystkie</b>\n  przyszłe wizyty?";

describe("K-04: ConfirmDialog preserves the consequence and requires an explicit decision", () => {
  it("uses its heading as the accessible name and preserves exact literal consequence text", async () => {
    const ConfirmDialog = requireComponent(await loadConfirmDialog());
    const user = userEvent.setup();
    function Harness({ text }: { text: string }) {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => {
            setOpen(true);
          }}>Otwórz</button>
          <ConfirmDialog
            open={open}
            title="Usunięcie klienta"
            consequence={text}
            confirmLabel="Usuń klienta"
            cancelLabel="Anuluj"
            onConfirm={() => { setOpen(false); }}
            onCancel={() => { setOpen(false); }}
          />
        </>
      );
    }
    const { rerender } = render(<Harness text={consequence} />);
    await user.click(screen.getByRole("button", { name: "Otwórz" }));
    const dialog = screen.getByRole("dialog", { name: "Usunięcie klienta" });

    expect(dialog.querySelector(".dialog-body")?.textContent).toBe(consequence);
    expect(dialog.querySelector("b")).not.toBeInTheDocument();
    rerender(<Harness text={"Zmieniona  treść\nkonsekwencji."} />);
    expect(dialog.querySelector(".dialog-body")?.textContent).toBe("Zmieniona  treść\nkonsekwencji.");
    expect(screen.queryByText(/Usunąć/)).not.toBeInTheDocument();
  });

  it("contains Tab focus, closes on Escape without confirmation, and returns focus", async () => {
    const ConfirmDialog = requireComponent(await loadConfirmDialog());
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => {
            setOpen(true);
          }}>Otwórz</button>
          <ConfirmDialog
            open={open}
            title="Usunięcie klienta"
            consequence={consequence}
            confirmLabel="Usuń klienta"
            cancelLabel="Anuluj"
            onConfirm={onConfirm}
            onCancel={() => { onCancel(); setOpen(false); }}
          />
        </>
      );
    }
    render(<Harness />);
    const invoker = screen.getByRole("button", { name: "Otwórz" });
    await user.click(invoker);
    const cancel = screen.getByRole("button", { name: "Anuluj" });
    const confirm = screen.getByRole("button", { name: "Usuń klienta" });

    expect(cancel).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(confirm).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(cancel).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(confirm).toHaveFocus();
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(invoker).toHaveFocus();
  });

  it("cancel and confirmation are distinct, and confirmation fires exactly once", async () => {
    const ConfirmDialog = requireComponent(await loadConfirmDialog());
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => {
            setOpen(true);
          }}>Otwórz</button>
          <ConfirmDialog
            open={open}
            title="Usunięcie klienta"
            consequence={consequence}
            confirmLabel="Usuń klienta"
            cancelLabel="Anuluj"
            onConfirm={() => { onConfirm(); setOpen(false); }}
            onCancel={() => { onCancel(); setOpen(false); }}
          />
        </>
      );
    }
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Otwórz" }));
    await user.click(screen.getByRole("button", { name: "Anuluj" }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Otwórz" }));
    await user.click(screen.getByRole("button", { name: "Usuń klienta" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onCancel).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps a long consequence readable and both actions reachable at 320px", async () => {
    const ConfirmDialog = requireComponent(await loadConfirmDialog());
    const user = userEvent.setup();
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 320 });
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => {
            setOpen(true);
          }}>Otwórz</button>
          <ConfirmDialog
            open={open}
            title="Usunięcie klienta"
            consequence={`${consequence} ${"Bardzo długa konsekwencja. ".repeat(12)}`}
            confirmLabel="Usuń klienta"
            cancelLabel="Anuluj"
            onConfirm={() => { setOpen(false); }}
            onCancel={() => { setOpen(false); }}
          />
        </>
      );
    }
    try {
      render(<Harness />);
      await user.click(screen.getByRole("button", { name: "Otwórz" }));
      const dialog = screen.getByRole("dialog");
      const body = dialog.querySelector(".dialog-body");
      expect(body).not.toBeNull();
      if (!body) return;
      const dialogRule = Array.from(document.styleSheets)
        .flatMap((sheet) => Array.from(sheet.cssRules))
        .find(
          (rule): rule is CSSStyleRule =>
            rule instanceof CSSStyleRule && rule.selectorText === ".confirm-dialog",
        );
      expect(dialog.querySelector(".dialog-body")?.textContent).toContain("Bardzo długa konsekwencja.");
      expect(dialogRule).toBeDefined();
      expect(dialogRule?.style.maxWidth).toMatch(/^min\(600px,.*100vw.*\)$/);
      expect(dialogRule?.style.maxWidth).toContain("32px");
      expect(getComputedStyle(body).overflowWrap).toBe("anywhere");
      expect(screen.getByRole("button", { name: "Anuluj" })).toBeVisible();
      expect(screen.getByRole("button", { name: "Usuń klienta" })).toBeVisible();
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth });
    }
  });
});
