import { Fragment, useEffect, useState, type ReactNode } from "react";
import { readSession, type SessionInfo } from "../../api/auth";
import { redirectToLogin } from "../../api/navigation";
import { messages } from "../../i18n/pl";

export type Schedule = (run: () => void, delayMs: number) => () => void;

const defaultSchedule: Schedule = (run, delayMs) => {
  const timer = window.setTimeout(run, delayMs);
  return () => {
    window.clearTimeout(timer);
  };
};

// After the last delay the gate stops retrying on its own; the user can still retry by hand.
const DEFAULT_RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 16000] as const;

type Phase =
  | { name: "checking" }
  | { name: "redirecting" }
  | { name: "unavailable"; retrying: boolean }
  | { name: "invalid" }
  | { name: "authenticated"; session: SessionInfo };

interface SessionGateProps {
  children: (session: SessionInfo) => ReactNode;
  retryDelaysMs?: readonly number[];
  schedule?: Schedule;
}

export function SessionGate({
  children,
  retryDelaysMs = DEFAULT_RETRY_DELAYS_MS,
  schedule = defaultSchedule,
}: SessionGateProps) {
  const [phase, setPhase] = useState<Phase>({ name: "checking" });
  const [check, setCheck] = useState({ round: 0, failures: 0 });

  useEffect(() => {
    let current = true;
    let cancelRetry: (() => void) | undefined;
    void readSession().then((result) => {
      if (!current) {
        return;
      }
      switch (result.kind) {
        case "authenticated":
          setPhase({ name: "authenticated", session: result.session });
          return;
        case "unauthenticated":
          setPhase({ name: "redirecting" });
          redirectToLogin();
          return;
        case "invalid":
          setPhase({ name: "invalid" });
          return;
        case "unavailable": {
          const delayMs = retryDelaysMs[check.failures];
          setPhase({ name: "unavailable", retrying: delayMs !== undefined });
          if (delayMs !== undefined) {
            cancelRetry = schedule(() => {
              setCheck(({ round, failures }) => ({ round: round + 1, failures: failures + 1 }));
            }, delayMs);
          }
          return;
        }
      }
    });
    return () => {
      current = false;
      cancelRetry?.();
    };
  }, [check, retryDelaysMs, schedule]);

  if (phase.name === "authenticated") {
    // A different subject gets a fresh subtree, so no component state crosses users.
    return <Fragment key={phase.session.subject}>{children(phase.session)}</Fragment>;
  }

  const retryByHand = () => {
    setPhase({ name: "checking" });
    setCheck((previous) => ({ ...previous, round: previous.round + 1 }));
  };

  return (
    <main id="main" className="session-screen" tabIndex={-1}>
      <h1>{messages.productName}</h1>
      {phase.name === "checking" ? <p role="status">{messages.session.checking}</p> : null}
      {phase.name === "redirecting" ? <p role="status">{messages.session.redirecting}</p> : null}
      {phase.name === "unavailable" ? (
        <>
          <p>{messages.session.unavailable}</p>
          {phase.retrying ? (
            <p role="status">{messages.session.retrying}</p>
          ) : (
            <p role="alert">{messages.session.retryLater}</p>
          )}
        </>
      ) : null}
      {phase.name === "invalid" ? <p role="alert">{messages.session.invalid}</p> : null}
      {phase.name === "unavailable" || phase.name === "invalid" ? (
        <button type="button" className="button button-primary" onClick={retryByHand}>
          {messages.session.retry}
        </button>
      ) : null}
    </main>
  );
}
