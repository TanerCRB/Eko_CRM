import { readdirSync, readFileSync } from "node:fs";
import { extname, join } from "node:path";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { pageNavigation } from "../src/api/navigation";
import { mount } from "../src/mount";
import { LOGOUT_URL, SESSION_URL, signedIn, stubFetch, unauthenticated } from "./support/http";

let unmount: (() => void) | undefined;
let assign: MockInstance<(url: string) => void>;

function mountPage() {
  document.body.innerHTML = '<div id="root"></div>';
  act(() => {
    unmount = mount(document);
  });
}

beforeEach(() => {
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  act(() => unmount?.());
  unmount = undefined;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

const shell = () => screen.queryByRole("navigation", { name: "Nawigacja główna" });

describe("K-03: the page the entry mounts is behind the session gate", () => {
  it.each(["/", "/klienci"])("sends an anonymous visit to %s to login and never shows the shell", async (path) => {
    window.history.replaceState(null, "", path);
    stubFetch({ [SESSION_URL]: [unauthenticated] });
    mountPage();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith(
        `/api/auth/login?return_to=${encodeURIComponent(path)}`,
      );
    });
    expect(shell()).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Pulpit" })).not.toBeInTheDocument();
  });

  it("contrast: with a valid session the same page shows the shell, the user's name and logout", async () => {
    window.history.replaceState(null, "", "/");
    stubFetch({ [SESSION_URL]: [signedIn("Anna Testowa")] });
    mountPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Pulpit" })).toBeVisible();
    const navigation = screen.getByRole("navigation", { name: "Nawigacja główna" });
    expect(within(navigation).getByText("Anna Testowa")).toBeInTheDocument();
    expect(within(navigation).getByRole("button", { name: "Wyloguj się" })).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });

  it("shows the neutral fallback in the shell when the session has no name", async () => {
    stubFetch({ [SESSION_URL]: [signedIn(null)] });
    mountPage();

    const navigation = await screen.findByRole("navigation", { name: "Nawigacja główna" });
    expect(within(navigation).getByText("Zalogowany użytkownik")).toBeInTheDocument();
  });
});

// Records every touch of a browser store, so the auth flow is proven to use none of them.
function trapBrowserStores() {
  const touched: string[] = [];
  const restorers: Array<() => void> = [];
  const trap = (target: object, key: string) => {
    const own = Object.getOwnPropertyDescriptor(target, key);
    Object.defineProperty(target, key, {
      configurable: true,
      get() {
        touched.push(`${key}:read`);
        return undefined;
      },
      set() {
        touched.push(`${key}:write`);
      },
    });
    restorers.push(() => {
      if (own === undefined) {
        Reflect.deleteProperty(target, key);
      } else {
        Object.defineProperty(target, key, own);
      }
    });
  };
  trap(document, "cookie");
  for (const key of ["localStorage", "sessionStorage", "indexedDB", "caches"]) {
    trap(window, key);
    if (globalThis !== window) {
      trap(globalThis, key);
    }
  }
  return {
    touched,
    restore: () => {
      restorers.reverse().forEach((restore) => {
        restore();
      });
    },
  };
}

describe("K-01/K-02 boundary: the frontend never touches cookies or browser storage for auth", () => {
  it("runs anonymous redirect, sign-in and logout without reading cookies or any browser store", async () => {
    const stores = trapBrowserStores();
    try {
      window.history.replaceState(null, "", "/klienci");
      stubFetch({ [SESSION_URL]: [unauthenticated] });
      mountPage();
      await waitFor(() => {
        expect(assign).toHaveBeenCalledTimes(1);
      });
      act(() => unmount?.());

      stubFetch({
        [SESSION_URL]: [signedIn("Anna Testowa")],
        [LOGOUT_URL]: [{ status: 200, body: { status: "logged_out" } }],
      });
      mountPage();
      const user = userEvent.setup();
      await user.click(await screen.findByRole("button", { name: "Wyloguj się" }));
      await waitFor(() => {
        expect(assign).toHaveBeenLastCalledWith("/");
      });

      expect(stores.touched).toEqual([]);

      // Contrast: the trap does see a store access when one happens.
      Reflect.get(document, "cookie");
      Reflect.get(window, "localStorage");
      expect(stores.touched).toEqual(["cookie:read", "localStorage:read"]);
    } finally {
      stores.restore();
    }
  });
});

const forbidden = {
  cookie: /document\s*\.\s*cookie/,
  webStorage: /localStorage|sessionStorage/,
  indexedDb: /indexedDB/,
  cacheStorage: /\bcaches\s*\./,
  serviceWorker: /serviceWorker/,
  bearer: /Authorization|Bearer\s/i,
  tokenField: /access_token|refresh_token|id_token/,
} as const;

function findings(source: string): string[] {
  return Object.entries(forbidden)
    .filter(([, pattern]) => pattern.test(source))
    .map(([name]) => name);
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(path) : [path];
  });
}

describe("K-01/K-02 boundary: production source holds no cookie, storage or token handling", () => {
  it("finds none of the forbidden mechanisms in frontend/src", () => {
    const sources = sourceFiles(join(process.cwd(), "src")).filter((path) =>
      [".ts", ".tsx", ".js", ".jsx"].includes(extname(path)),
    );
    expect(sources.length).toBeGreaterThan(0);
    const violations = sources.flatMap((path) =>
      findings(readFileSync(path, "utf8")).map((finding) => `${path}: ${finding}`),
    );
    expect(violations).toEqual([]);
  });

  it.each([
    ["cookie", "const raw = document.cookie;"],
    ["webStorage", "window.localStorage.setItem('k', v);"],
    ["webStorage", "sessionStorage.getItem('k');"],
    ["indexedDb", "indexedDB.open('eko');"],
    ["cacheStorage", "await caches.open('api');"],
    ["serviceWorker", "navigator.serviceWorker.register('/sw.js');"],
    ["bearer", "headers: { Authorization: `Bearer ${t}` }"],
    ["tokenField", "const t = body.access_token;"],
  ])("rejects a minimal fixture using %s", (finding, fixture) => {
    expect(findings(fixture)).toContain(finding);
  });
});
