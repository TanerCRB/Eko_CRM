import { lazy, Suspense, type ReactNode } from "react";
import { AppShell } from "./components/AppShell";
import { messages } from "./i18n/pl";
import { CUSTOMERS_PATH } from "./features/customers/paths";
import { isVisitsPath, MY_DAY_PATH, VISITS_PATH } from "./features/visits/paths";
import { followLink, navigateTo, useLocationPath } from "./routing/location";

const Customers = lazy(() => import("./features/Klienci"));
const Visits = lazy(() => import("./features/Wizyty"));

interface AppProps {
  account?: ReactNode;
}

function DestinationLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      className="button button-leaf lazy-destination"
      href={href}
      onClick={(event) => {
        followLink(event, href);
      }}
    >
      {label}
    </a>
  );
}

export function App({ account }: AppProps = {}) {
  const path = useLocationPath();
  const customersActive = path === CUSTOMERS_PATH || path.startsWith(`${CUSTOMERS_PATH}/`);
  const visitsActive = isVisitsPath(path);
  const dashboardActive = !customersActive && !visitsActive;
  const section = customersActive
    ? messages.customers
    : visitsActive
      ? path === MY_DAY_PATH
        ? messages.myDay
        : messages.visits
      : messages.dashboard;

  return (
    <AppShell
      section={section}
      navigationItems={[{ href: "/", label: messages.dashboard, current: dashboardActive }]}
      onNavigate={navigateTo}
      account={account}
    >
      {dashboardActive ? (
        <>
          <div className="page-heading">
            <h1>{messages.dashboard}</h1>
            <p>{messages.dashboardIntro}</p>
          </div>
          <section className="welcome-panel" aria-labelledby="welcome-title">
            <h2 id="welcome-title">{messages.welcomeTitle}</h2>
            <p>{messages.welcomeBody}</p>
            <DestinationLink href={MY_DAY_PATH} label={messages.myDay} />
            <DestinationLink href={VISITS_PATH} label={messages.visits} />
            <DestinationLink href={CUSTOMERS_PATH} label={messages.customers} />
          </section>
        </>
      ) : (
        <Suspense fallback={<p role="status">{messages.loading}</p>}>
          {customersActive ? <Customers /> : <Visits />}
        </Suspense>
      )}
    </AppShell>
  );
}
