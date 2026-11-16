import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import { AccountPanel } from "../../../src/features/session/AccountPanel";
import { SessionGate } from "../../../src/features/session/SessionGate";
import {
  LOGOUT_URL,
  SESSION_URL,
  respond,
  signedIn,
  stubFetch,
  unauthenticated,
  unavailable,
  type Call,
  type Reply,
} from "../../support/http";

// EKO-2-02 K-08: a 403 on the session read means "authenticated, no application role" (ADR-0003
// roles addendum, 2026-11-16, section 1); only the status decides, so the body is never read.

const noRole: Reply = { status: 403, body: { detail: "no application role" } };
const loggedOut: Reply = { status: 200, body: { status: "logged_out" } };

const SUBJECT = "synthetic-subject-0001";
const NAME = "Anna Testowa";
const INVALID_TEXT = "Nie udało się sprawdzić sesji.";
const LOGOUT_FAILED_TEXT = "Nie udało się wylogować. Spróbuj ponownie.";

// The composition mount() renders, so "no shell" is checked against the real shell.
function renderApp() {
  return render(
    <SessionGate retryDelaysMs={[]}>
      {(session) => <App account={<AccountPanel session={session} />} />}
    </SessionGate>,
  );
}

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
}

// The typed stub serves raw bodies only on 200, and these 403 bodies are deliberately off-contract.
function stubRawNoRoleSession(sessionBody: string) {
  const calls: Call[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    calls.push({ url, init });
    return url === SESSION_URL
      ? Promise.resolve(new Response(sessionBody, { status: 403 }))
      : Promise.reject(new Error(`Unexpected request to ${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

const logoutButton = () => screen.getByRole("button", { name: "Wyloguj się" });
const findLogoutButton = () => screen.findByRole("button", { name: "Wyloguj się" });
const queryLogoutButton = () => screen.queryByRole("button", { name: "Wyloguj się" });
const shell = () => screen.queryByRole("navigation", { name: "Nawigacja główna" });
const accountPanel = () => screen.queryByRole("region", { name: "Konto" });
const urls = (calls: readonly Call[]) => calls.map((call) => call.url);

let assign: MockInstance<(url: string) => void>;

beforeEach(() => {
  window.history.replaceState(null, "", "/klienci?x=1");
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("K-08: a 403 on the session read is the no-role screen", () => {
  it("shows the no-role screen with a logout action on 403 and renders neither the shell nor a login redirect", async () => {
    const { calls } = stubFetch({ [SESSION_URL]: [noRole] });
    renderApp();

    expect(await findLogoutButton()).toBeEnabled();
    expect(shell()).not.toBeInTheDocument();
    expect(accountPanel()).not.toBeInTheDocument();
    expect(screen.queryByText(INVALID_TEXT)).not.toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
    expect(urls(calls)).toEqual([SESSION_URL]);
  });

  it.each([
    ["empty", ""],
    ["not JSON", "<html>forbidden</html>"],
    ["JSON naming a subject", `{"subject":"${SUBJECT}","name":"${NAME}"}`],
  ])(
    "edge: a 403 whose body is %s still shows the no-role screen and no subject or name",
    async (_label, rawBody) => {
      const { calls } = stubRawNoRoleSession(rawBody);
      renderApp();

      expect(await findLogoutButton()).toBeEnabled();
      expect(shell()).not.toBeInTheDocument();
      expect(screen.queryByText(INVALID_TEXT)).not.toBeInTheDocument();
      expect(screen.queryByText(SUBJECT, { exact: false })).not.toBeInTheDocument();
      expect(screen.queryByText(NAME, { exact: false })).not.toBeInTheDocument();
      expect(assign).not.toHaveBeenCalled();
      expect(urls(calls)).toEqual([SESSION_URL]);
    },
  );

  it("logout from the no-role screen POSTs the logout operation same-origin with no body and then loads the root page", async () => {
    const { calls } = stubFetch({ [SESSION_URL]: [noRole], [LOGOUT_URL]: [loggedOut] });
    const user = userEvent.setup();
    renderApp();

    await user.click(await findLogoutButton());

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
    expect(urls(calls)).toEqual([SESSION_URL, LOGOUT_URL]);
    const logoutCall = calls[1];
    expect(logoutCall?.init?.method).toBe("POST");
    expect(logoutCall?.init?.credentials).toBe("same-origin");
    expect(logoutCall?.init?.body).toBeUndefined();
  });

  it("contrast: 401 redirects to login and 500 shows the invalid screen, neither offering the no-role logout", async () => {
    stubFetch({ [SESSION_URL]: [unauthenticated] });
    const anonymous = renderApp();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/api/auth/login?return_to=%2Fklienci%3Fx%3D1");
    });
    expect(queryLogoutButton()).not.toBeInTheDocument();
    expect(shell()).not.toBeInTheDocument();
    anonymous.unmount();
    vi.unstubAllGlobals();
    assign.mockClear();

    const notAContractAnswer = [
      { status: 500, body: { detail: "boom" } },
      { status: 200, raw: '{"name":"Anna"}' },
    ] as const satisfies readonly Reply[];
    for (const reply of notAContractAnswer) {
      stubFetch({ [SESSION_URL]: [reply] });
      const view = renderApp();

      expect(await screen.findByRole("alert")).toHaveTextContent(INVALID_TEXT);
      expect(screen.getByRole("button", { name: "Spróbuj ponownie" })).toBeInTheDocument();
      expect(queryLogoutButton()).not.toBeInTheDocument();
      expect(shell()).not.toBeInTheDocument();
      expect(assign).not.toHaveBeenCalled();
      view.unmount();
      vi.unstubAllGlobals();
    }
  });

  it("contrast: 200 on the session read shows the shell and its account panel, not the no-role screen", async () => {
    stubFetch({ [SESSION_URL]: [signedIn(NAME, SUBJECT)] });
    renderApp();

    expect(await screen.findByRole("navigation", { name: "Nawigacja główna" })).toBeInTheDocument();
    expect(accountPanel()).toBeInTheDocument();
    expect(screen.getByText(NAME)).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});

describe("K-08: logout outcomes on the no-role screen", () => {
  it("503 or a network failure on logout keeps the no-role screen, shows the logout failure and allows a retry", async () => {
    const { calls } = stubFetch({
      [SESSION_URL]: [noRole],
      [LOGOUT_URL]: [unavailable, "network-error", loggedOut],
    });
    const user = userEvent.setup();
    renderApp();
    await findLogoutButton();

    for (const attempt of [1, 2]) {
      await user.click(logoutButton());

      expect(await screen.findByText(LOGOUT_FAILED_TEXT)).toBeInTheDocument();
      expect(calls).toHaveLength(1 + attempt);
      expect(assign).not.toHaveBeenCalled();
      expect(shell()).not.toBeInTheDocument();
      expect(logoutButton()).toBeEnabled();
    }

    await user.click(logoutButton());

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
    expect(urls(calls)).toEqual([SESSION_URL, LOGOUT_URL, LOGOUT_URL, LOGOUT_URL]);
  });

  it("401 on logout is treated as already logged out and loads the root page", async () => {
    const { calls } = stubFetch({ [SESSION_URL]: [noRole], [LOGOUT_URL]: [unauthenticated] });
    const user = userEvent.setup();
    renderApp();

    await user.click(await findLogoutButton());

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
    expect(urls(calls)).toEqual([SESSION_URL, LOGOUT_URL]);
    expect(screen.queryByText(LOGOUT_FAILED_TEXT)).not.toBeInTheDocument();
  });

  it("a double click sends one logout", async () => {
    let release: (value: Response) => void = () => undefined;
    const typed = stubFetch({ [SESSION_URL]: [noRole] });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (requestUrl(input) === LOGOUT_URL) {
        typed.calls.push({ url: LOGOUT_URL, init });
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }
      return typed.fetchMock(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp();

    await user.dblClick(await findLogoutButton());

    expect(urls(typed.calls)).toEqual([SESSION_URL, LOGOUT_URL]);
    expect(assign).not.toHaveBeenCalled();
    release(await respond(loggedOut));
    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
    expect(urls(typed.calls)).toEqual([SESSION_URL, LOGOUT_URL]);
  });
});
