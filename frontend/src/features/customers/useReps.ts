import { useEffect, useState } from "react";
import { readReps, type RepEntry } from "../../api/reps";

// Read once per mounted list and only when `enabled`, held in memory only, never in browser storage
// (ADR-0005-C12). `null` means nothing to offer: not asked, still on its way, or failed (G-8 A).
export function useReps(enabled: boolean): readonly RepEntry[] | null {
  const [reps, setReps] = useState<readonly RepEntry[] | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let current = true;
    void readReps().then((result) => {
      if (current && result.kind === "listed") {
        setReps(result.reps);
      }
    });
    return () => {
      current = false;
    };
  }, [enabled]);

  return enabled ? reps : null;
}
