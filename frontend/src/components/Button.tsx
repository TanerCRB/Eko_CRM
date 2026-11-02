import type { ButtonHTMLAttributes, ReactNode } from "react";
import "../styles/components.css";

interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "className"> {
  label: string;
  icon?: ReactNode;
  variant?: "primary" | "secondary" | "leaf" | "ghost" | "danger";
}

export function Button({ label, icon, variant = "secondary", type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} className={`button button-${variant}`} {...props}>
      {icon === undefined ? null : (
        <span className="button-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      {label}
    </button>
  );
}
