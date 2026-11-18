import { useSyncExternalStore } from "react";

// The SPA's one client-side navigation: the shell and every screen read the same location, so a
// screen that navigates needs no handle on the shell.
const NAVIGATED = "eko:navigated";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(NAVIGATED, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(NAVIGATED, onChange);
  };
}

function currentPath(): string {
  return window.location.pathname;
}

export function useLocationPath(): string {
  return useSyncExternalStore(subscribe, currentPath);
}

export function navigateTo(href: string): void {
  window.history.pushState(null, "", href);
  window.dispatchEvent(new Event(NAVIGATED));
}

// An ordinary click on an in-app link is taken over; a modified or middle click keeps the
// browser's own handling (a new tab, a download).
export function followLink(
  event: {
    button: number;
    altKey: boolean;
    ctrlKey: boolean;
    metaKey: boolean;
    shiftKey: boolean;
    preventDefault: () => void;
  },
  href: string,
): void {
  const ordinaryClick =
    event.button === 0 && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey;
  if (ordinaryClick) {
    event.preventDefault();
    navigateTo(href);
  }
}
