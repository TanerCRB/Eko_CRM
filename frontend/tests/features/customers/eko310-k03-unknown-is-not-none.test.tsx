import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { pageNavigation } from "../../../src/api/navigation";
import { deferred } from "../../support/customers-http";
import {
  FIRST_TEXT,
  FIRST_TITLE,
  type ListAnswer,
  listOf,
  mountListScreen,
  NO_MATCH_TITLE,
  NOTHING,
  POINTER_TEXT,
  POINTER_TITLE,
  searchBox,
  settle,
  stateButton,
  stubListScreen,
  unmountListScreen,
} from "../../support/customer-list-screen";

// EKO-3-10 K-03: the first-customer text needs the server's answer that no archived customer
// exists; held, failed or unreadable is not that answer, and a late one never wins (G-3 A).

const LIST_FAILED = "Nie udało się wczytać listy klientów.";

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  unmountListScreen();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function expectNeitherEmptyText() {
  expect(screen.queryByText(FIRST_TITLE)).not.toBeInTheDocument();
  expect(screen.queryByText(FIRST_TEXT)).not.toBeInTheDocument();
  expect(screen.queryByText(POINTER_TITLE)).not.toBeInTheDocument();
  expect(screen.queryByText(POINTER_TEXT)).not.toBeInTheDocument();
}

// Serves the answers in order, one per request; a request past the last one fails the test.
function inTurn(...answers: (ListAnswer | Promise<ListAnswer>)[]) {
  const queue = [...answers];
  return () => {
    const next = queue.shift();
    return next === undefined
      ? Promise.reject(new Error("more requests than answers"))
      : Promise.resolve(next);
  };
}

describe("K-03 held: while the archived answer is pending, neither empty text is shown", () => {
  it("shows the loading status until the held answer is released as none", async () => {
    const held = deferred<ListAnswer>();
    const { lists } = stubListScreen(["rep"], { "||": NOTHING, "||archived": () => held.promise });
    mountListScreen();
    await settle();

    // StrictMode runs the mount effect twice in development: the first default request is dropped.
    expect(lists.map((url) => url.search)).toEqual(["", "", "?state=archived"]);
    expect(screen.getByRole("status")).toHaveTextContent("Ładowanie…");
    expectNeitherEmptyText();

    await act(async () => {
      held.resolve(NOTHING);
      await new Promise((done) => setTimeout(done, 50));
    });

    expect(screen.getByRole("heading", { name: FIRST_TITLE })).toBeVisible();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("edge: a double click on Aktywni while the check is pending sends no second request", async () => {
    const held = deferred<ListAnswer>();
    const { lists } = stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": inTurn(listOf(["Sad Zamknięty", true]), listOf(["Sad Zamknięty", true]), held.promise),
      "||active": NOTHING,
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("heading", { name: POINTER_TITLE });
    await user.click(stateButton("Archiwum"));
    await screen.findByRole("link", { name: "Sad Zamknięty" });
    const before = lists.length;

    await user.dblClick(stateButton("Aktywni"));
    await settle();

    expect(lists.slice(before).map((url) => url.search)).toEqual(["?state=active", "?state=archived"]);
    expect(screen.getByRole("status")).toHaveTextContent("Ładowanie…");
    expectNeitherEmptyText();

    await act(async () => {
      held.resolve(NOTHING);
      await new Promise((done) => setTimeout(done, 50));
    });
    expect(screen.getByRole("heading", { name: FIRST_TITLE })).toBeVisible();
    expect(lists.slice(before)).toHaveLength(2);
  });
});

describe("K-03 failed: a failed or unreadable archived answer shows the list-failed alert", () => {
  const failures: [string, ListAnswer][] = [
    ["a 5xx answer", { status: 500, body: { detail: "synthetic failure" } }],
    ["a network error", "network-error"],
    ["an unreadable body", { status: 200, raw: "{not json" }],
    ["an item outside the contract", { status: 200, raw: '{"items":[{"name":7}]}' }],
  ];

  for (const [label, failure] of failures) {
    it(`${label} shows the alert with its retry, and neither empty text`, async () => {
      stubListScreen(["rep"], { "||": NOTHING, "||archived": failure });
      mountListScreen();

      expect(await screen.findByRole("alert")).toHaveTextContent(LIST_FAILED);
      expect(screen.getByRole("button", { name: "Spróbuj ponownie" })).toBeVisible();
      expectNeitherEmptyText();
    });
  }

  it("the retry re-asks both requests, and a none then gives the first-customer text", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": inTurn({ status: 500, body: { detail: "synthetic failure" } }, NOTHING),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("alert");

    await user.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));

    expect(await screen.findByRole("heading", { name: FIRST_TITLE })).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(lists.map((url) => url.search)).toEqual(["", "", "?state=archived", "", "?state=archived"]);
  });
});

describe("K-03 late: an archived answer for a default list since left never replaces the newer screen", () => {
  it("picking Archiwum while the check is held keeps the archived list when the check lands", async () => {
    const held = deferred<ListAnswer>();
    stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": inTurn(held.promise, listOf(["Sad Zamknięty", true])),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await settle();

    await user.click(stateButton("Archiwum"));
    expect(await screen.findByRole("link", { name: "Sad Zamknięty" })).toBeVisible();
    await act(async () => {
      held.resolve(NOTHING);
      await new Promise((done) => setTimeout(done, 50));
    });

    expect(screen.getByRole("link", { name: "Sad Zamknięty" })).toBeVisible();
    expectNeitherEmptyText();
  });

  it("typing a term while the check is held keeps the search's empty state when the check lands", async () => {
    const held = deferred<ListAnswer>();
    stubListScreen(["rep"], { "||": NOTHING, "||archived": () => held.promise, "kowal||": NOTHING });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await settle();

    await user.type(searchBox(), "kowal{Enter}");
    expect(await screen.findByRole("heading", { name: NO_MATCH_TITLE })).toBeVisible();
    await act(async () => {
      held.resolve(NOTHING);
      await new Promise((done) => setTimeout(done, 50));
    });

    expect(screen.getByRole("heading", { name: NO_MATCH_TITLE })).toBeVisible();
    expectNeitherEmptyText();
  });

  it("edge: an older check answered after a newer one never replaces it", async () => {
    const older = deferred<ListAnswer>();
    stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": inTurn(older.promise, listOf(["Sad Zamknięty", true]), NOTHING),
      "||active": NOTHING,
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await settle();
    await user.click(stateButton("Archiwum"));
    await screen.findByRole("link", { name: "Sad Zamknięty" });
    await user.click(stateButton("Aktywni"));
    expect(await screen.findByRole("heading", { name: FIRST_TITLE })).toBeVisible();

    await act(async () => {
      older.resolve(listOf(["Sad Spóźniony", true]));
      await new Promise((done) => setTimeout(done, 50));
    });

    expect(screen.getByRole("heading", { name: FIRST_TITLE })).toBeVisible();
    expect(screen.queryByText(POINTER_TITLE)).not.toBeInTheDocument();
  });
});
