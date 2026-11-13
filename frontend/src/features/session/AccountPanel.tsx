import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { logout, type SessionInfo } from "../../api/auth";
import { pageNavigation } from "../../api/navigation";
import { Toast } from "../../components/Toast";
import { messages } from "../../i18n/pl";

interface AccountPanelProps {
  session: SessionInfo;
}

export function displayName(name: string | null): string {
  const trimmed = name?.trim() ?? "";
  return trimmed === "" ? messages.account.unnamedUser : trimmed;
}

export function AccountPanel({ session }: AccountPanelProps) {
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  const signOut = async () => {
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

  return (
    <section className="profile" aria-label={messages.account.label}>
      <strong className="profile-name">{displayName(session.name)}</strong>
      <button
        type="button"
        className="nav-link profile-logout"
        disabled={pending}
        aria-busy={pending}
        onClick={() => {
          void signOut();
        }}
      >
        {messages.account.logout}
      </button>
      {failed ? createPortal(<Toast message={messages.account.logoutFailed} />, document.body) : null}
    </section>
  );
}
