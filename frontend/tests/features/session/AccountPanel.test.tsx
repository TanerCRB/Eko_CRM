import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { AccountPanel } from "../../../src/features/session/AccountPanel";
import { pageNavigation } from "../../../src/api/navigation";
import { LOGOUT_URL, stubFetch, unauthenticated, unavailable, type Reply } from "../../support/http";

const session = { subject: "synthetic-subject-0001", name: "Anna Testowa" };
const loggedOut: Reply = { status: 200, body: { status: "logged_out" } };

let assign: MockInstance<(url: string) => void>;

beforeEach(() => {
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.history.replaceState(null, "", "/klienci?x=1");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

const logoutButton = () => screen.getByRole("button", { name: "Wyloguj się" });

describe("K-03 / G-2: the shell names the signed-in user", () => {
  it("shows the session's display name", () => {
    render(<AccountPanel session={session} />);

    expect(screen.getByText("Anna Testowa")).toBeInTheDocument();
    expect(screen.queryByText("Zalogowany użytkownik")).not.toBeInTheDocument();
  });

  it.each([
    ["null", null],
    ["empty", ""],
    ["blank", "   "],
  ])("falls back to a neutral Polish label when the name is %s", (_label, name) => {
    render(<AccountPanel session={{ subject: "synthetic-subject-0002", name }} />);

    expect(screen.getByText("Zalogowany użytkownik")).toBeInTheDocument();
    expect(screen.queryByText("synthetic-subject-0002")).not.toBeInTheDocument();
  });
});

describe("K-03 / G-2: logout", () => {
  it("POSTs to the logout operation same-origin and then loads the root page", async () => {
    const { calls } = stubFetch({ [LOGOUT_URL]: [loggedOut] });
    const user = userEvent.setup();
    render(<AccountPanel session={session} />);

    await user.click(logoutButton());

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe(LOGOUT_URL);
    expect(calls[0]?.init?.method).toBe("POST");
    expect(calls[0]?.init?.credentials).toBe("same-origin");
    expect(calls[0]?.init?.body).toBeUndefined();
  });

  it("treats 401 as already logged out: loads the root page, not a login with return_to", async () => {
    stubFetch({ [LOGOUT_URL]: [unauthenticated] });
    const user = userEvent.setup();
    render(<AccountPanel session={session} />);

    await user.click(logoutButton());

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
  });

  it("keeps the user signed in on 503, shows an error and allows a retry", async () => {
    const { calls } = stubFetch({ [LOGOUT_URL]: [unavailable, loggedOut] });
    const user = userEvent.setup();
    render(<AccountPanel session={session} />);

    await user.click(logoutButton());

    expect(await screen.findByText("Nie udało się wylogować. Spróbuj ponownie.")).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
    expect(screen.getByText("Anna Testowa")).toBeInTheDocument();
    expect(logoutButton()).toBeEnabled();

    await user.click(logoutButton());

    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
    expect(calls).toHaveLength(2);
  });

  it.each([
    ["a network failure", "network-error" as const],
    ["403", { status: 403, body: { detail: "origin refused" } } as const],
  ])("keeps the user signed in on %s", async (_label, reply) => {
    stubFetch({ [LOGOUT_URL]: [reply] });
    const user = userEvent.setup();
    render(<AccountPanel session={session} />);

    await user.click(logoutButton());

    expect(await screen.findByText("Nie udało się wylogować. Spróbuj ponownie.")).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });

  it("sends one logout for a double click while the first is in flight", async () => {
    let release: (value: Response) => void = () => undefined;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<AccountPanel session={session} />);

    await user.dblClick(logoutButton());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(logoutButton()).toBeDisabled();
    release(new Response('{"status":"logged_out"}', { status: 200 }));
    await waitFor(() => {
      expect(assign).toHaveBeenCalledExactlyOnceWith("/");
    });
  });

  it("announces the logout failure in a live region outside the sidebar", async () => {
    stubFetch({ [LOGOUT_URL]: [unavailable] });
    const user = userEvent.setup();
    const view = render(
      <nav aria-label="Nawigacja główna">
        <AccountPanel session={session} />
      </nav>,
    );

    await user.click(logoutButton());

    const toast = await screen.findByRole("status");
    expect(toast).toHaveTextContent("Nie udało się wylogować. Spróbuj ponownie.");
    expect(within(view.container).queryByRole("status")).not.toBeInTheDocument();
  });
});
