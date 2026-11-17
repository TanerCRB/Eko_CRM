import { useRef, useState } from "react";
import { logout } from "../../api/auth";
import { pageNavigation } from "../../api/navigation";

export interface LogoutControl {
  pending: boolean;
  failed: boolean;
  signOut: () => void;
}

// The one logout action of the SPA: the account panel and the no-role screen both use it.
export function useLogout(): LogoutControl {
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  const run = async () => {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(true);
    setFailed(false);
    const result = await logout();
    if (result.kind === "failed") {
      inFlight.current = false;
      setPending(false);
      setFailed(true);
      return;
    }
    // A full load of "/" drops every in-memory per-user state; the gate then starts a fresh login.
    pageNavigation.assign("/");
  };

  return {
    pending,
    failed,
    signOut: () => {
      void run();
    },
  };
}
