import { messages } from "../i18n/pl";
import "../styles/components.css";

export type VisitState = "planned" | "held" | "cancelled" | "decision";
export type ActionStatus = "todo" | "progress" | "done" | "cancelled";
export type StatusBadgeState = VisitState | ActionStatus | "moved" | "unsynced";
export type StatusPresentation = "visit" | "action" | "flag";

interface StatusBadgeProps {
  state: StatusBadgeState;
  label?: string;
  presentation?: StatusPresentation;
}

function StatusIcon({ state }: { state: StatusBadgeState }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {state === "held" || state === "done" ? (
        <path d="m5 12 4 4L19 6" />
      ) : state === "decision" || state === "unsynced" ? (
        <path d="m10 4-8 14a2 2 0 0 0 2 3h16a2 2 0 0 0 2-3L14 4a2.3 2.3 0 0 0-4 0ZM12 9v4m0 4h.01" />
      ) : state === "moved" ? (
        <path d="M20 7a9 9 0 0 0-15-2L2 8m0-5v5h5m-3 9a9 9 0 0 0 15 2l3-3m0 5v-5h-5" />
      ) : (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </>
      )}
    </svg>
  );
}

export function StatusBadge({ state, label, presentation = "visit" }: StatusBadgeProps) {
  const defaultLabel =
    state === "cancelled" && presentation === "action"
      ? messages.actionCancelled
      : messages.status[state];

  return (
    <span className={`badge badge-${state}`} data-presentation={presentation}>
      <StatusIcon state={state} />
      {label || defaultLabel}
    </span>
  );
}
