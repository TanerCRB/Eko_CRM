import { createPortal } from "react-dom";
import { type SessionInfo } from "../../api/auth";
import { Toast } from "../../components/Toast";
import { messages } from "../../i18n/pl";
import { useLogout } from "./useLogout";

// The panel shows the caller's name only; its roles decide nothing here.
interface AccountPanelProps {
  session: Pick<SessionInfo, "subject" | "name">;
}

export function displayName(name: string | null): string {
  const trimmed = name?.trim() ?? "";
  return trimmed === "" ? messages.account.unnamedUser : trimmed;
}

export function AccountPanel({ session }: AccountPanelProps) {
  const { pending, failed, signOut } = useLogout();

  return (
    <section className="profile" aria-label={messages.account.label}>
      <strong className="profile-name">{displayName(session.name)}</strong>
      <button
        type="button"
        className="nav-link profile-logout"
        disabled={pending}
        aria-busy={pending}
        onClick={signOut}
      >
        {messages.account.logout}
      </button>
      {failed ? createPortal(<Toast message={messages.account.logoutFailed} />, document.body) : null}
    </section>
  );
}
