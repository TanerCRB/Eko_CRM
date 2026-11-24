import { createContext, useContext } from "react";
import type { SessionInfo } from "../../api/auth";

// The signed-in session for the screens below the session gate; `null` outside it. It decides
// only what is shown: every request is decided by the server from the verified token.
export const SessionContext = createContext<SessionInfo | null>(null);

export function useSession(): SessionInfo | null {
  return useContext(SessionContext);
}

export function holdsManager(session: SessionInfo | null): boolean {
  return session?.roles.includes("manager") ?? false;
}
