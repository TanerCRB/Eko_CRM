import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import type { Problem } from "../../../src/api/auth";
import type { CustomerList, ValidationProblem } from "../../../src/api/customers";
import { pageNavigation } from "../../../src/api/navigation";
import { mount } from "../../../src/mount";
import { CUSTOMERS_URL, deferred } from "../../support/customers-http";
import { type OlderSessionInfo, SESSION_URL } from "../../support/http";

// K-07 (EKO-3-04): the search field is a convenience; the server decides what matches (K-01..K-04).
// Synthetic values throughout (ADR-0005).

type ListReply =
  | { status: 200; body: CustomerList }
  | { status: 422; body: ValidationProblem }
  | { status: 500; body: Problem };

type ListSource = ListReply | (() => Promise<ListReply>);

// Routed by the decoded `q` the request carries ("" when it carries none), so a test states the
// term it expects without depending on how the SPA encodes it.
function stubListApi(byTerm: Record<string, ListSource>, session?: OlderSessionInfo) {
  const lists: URL[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(href, "http://spa.test");
    const method = init?.method ?? "GET";
    if (session !== undefined && method === "GET" && url.pathname === SESSION_URL) {
      return new Response(JSON.stringify(session), { status: 200 });
    }
    if (method !== "GET" || url.pathname !== CUSTOMERS_URL) {
      throw new Error(`Unexpected request ${method} ${href}`);
    }
    lists.push(url);
    const source = byTerm[url.searchParams.get("q") ?? ""];
    if (source === undefined) {
      throw new Error(`Unexpected list request ${href}`);
    }
    const reply = typeof source === "function" ? await source() : source;
    return new Response(JSON.stringify(reply.body), {
      status: reply.status,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { lists };
}

const ID_A = "0a1b2c3d-0000-4000-8000-000000000001";
const ID_B = "0a1b2c3d-0000-4000-8000-000000000002";
const ID_C = "0a1b2c3d-0000-4000-8000-000000000003";

function listOf(...names: string[]): ListReply {
  const ids = [ID_A, ID_B, ID_C];
  return {
    status: 200,
    body: { items: names.map((name, index) => ({ id: ids[index] ?? ID_C, name, country: "PL" })) },
  };
}

const noCustomers: ListReply = { status: 200, body: { items: [] } };

function searchBox() {
  return screen.getByRole("searchbox", { name: "Szukaj klientów" });
}

function searches(lists: readonly URL[]) {
  return lists.filter((url) => url.searchParams.has("q"));
}

function expectNoOwner(lists: readonly URL[]) {
  for (const url of lists) {
    expect([...url.searchParams.keys()].filter((key) => key !== "q")).toEqual([]);
  }
}

// Lets every answer already released travel through the client and into the screen; the
// contrast test below shows this is long enough for an answer to render.
async function settle() {
  await act(async () => {
    await new Promise((done) => setTimeout(done, 50));
  });
}

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.history.replaceState(null, "", "/klienci");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("K-07: the Customers screen sends the search to the server and shows what it answers", () => {
  it("typing a term sends one list request carrying it and no owner parameter", async () => {
    const { lists } = stubListApi({
      "": listOf("Gospodarstwo Startowe"),
      kowal: listOf("Zupełnie Inny"),
    });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByRole("link", { name: "Gospodarstwo Startowe" });

    await user.type(searchBox(), "kowal");

    expect(
      await screen.findByRole("link", { name: "Zupełnie Inny" }, { timeout: 3000 }),
    ).toBeVisible();
    expect(searches(lists).map((url) => url.searchParams.getAll("q"))).toEqual([["kowal"]]);
    expect(lists).toHaveLength(2);
    expect(lists[0]?.search).toBe("");
    expectNoOwner(lists);
  });

  it("shows exactly what the server answered, even an entry the term does not appear in", async () => {
    stubListApi({ "": noCustomers, kowal: listOf("Zupełnie Inny", "Kowal Agro") });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.type(searchBox(), "kowal{Enter}");

    const list = await screen.findByRole("list", { name: "Lista klientów" });
    expect(within(list).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Zupełnie Inny",
      "Kowal Agro",
    ]);
  });

  it("an empty answer to a query shows the no-match state; the same answer without one does not", async () => {
    const { lists } = stubListApi({ "": noCustomers, kowal: noCustomers });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Nie masz jeszcze klientów" })).toBeVisible();
    expect(screen.queryByText("Nie znaleziono klientów")).not.toBeInTheDocument();

    await user.type(searchBox(), "kowal{Enter}");

    expect(await screen.findByRole("heading", { name: "Nie znaleziono klientów" })).toBeVisible();
    expect(screen.getByText("Wpisz inną nazwę, miejscowość lub dane kontaktowe.")).toBeVisible();
    expect(screen.queryByText("Nie masz jeszcze klientów")).not.toBeInTheDocument();

    await user.clear(searchBox());
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("heading", { name: "Nie masz jeszcze klientów" })).toBeVisible();
    expect(screen.queryByText("Nie znaleziono klientów")).not.toBeInTheDocument();
    expect(lists.at(-1)?.search).toBe("");
  });

  it("the term never enters the location or the history", async () => {
    const term = "kowal";
    stubListApi({ "": noCustomers, [term]: listOf("Kowal Agro") });
    const pushState = vi.spyOn(window.history, "pushState");
    const replaceState = vi.spyOn(window.history, "replaceState");
    const seen: string[] = [];
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");
    seen.push(window.location.href);

    await user.type(searchBox(), `${term}{Enter}`);
    await screen.findByRole("link", { name: "Kowal Agro" });
    seen.push(window.location.href);

    for (const href of seen) {
      expect(decodeURIComponent(href).toLowerCase()).not.toContain(term);
      expect(new URL(href).search).toBe("");
      expect(new URL(href).hash).toBe("");
    }
    expect(JSON.stringify(window.history.state ?? null)).not.toContain(term);
    for (const call of [...pushState.mock.calls, ...replaceState.mock.calls]) {
      expect(JSON.stringify(call).toLowerCase()).not.toContain(term);
    }
  });

  it("a late answer for an older term never replaces the answer for the newer one", async () => {
    const older = deferred<ListReply>();
    const { lists } = stubListApi({
      "": noCustomers,
      ko: () => older.promise,
      kowal: listOf("Kowal Agro"),
    });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.type(searchBox(), "ko{Enter}");
    await user.type(searchBox(), "wal{Enter}");
    expect(await screen.findByRole("link", { name: "Kowal Agro" })).toBeVisible();

    older.resolve(listOf("Kostrzewa Farma"));
    await settle();

    expect(screen.getByRole("link", { name: "Kowal Agro" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Kostrzewa Farma" })).not.toBeInTheDocument();
    expect(searches(lists).map((url) => url.searchParams.get("q"))).toEqual(["ko", "kowal"]);
  });

  it("contrast: the same late answer is shown when no newer term was sent", async () => {
    const older = deferred<ListReply>();
    stubListApi({ "": noCustomers, ko: () => older.promise });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.type(searchBox(), "ko{Enter}");
    older.resolve(listOf("Kostrzewa Farma"));
    await settle();

    expect(screen.getByRole("link", { name: "Kostrzewa Farma" })).toBeVisible();
  });

  it("a term written as markup renders as text, in the field and in an answer naming it", async () => {
    const term = "<img src=x onerror=alert(1)>";
    stubListApi({ "": noCustomers, [term]: listOf(term) });
    const alert = vi.spyOn(window, "alert").mockImplementation(() => undefined);
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.click(searchBox());
    await user.paste(term);
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("link", { name: term })).toBeVisible();
    expect(searchBox()).toHaveValue(term);
    expect(screen.getByRole("main").querySelector("img")).toBeNull();
    expect(alert).not.toHaveBeenCalled();
  });

  it("no session is shown an owner selector, and the screen never sends an owner", async () => {
    // This session read carries no `roles`, as from a backend before EKO-3-08, which the SPA reads
    // as no roles (EKO-3-08 K-07 edge); a session holding `manager` is shown the selector instead
    // (OwnerSelector.test.tsx).
    window.history.replaceState(null, "", "/klienci");
    const { lists } = stubListApi(
      { "": listOf("Kowal Agro"), kowal: listOf("Kowal Agro") },
      { subject: "synthetic-subject-0001", name: "Anna Testowa" },
    );
    document.body.innerHTML = '<div id="root"></div>';
    let unmount: (() => void) | undefined;
    act(() => {
      unmount = mount(document);
    });
    try {
      const user = userEvent.setup({ delay: null });
      await screen.findByRole("link", { name: "Kowal Agro" });
      await user.type(searchBox(), "kowal{Enter}");
      await waitFor(() => {
        expect(searches(lists)).toHaveLength(1);
      });

      const main = screen.getByRole("main");
      expect(within(main).queryAllByRole("combobox")).toEqual([]);
      expect(within(main).queryAllByRole("listbox")).toEqual([]);
      expect(within(main).queryAllByRole("radiogroup")).toEqual([]);
      expect(within(main).queryByText(/opiekun|handlowc|właściciel/i)).not.toBeInTheDocument();
      expect(within(main).queryByLabelText(/opiekun|handlowc|właściciel|owner/i)).toBeNull();
      expect(within(main).getAllByRole("searchbox")).toHaveLength(1);
      expectNoOwner(lists);
    } finally {
      act(() => unmount?.());
      document.body.innerHTML = "";
    }
  });
});

describe("K-07 edges", () => {
  it("a second Enter on the same term sends no second request", async () => {
    const { lists } = stubListApi({ "": noCustomers, kowal: listOf("Kowal Agro") });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.type(searchBox(), "kowal{Enter}{Enter}");
    await screen.findByRole("link", { name: "Kowal Agro" });
    await settle();

    expect(searches(lists)).toHaveLength(1);
  });

  it("a failed search shows the list alert, and its retry sends the same term again", async () => {
    let attempt = 0;
    const { lists } = stubListApi({
      "": noCustomers,
      kowal: () => {
        attempt += 1;
        return Promise.resolve(
          attempt === 1
            ? { status: 500, body: { detail: "synthetic failure" } }
            : listOf("Kowal Agro"),
        );
      },
    });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.type(searchBox(), "kowal{Enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Nie udało się wczytać listy klientów.");

    await user.click(within(alert).getByRole("button", { name: "Spróbuj ponownie" }));

    expect(await screen.findByRole("link", { name: "Kowal Agro" })).toBeVisible();
    expect(searches(lists).map((url) => url.searchParams.get("q"))).toEqual(["kowal", "kowal"]);
  });

  it("A-05: a whitespace-only term is the unfiltered list and sends no query", async () => {
    const { lists } = stubListApi({ "": noCustomers });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.type(searchBox(), "   {Enter}");
    await settle();

    expect(searches(lists)).toEqual([]);
    expect(screen.getByText("Nie masz jeszcze klientów")).toBeVisible();
  });

  it("A-06: a rejected term is named at the search field, not as a failed list", async () => {
    stubListApi({
      "": noCustomers,
      kowal: {
        status: 422,
        body: { detail: [{ type: "value_error", loc: ["query", "q"], msg: "synthetic" }] },
      },
    });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.type(searchBox(), "kowal{Enter}");

    expect(await screen.findByText("Wpisz krótszą frazę, najwyżej 254 znaki.")).toBeVisible();
    expect(searchBox()).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByText("Nie udało się wczytać listy klientów.")).not.toBeInTheDocument();
    expect(screen.queryByText("synthetic")).not.toBeInTheDocument();
  });

  it("A-06: the field takes at most 254 characters, so a pasted longer term is cut before it is sent", async () => {
    const long = "a".repeat(300);
    const { lists } = stubListApi({ "": noCustomers, ["a".repeat(254)]: noCustomers });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByText("Nie masz jeszcze klientów");

    await user.click(searchBox());
    await user.paste(long);
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Nie znaleziono klientów")).toBeVisible();
    expect(searches(lists).map((url) => url.searchParams.get("q")?.length)).toEqual([254]);
  });
});
