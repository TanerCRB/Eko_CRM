import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import type { SessionInfo } from "../../../src/api/auth";
import { SessionGate, type Schedule } from "../../../src/features/session/SessionGate";
import { pageNavigation } from "../../../src/api/navigation";
import {
  SESSION_URL,
  signedIn,
  stubFetch,
  unauthenticated,
  unavailable,
  type Reply,
} from "../../support/http";

interface Scheduled {
  run: () => void;
  delayMs: number;
  cancelled: boolean;
}

function manualClock() {
  const scheduled: Scheduled[] = [];
  const schedule: Schedule = (run, delayMs) => {
    const entry = { run, delayMs, cancelled: false };
    scheduled.push(entry);
    return () => {
      entry.cancelled = true;
    };
  };
  const fireNext = () => {
    const next = scheduled.find((entry) => !entry.cancelled);
    if (next === undefined) {
      throw new Error("Nothing is scheduled");
    }
    next.cancelled = true;
    act(() => {
      next.run();
    });
  };
  return { scheduled, schedule, fireNext };
}

const DELAYS = [1000, 2000, 4000] as const;

function Protected({ session }: { session: SessionInfo }) {
  return (
    <nav aria-label="Nawigacja główna">
      <p>shell for {session.subject}</p>
    </nav>
  );
}

function renderGate(replies: readonly Reply[], clock = manualClock()) {
  const http = stubFetch({ [SESSION_URL]: replies });
  render(
    <SessionGate retryDelaysMs={DELAYS} schedule={clock.schedule}>
      {(session) => <Protected session={session} />}
    </SessionGate>,
  );
  return { ...http, clock };
}

const shell = () => screen.queryByRole("navigation", { name: "Nawigacja główna" });

let assign: MockInstance<(url: string) => void>;

beforeEach(() => {
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("K-03: anonymous navigation is sent to login before the shell renders", () => {
  it("redirects an anonymous deep link to login with the exact encoded path and query", async () => {
    window.history.replaceState(null, "", "/klienci?recovery=1&q=a b");
    const { calls } = renderGate([unauthenticated]);

    await waitFor(() => {
      expect(assign).toHaveBeenCalledTimes(1);
    });
    // location.search already holds the space as %20; return_to decodes back to that exact URL.
    expect(assign).toHaveBeenCalledExactlyOnceWith(
      "/api/auth/login?return_to=%2Fklienci%3Frecovery%3D1%26q%3Da%2520b",
    );
    const target = new URL(String(assign.mock.calls[0]?.[0]), "https://eko.invalid");
    expect(target.searchParams.get("return_to")).toBe("/klienci?recovery=1&q=a%20b");
    expect(calls.map((call) => call.url)).toEqual([SESSION_URL]);
    expect(shell()).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Przekierowanie do logowania…");
  });

  it("redirects an anonymous visit to the root with return_to=%2F", async () => {
    window.history.replaceState(null, "", "/");
    renderGate([unauthenticated]);

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/api/auth/login?return_to=%2F");
    });
    expect(shell()).not.toBeInTheDocument();
  });

  it("does not render the shell while the session check is still pending", () => {
    window.history.replaceState(null, "", "/klienci");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    render(<SessionGate>{(session) => <Protected session={session} />}</SessionGate>);

    expect(shell()).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Sprawdzanie sesji…");
    expect(assign).not.toHaveBeenCalled();
  });

  it("contrast: the same deep link with a valid session stays in the shell without a redirect", async () => {
    window.history.replaceState(null, "", "/klienci?recovery=1&q=a b");
    renderGate([signedIn("Anna Testowa")]);

    expect(await screen.findByText("shell for synthetic-subject-0001")).toBeInTheDocument();
    expect(shell()).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
    expect(window.location.pathname + window.location.search).toBe("/klienci?recovery=1&q=a%20b");
  });

  it("asks for the session same-origin with GET, carrying no credentials of its own", async () => {
    const { calls } = renderGate([signedIn(null)]);
    await screen.findByText("shell for synthetic-subject-0001");

    expect(calls).toHaveLength(1);
    const [call] = calls;
    expect(call?.init?.method).toBe("GET");
    expect(call?.init?.credentials).toBe("same-origin");
    expect(new Headers(call?.init?.headers).has("authorization")).toBe(false);
  });
});

describe("K-03: an unavailable session service is a busy state, never a logout", () => {
  it("shows a busy state on 503, retries after the first delay and then admits the session", async () => {
    const { calls, clock } = renderGate([unavailable, signedIn("Anna Testowa")]);

    expect(await screen.findByText(/Logowanie jest chwilowo niedostępne/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Ponawiamy próbę połączenia…");
    expect(shell()).not.toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
    expect(clock.scheduled.map((entry) => entry.delayMs)).toEqual([1000]);

    clock.fireNext();

    expect(await screen.findByText("shell for synthetic-subject-0001")).toBeInTheDocument();
    expect(calls).toHaveLength(2);
    expect(assign).not.toHaveBeenCalled();
  });

  it("treats a network failure like 503: busy, retried, not redirected", async () => {
    const { calls, clock } = renderGate(["network-error", signedIn(null)]);

    expect(await screen.findByText(/Logowanie jest chwilowo niedostępne/)).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();

    clock.fireNext();

    expect(await screen.findByText("shell for synthetic-subject-0001")).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });

  it("backs off with the bounded delays, then stops retrying on its own and offers a manual retry", async () => {
    const { calls, clock } = renderGate([unavailable]);
    await screen.findByText(/Logowanie jest chwilowo niedostępne/);

    for (let fired = 0; fired < DELAYS.length; fired += 1) {
      const before = calls.length;
      clock.fireNext();
      await waitFor(() => {
        expect(calls).toHaveLength(before + 1);
      });
    }

    expect(await screen.findByText("Spróbuj ponownie za chwilę.")).toBeInTheDocument();
    expect(clock.scheduled.map((entry) => entry.delayMs)).toEqual([...DELAYS]);
    expect(clock.scheduled.every((entry) => entry.cancelled)).toBe(true);
    expect(calls).toHaveLength(1 + DELAYS.length);
    expect(assign).not.toHaveBeenCalled();
    expect(shell()).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));
    await waitFor(() => {
      expect(calls).toHaveLength(2 + DELAYS.length);
    });
    expect(assign).not.toHaveBeenCalled();
  });

  it("contrast: a 401 after a 503 retry redirects exactly once", async () => {
    window.history.replaceState(null, "", "/klienci");
    const { clock } = renderGate([unavailable, unauthenticated]);
    await screen.findByText(/Logowanie jest chwilowo niedostępne/);
    expect(assign).not.toHaveBeenCalled();

    clock.fireNext();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/api/auth/login?return_to=%2Fklienci");
    });
  });

  it("cancels a pending retry when the gate unmounts", async () => {
    const clock = manualClock();
    const { calls } = stubFetch({ [SESSION_URL]: [unavailable] });
    const view = render(
      <SessionGate retryDelaysMs={DELAYS} schedule={clock.schedule}>
        {(session) => <Protected session={session} />}
      </SessionGate>,
    );
    await screen.findByText(/Logowanie jest chwilowo niedostępne/);
    view.unmount();

    expect(clock.scheduled).toHaveLength(1);
    expect(clock.scheduled[0]?.cancelled).toBe(true);
    expect(calls).toHaveLength(1);
  });
});

describe("K-03: a session answer the contract does not describe is an error, not a shell", () => {
  it.each([
    ["a body that is not JSON", { status: 200, raw: "<html>" } as const],
    ["a body without a subject", { status: 200, raw: '{"name":"Anna"}' } as const],
    ["an empty subject", { status: 200, raw: '{"subject":"","name":null}' } as const],
    ["a name that is not a string", { status: 200, raw: '{"subject":"s","name":7}' } as const],
    ["a 500 response", { status: 500, body: { detail: "boom" } } as const],
  ])("shows a visible error for %s and neither renders the shell nor redirects", async (_label, reply) => {
    renderGate([reply]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Nie udało się sprawdzić sesji.");
    expect(screen.getByRole("button", { name: "Spróbuj ponownie" })).toBeInTheDocument();
    expect(shell()).not.toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });

  it("contrast: the same session with an extra field still enters the shell", async () => {
    renderGate([{ status: 200, raw: '{"subject":"synthetic-subject-0001","name":null,"extra":1}' }]);

    expect(await screen.findByText("shell for synthetic-subject-0001")).toBeInTheDocument();
  });
});
