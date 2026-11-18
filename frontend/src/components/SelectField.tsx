import { useId, type SelectHTMLAttributes } from "react";
import { messages } from "../i18n/pl";
import "../styles/components.css";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectFieldProps
  extends Omit<
    SelectHTMLAttributes<HTMLSelectElement>,
    "id" | "className" | "aria-describedby" | "aria-invalid" | "children"
  > {
  id?: string;
  label: string;
  options: readonly SelectOption[];
  error?: string | undefined;
}

// The select counterpart of `Field`: same label, required marker and error wiring.
export function SelectField({ id, label, options, error, required, ...props }: SelectFieldProps) {
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
      <select
        id={controlId}
        required={required}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={error === undefined ? undefined : errorId}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error === undefined ? null : (
        <small id={errorId} className="field-error" role="alert">
          {error}
        </small>
      )}
    </label>
  );
}
