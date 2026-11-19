import { useEffect, useState } from "react";
import { readVoivodeships, type VoivodeshipsResult } from "../../api/reference";

export type VoivodeshipsState = { kind: "loading" } | VoivodeshipsResult;

// Read once per mounted form and held in memory only: never in browser storage (ADR-0005-C12).
export function useVoivodeships(): VoivodeshipsState {
  const [state, setState] = useState<VoivodeshipsState>({ kind: "loading" });

  useEffect(() => {
    let current = true;
    void readVoivodeships().then((result) => {
      if (current) {
        setState(result);
      }
    });
    return () => {
      current = false;
    };
  }, []);

  return state;
}
