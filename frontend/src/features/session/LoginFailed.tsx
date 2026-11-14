import { loginUrl, pageNavigation } from "../../api/navigation";
import { messages } from "../../i18n/pl";

// The backend's 303 target for a refused or unavailable login callback (R-03).
export const LOGIN_FAILED_PATH = "/logowanie-nieudane";

// Rendered without the session gate: checking the session here could loop a refused login.
export function LoginFailed() {
  return (
    <main id="main" className="session-screen" tabIndex={-1}>
      <p className="session-product">{messages.productName}</p>
      <h1>{messages.loginFailed.title}</h1>
      <p>{messages.loginFailed.explanation}</p>
      <button
        type="button"
        className="button button-primary"
        onClick={() => {
          pageNavigation.assign(loginUrl("/", ""));
        }}
      >
        {messages.loginFailed.retry}
      </button>
    </main>
  );
}
