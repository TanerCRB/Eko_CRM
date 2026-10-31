import type { ReactNode } from "react";
import "../styles/components.css";

interface EmptyStateProps {
  title: string;
  explanation: string;
  action?: ReactNode;
}

export function EmptyState({ title, explanation, action }: EmptyStateProps) {
  return (
    <div className="empty">
      <svg
        className="icon empty-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M20 3C6 1 1 9 5 16s18 4 15-13ZM4 21 16 9" />
      </svg>
      <h3>{title}</h3>
      <p>{explanation}</p>
      {action === undefined ? null : <div className="empty-action">{action}</div>}
    </div>
  );
}
