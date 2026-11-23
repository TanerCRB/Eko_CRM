import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AccountPanel } from "./features/session/AccountPanel";
import { LOGIN_FAILED_PATH, LoginFailed } from "./features/session/LoginFailed";
import { SessionGate } from "./features/session/SessionGate";
import { SessionContext } from "./features/session/sessionContext";

const ROOT_ID = "root";

export function mount(page: Document): () => void {
  const container = page.getElementById(ROOT_ID);
  if (container === null) {
    throw new Error(`No element with id "${ROOT_ID}" to mount the application into`);
  }
  const root = createRoot(container);
  root.render(
    <StrictMode>
      {page.location.pathname === LOGIN_FAILED_PATH ? (
        <LoginFailed />
      ) : (
        <SessionGate>
          {(session) => (
            <SessionContext value={session}>
              <App account={<AccountPanel session={session} />} />
            </SessionContext>
          )}
        </SessionGate>
      )}
    </StrictMode>,
  );
  return () => {
    root.unmount();
  };
}
