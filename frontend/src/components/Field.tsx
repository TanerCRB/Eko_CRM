import { useId, type InputHTMLAttributes } from "react";
import { messages } from "../i18n/pl";
import "../styles/components.css";

interface FieldProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "id" | "className" | "aria-describedby" | "aria-invalid"
  > {
  id?: string;
  label: string;
  error?: string;
}

export function Field({ id, label, error, required, ...props }: FieldProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const errorId = `${controlId}-error`;

  return (
    <label className="field" htmlFor={controlId}>
      <span>
        {label}
        {required ? (
          <>
            <span aria-hidden="true"> *</span>
            <span className="sr-only"> ({messages.required})</span>
          </>
        ) : null}
      </span>
      <input
        id={controlId}
        required={required}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={error === undefined ? undefined : errorId}
        {...props}
      />
      {error === undefined ? null : (
        <small id={errorId} className="field-error" role="alert">
          {error}
        </small>
      )}
    </label>
  );
}
