import { lazy, Suspense, useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { AppShell } from "./components/AppShell";
import { messages } from "./i18n/pl";

const Customers = lazy(() => import("./features/Klienci"));

interface AppProps {
  account?: ReactNode;
}

export function App({ account }: AppProps = {}) {
  const [path, setPath] = useState(() => window.location.pathname);
  const dashboardActive = path !== "/klienci";

  useEffect(() => {
    const followHistory = () => {
      setPath(window.location.pathname);
    };
    window.addEventListener("popstate", followHistory);
    return () => {
      window.removeEventListener("popstate", followHistory);
    };
  }, []);

  const navigate = (href: string) => {
    window.history.pushState(null, "", href);
    setPath(href);
  };

  const followDestination = (event: MouseEvent<HTMLAnchorElement>, href: string) => {
    const ordinaryClick =
      event.button === 0 && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey;
    if (ordinaryClick) {
      event.preventDefault();
      navigate(href);
    }
  };

  return (
    <AppShell
      section={dashboardActive ? messages.dashboard : messages.customers}
      navigationItems={[{ href: "/", label: messages.dashboard, current: dashboardActive }]}
      onNavigate={navigate}
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
              href="/klienci"
              onClick={(event) => {
                followDestination(event, "/klienci");
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
