import { lazy, Suspense, type ReactNode } from "react";
import { AppShell } from "./components/AppShell";
import { messages } from "./i18n/pl";
import { CUSTOMERS_PATH } from "./features/customers/paths";
import { followLink, navigateTo, useLocationPath } from "./routing/location";

const Customers = lazy(() => import("./features/Klienci"));

interface AppProps {
  account?: ReactNode;
}

export function App({ account }: AppProps = {}) {
  const path = useLocationPath();
  const dashboardActive = path !== CUSTOMERS_PATH && !path.startsWith(`${CUSTOMERS_PATH}/`);

  return (
    <AppShell
      section={dashboardActive ? messages.dashboard : messages.customers}
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
            <a
              className="button button-leaf lazy-destination"
              href={CUSTOMERS_PATH}
              onClick={(event) => {
                followLink(event, CUSTOMERS_PATH);
              }}
            >
              {messages.customers}
            </a>
          </section>
        </>
      ) : (
        <Suspense fallback={<p role="status">{messages.loading}</p>}>
          <Customers />
        </Suspense>
      )}
    </AppShell>
  );
}
