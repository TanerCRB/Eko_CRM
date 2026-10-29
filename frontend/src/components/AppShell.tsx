import { useId, useState, type ReactNode } from "react";
import mark from "../assets/mark.svg";
import { messages } from "../i18n/pl";
import { apiClient } from "@/api/client";

interface AppShellProps {
  section: string;
  children: ReactNode;
}

export function AppShell({ section, children }: AppShellProps) {
  const navId = useId();
  const [navOpen, setNavOpen] = useState(false);

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
      >
        <div className="brand">
          <img src={mark} alt="" width={39} height={39} />
          <div>
            <strong>
              <span className="sr-only">{messages.productName}</span>
              {/* The wordmark is styled lower case; assistive technology reads the name above. */}
              <span aria-hidden="true">
                eko<span className="brand-light">crm</span>
              </span>
            </strong>
            <small>{messages.productTagline}</small>
          </div>
        </div>
        <a className="nav-link" href="/" aria-current="page">
          {messages.dashboard}
        </a>
      </nav>
      <div className="workspace">
        <header className="topbar">
          <button
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
