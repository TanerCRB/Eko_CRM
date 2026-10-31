import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import { Button } from "./Button";
import "../styles/components.css";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  consequence: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  consequence,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const consequenceId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (open && !dialog.open) {
      returnFocusRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.querySelector("button")?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(
    () => () => {
      returnFocusRef.current?.focus();
    },
    [],
  );

  const closeDialog = () => {
    const dialog = dialogRef.current;
    if (dialog?.open) {
      dialog.close();
    }
    returnFocusRef.current?.focus();
  };

  const cancel = () => {
    closeDialog();
    onCancel();
  };

  const confirm = () => {
    closeDialog();
    onConfirm();
  };

  const containFocus = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      cancel();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    const buttons = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not([disabled])"),
    );
    const first = buttons.at(0);
    const last = buttons.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  };

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-labelledby={titleId}
      aria-describedby={consequenceId}
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        cancel();
      }}
      onKeyDown={containFocus}
    >
      <div className="dialog-header">
        <h2 id={titleId}>{title}</h2>
      </div>
      <div id={consequenceId} className="dialog-body">
        {consequence}
      </div>
      <div className="dialog-footer">
        <Button label={cancelLabel} onClick={cancel} />
        <Button label={confirmLabel} variant="danger" onClick={confirm} />
      </div>
    </dialog>
  );
}
