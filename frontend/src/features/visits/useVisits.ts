import { useEffect, useState } from "react";
import { listVisitPeriod, listVisits } from "../../api/visits";
import { compareInstants } from "../../time/warsaw";

type VisitsResult = Awaited<ReturnType<typeof listVisits>>;
export type VisitsState = { kind: "loading" } | VisitsResult;

// Both inclusive Europe/Warsaw dates; `null` instead reads every visit the caller may read.
export interface VisitsRequest {
  first: string;
  last: string;
}

function keyOf(first: string | null, last: string | null, attempt: number): string {
  return `${first ?? "all"}|${last ?? "all"}|${String(attempt)}`;
}

function inStartOrder(result: VisitsResult): VisitsResult {
  if (result.kind !== "listed") {
    return result;
  }
  // A stable sort: visits with the same start keep the server's order.
  const visits = [...result.visits].sort((a, b) => compareInstants(a.starts_at, b.starts_at));
  return { kind: "listed", visits };
}

// One read of the server's visits per request and attempt. An answer is kept with the request it
// answers, so a late answer to an older request never shows and a new request shows loading until
// its own answer arrives. The server state lives here only, never copied into a global store.
export function useVisits(request: VisitsRequest | null): { state: VisitsState; retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [answer, setAnswer] = useState<{ key: string; result: VisitsResult } | null>(null);
  const first = request?.first ?? null;
  const last = request?.last ?? null;

  useEffect(() => {
    let current = true;
    const load =
      first === null || last === null ? listVisits() : listVisitPeriod({ first, last });
    void load.then((result) => {
      if (current) {
        setAnswer({ key: keyOf(first, last, attempt), result: inStartOrder(result) });
      }
    });
    return () => {
      current = false;
    };
  }, [first, last, attempt]);

  return {
    state: answer?.key === keyOf(first, last, attempt) ? answer.result : { kind: "loading" },
    retry: () => {
      setAttempt((count) => count + 1);
    },
  };
}
