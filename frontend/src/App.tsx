import { AppShell } from "./components/AppShell";
import { messages } from "./i18n/pl";

export function App() {
  return (
    <AppShell section={messages.dashboard}>
      <div className="page-heading">
        <h1>{messages.dashboard}</h1>
        <p>{messages.dashboardIntro}</p>
      </div>
      <section className="welcome-panel" aria-labelledby="welcome-title">
        <h2 id="welcome-title">{messages.welcomeTitle}</h2>
        <p>{messages.welcomeBody}</p>
      </section>
    </AppShell>
  );
}
