import { useEffect, useId, useRef, useState, type MouseEvent, type ReactNode } from "react";
import mark from "../assets/mark.svg";
import { messages } from "../i18n/pl";

export interface NavigationItem {
  href: string;
  label: string;
  current?: boolean;
}

interface AppShellProps {
  section: string;
  children: ReactNode;
  navigationItems?: readonly NavigationItem[];
  onNavigate?: (href: string) => void;
}

const mobileNavigationQuery = "(max-width: 700px)";

export function AppShell({
  section,
  children,
  navigationItems = [{ href: "/", label: messages.dashboard, current: true }],
  onNavigate,
}: AppShellProps) {
  const navId = useId();
  const menuRef = useRef<HTMLButtonElement>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [mobileNavigation, setMobileNavigation] = useState(
    () => typeof window.matchMedia === "function" && window.matchMedia(mobileNavigationQuery).matches,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia(mobileNavigationQuery);
    const followViewport = (event: MediaQueryListEvent) => {
      setMobileNavigation(event.matches);
    };
    query.addEventListener("change", followViewport);
    return () => {
      query.removeEventListener("change", followViewport);
    };
  }, []);

  useEffect(() => {
    if (!navOpen) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setNavOpen(false);
        menuRef.current?.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [navOpen]);

  const activateDestination = (href: string, event: MouseEvent<HTMLAnchorElement>) => {
    setNavOpen(false);
    const ordinaryClick =
      event.button === 0 && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey;
    if (onNavigate && ordinaryClick) {
      event.preventDefault();
      onNavigate(href);
    }
  };

  return (
    <>
      <a className="skip-link" href="#main">
        {messages.skipToContent}
      </a>
      <nav
        id={navId}
        className="sidebar"
        data-open={navOpen}
        aria-label={messages.mainNavigation}
        inert={mobileNavigation && !navOpen}
      >
        <div className="brand">
          <img src={mark} alt="" width={39} height={39} />
          <div>
            <strong>
              <span className="sr-only">{messages.productName}</span>
              <span aria-hidden="true">
                eko<span className="brand-light">crm</span>
              </span>
            </strong>
            <small>{messages.productTagline}</small>
          </div>
        </div>
        {navigationItems.map((item) => (
          <a
            key={item.href}
            className="nav-link"
            href={item.href}
            aria-current={item.current ? "page" : undefined}
            onClick={(event) => {
              activateDestination(item.href, event);
            }}
          >
            {item.label}
          </a>
        ))}
      </nav>
      <div className="workspace">
        <header className="topbar">
          <button
            ref={menuRef}
            type="button"
            className="menu-button"
            aria-label={messages.toggleNavigation}
            aria-controls={navId}
            aria-expanded={navOpen}
            onClick={() => {
              setNavOpen((open) => !open);
            }}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
              <path
                d="M4 7h16M4 12h16M4 17h16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <p className="breadcrumb">
            <strong>{section}</strong>
          </p>
        </header>
        <main id="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </>
  );
}
