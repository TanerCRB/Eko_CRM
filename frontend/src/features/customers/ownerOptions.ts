import type { RepEntry } from "../../api/reps";
import { displayName } from "../session/AccountPanel";

export interface OwnerOption {
  subject: string;
  label: string;
}

function shownName(rep: RepEntry): string | null {
  const trimmed = rep.name?.trim() ?? "";
  return trimmed === "" ? null : trimmed;
}

// Subjects are opaque keys: compared by code unit, never by a locale.
function bySubject(a: RepEntry, b: RepEntry): number {
  return a.subject < b.subject ? -1 : a.subject > b.subject ? 1 : 0;
}

// G-6 A: by the name as shown, in Polish order; ties by subject; reps with no name last.
export function ownerOptions(reps: readonly RepEntry[]): OwnerOption[] {
  return reps
    .map((rep) => ({ rep, name: shownName(rep) }))
    .sort((a, b) => {
      if (a.name !== null && b.name !== null) {
        const byName = a.name.localeCompare(b.name, "pl");
        if (byName !== 0) {
          return byName;
        }
      } else if (a.name !== b.name) {
        return a.name === null ? 1 : -1;
      }
      return bySubject(a.rep, b.rep);
    })
    .map(({ rep }) => ({ subject: rep.subject, label: displayName(rep.name) }));
}
