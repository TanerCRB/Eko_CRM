import type { ButtonHTMLAttributes, ReactNode } from "react";
import "../styles/components.css";

interface IconButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "className" | "aria-label"> {
  label: string;
  icon: ReactNode;
}

export function IconButton({ label, icon, type = "button", ...props }: IconButtonProps) {
  return (
    <button type={type} className="icon-button" aria-label={label} title={label} {...props}>
      <span className="icon-button-icon" aria-hidden="true">
        {icon}
      </span>
    </button>
  );
}
