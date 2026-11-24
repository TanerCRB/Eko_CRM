import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Problem, SessionInfo } from "../../../src/api/auth";
import type { CustomerList } from "../../../src/api/customers";
import { pageNavigation } from "../../../src/api/navigation";
import type { RepEntry, RepList } from "../../../src/api/reps";
import { mount } from "../../../src/mount";
import { CUSTOMERS_URL, deferred } from "../../support/customers-http";
import { type OlderSessionInfo, SESSION_URL } from "../../support/http";

// EKO-3-08 K-07: the manager's owner selector on the Customers screen. Its visibility is a
// convenience; the server's K-03 refusal and EKO-3-04 scope are the boundary. Staff and customer
// names are invented (ADR-0005).

const REPS_URL = "/api/reps";

type ListReply = { status: 200; body: CustomerList } | { status: 500; body: Problem };
type ListSource = ListReply | (() => Promise<ListReply>);
type RepsReply =
  | { status: 200; body: RepList }
  | { status: 403 | 500; body: Problem }
  | { status: 200; raw: string };

// Lists are routed by the decoded `q` and `owner` they carry ("" for one not carried), written
// "q|owner", so a test states what it expects without depending on how the SPA encodes it.
function stubScreenApi(
  session: SessionInfo | OlderSessionInfo,
  reps: RepsReply | (() => Promise<RepsReply>),
  byQuery: Record<string, ListSource>,
) {
  const lists: URL[] = [];
  const repsReads: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const url = new URL(href, "http://spa.test");
      const method = init?.method ?? "GET";
      if (method !== "GET") {
        throw new Error(`Unexpected request ${method} ${href}`);
      }
      let reply: ListReply | RepsReply;
      if (url.pathname === SESSION_URL) {
        return new Response(JSON.stringify(session), { status: 200 });
      } else if (url.pathname === REPS_URL) {
        repsReads.push(href);
        reply = typeof reps === "function" ? await reps() : reps;
      } else if (url.pathname === CUSTOMERS_URL) {
        lists.push(url);
        const key = `${url.searchParams.get("q") ?? ""}|${url.searchParams.get("owner") ?? ""}`;
        const source = byQuery[key];
        if (source === undefined) {
          throw new Error(`Unexpected list request ${href}`);
        }
        reply = typeof source === "function" ? await source() : source;
      } else {
        throw new Error(`Unexpected request ${href}`);
      }
      const text = "raw" in reply ? reply.raw : JSON.stringify(reply.body);
      return new Response(text, {
        status: reply.status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return { lists, repsReads };
}

const ID_A = "0b1c2d3e-0000-4000-8000-000000000001";
const ID_B = "0b1c2d3e-0000-4000-8000-000000000002";

function listOf(...names: string[]): ListReply {
  const ids = [ID_A, ID_B];
  return {
    status: 200,
    body: { items: names.map((name, index) => ({ id: ids[index] ?? ID_B, name, country: "PL" })) },
  };
}

const noCustomers: ListReply = { status: 200, body: { items: [] } };

function repsOf(...entries: RepEntry[]): RepsReply {
  return { status: 200, body: { items: entries } };
}

const ANNA: RepEntry = { subject: "synthetic-rep-0001", name: "Anna Testowa" };
const BOGDAN: RepEntry = { subject: "synthetic-rep-0002", name: "Bogdan Przykładowy" };

function session(roles: SessionInfo["roles"]): SessionInfo {
  return { subject: "synthetic-staff-0009", name: "Maria Kierownik", roles };
}

let unmount: (() => void) | undefined;

function mountScreen() {
  document.body.innerHTML = '<div id="root"></div>';
  act(() => {
    unmount = mount(document);
  });
}

function ownerSelect() {
  return screen.findByRole("combobox", { name: "Opiekun klienta" });
}

function optionTexts(select: HTMLElement) {
  return within(select)
    .getAllByRole("option")
    .map((option) => option.textContent);
}

function searchBox() {
  return screen.getByRole("searchbox", { name: "Szukaj klientów" });
}

// StrictMode (mount.tsx) runs each effect twice in development, so the unfiltered first list and
// the reps read may be sent twice; requests are counted by what they carry, not in total.
function filtered(lists: readonly URL[]) {
  return lists.filter((url) => url.search !== "");
}

function owners(lists: readonly URL[]) {
  return lists.map((url) => url.searchParams.getAll("owner"));
}

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
  act(() => unmount?.());
  unmount = undefined;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("EKO-3-08 K-07: the owner selector is shown to a manager and sends `owner`", () => {
  it("a manager sees 'Opiekun klienta' holding 'Wszyscy handlowcy' and every rep", async () => {
    const { repsReads } = stubScreenApi(session(["manager"]), repsOf(BOGDAN, ANNA), {
      "|": listOf("Kowal Agro"),
    });
    mountScreen();

    const select = await ownerSelect();

    expect(optionTexts(select)).toEqual([
      "Wszyscy handlowcy",
      "Anna Testowa",
      "Bogdan Przykładowy",
    ]);
    expect(select).toHaveDisplayValue("Wszyscy handlowcy");
    expect(repsReads.length).toBeGreaterThan(0);
    expect(new Set(repsReads)).toEqual(new Set([REPS_URL]));
  });

  it("choosing a rep sends one list request with that rep's subject as `owner`; 'all' sends none", async () => {
    const { lists } = stubScreenApi(session(["rep", "manager"]), repsOf(ANNA, BOGDAN), {
      "|": listOf("Kowal Agro", "Nowak Farma"),
      [`|${BOGDAN.subject}`]: listOf("Nowak Farma"),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    const select = await ownerSelect();
    await settle();
    const before = lists.length;

    await user.selectOptions(select, "Bogdan Przykładowy");

    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Kowal Agro" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Nowak Farma" })).toBeVisible();
    expect(lists).toHaveLength(before + 1);
    expect(owners(lists.slice(before))).toEqual([[BOGDAN.subject]]);
    expect([...(lists.at(-1)?.searchParams.keys() ?? [])]).toEqual(["owner"]);

    await user.selectOptions(select, "Wszyscy handlowcy");

    expect(await screen.findByRole("link", { name: "Kowal Agro" })).toBeVisible();
    expect(lists).toHaveLength(before + 2);
    expect(lists.at(-1)?.search).toBe("");
  });

  it("with a search term both `q` and `owner` are sent, and an empty answer shows the no-match state", async () => {
    const { lists } = stubScreenApi(session(["manager"]), repsOf(ANNA, BOGDAN), {
      "|": listOf("Kowal Agro"),
      "kowal|": listOf("Kowal Agro"),
      [`kowal|${ANNA.subject}`]: noCustomers,
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.type(searchBox(), "kowal{Enter}");
    await waitFor(() => {
      expect(filtered(lists)).toHaveLength(1);
    });

    await user.selectOptions(await ownerSelect(), "Anna Testowa");

    expect(await screen.findByRole("heading", { name: "Nie znaleziono klientów" })).toBeVisible();
    const last = lists.at(-1);
    expect(last?.searchParams.getAll("q")).toEqual(["kowal"]);
    expect(last?.searchParams.getAll("owner")).toEqual([ANNA.subject]);
  });

  it("G-7 A: an empty answer to an owner alone shows 'Nie znaleziono klientów', not the no-customers state", async () => {
    stubScreenApi(session(["manager"]), repsOf(ANNA), {
      "|": listOf("Kowal Agro"),
      [`|${ANNA.subject}`]: noCustomers,
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    await user.selectOptions(await ownerSelect(), "Anna Testowa");

    expect(await screen.findByRole("heading", { name: "Nie znaleziono klientów" })).toBeVisible();
    expect(screen.queryByText("Nie masz jeszcze klientów")).not.toBeInTheDocument();
  });

  it("a term typed after an owner is chosen keeps the owner", async () => {
    const { lists } = stubScreenApi(session(["manager"]), repsOf(ANNA), {
      "|": noCustomers,
      [`|${ANNA.subject}`]: noCustomers,
      [`kowal|${ANNA.subject}`]: listOf("Kowal Agro"),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await user.selectOptions(await ownerSelect(), "Anna Testowa");

    await user.type(searchBox(), "kowal{Enter}");

    expect(await screen.findByRole("link", { name: "Kowal Agro" })).toBeVisible();
    expect(lists.at(-1)?.searchParams.getAll("owner")).toEqual([ANNA.subject]);
    expect(lists.at(-1)?.searchParams.getAll("q")).toEqual(["kowal"]);
  });
});

describe("EKO-3-08 K-07 contrast: no selector without `manager`", () => {
  it.each([
    ["rep", ["rep"]],
    ["administrator", ["administrator"]],
    ["no roles", []],
  ] as const)(
    "a %s session sees no selector, makes no reps request and never sends `owner`",
    async (_label, roles) => {
      const { lists, repsReads } = stubScreenApi(session([...roles]), repsOf(ANNA, BOGDAN), {
        "|": listOf("Kowal Agro"),
        "kowal|": listOf("Kowal Agro"),
      });
      const user = userEvent.setup({ delay: null });
      mountScreen();
      await screen.findByRole("link", { name: "Kowal Agro" });
      await user.type(searchBox(), "kowal{Enter}");
      await waitFor(() => {
        expect(filtered(lists)).toHaveLength(1);
      });
      await settle();

      const main = screen.getByRole("main");
      expect(within(main).queryAllByRole("combobox")).toEqual([]);
      expect(within(main).queryByText(/opiekun|handlowc/i)).not.toBeInTheDocument();
      expect(repsReads).toEqual([]);
      expect(owners(lists).flat()).toEqual([]);
    },
  );

  it("edge: a session answer without `roles` (older backend) sees no selector and no reps request", async () => {
    const { repsReads } = stubScreenApi(
      { subject: "synthetic-staff-0009", name: "Maria Kierownik" },
      repsOf(ANNA),
      { "|": listOf("Kowal Agro") },
    );
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await settle();

    expect(screen.queryByRole("combobox", { name: "Opiekun klienta" })).not.toBeInTheDocument();
    expect(repsReads).toEqual([]);
  });
});

describe("EKO-3-08 K-07 edges", () => {
  it("A-17: an empty reps list still shows the selector, holding only 'Wszyscy handlowcy'", async () => {
    stubScreenApi(session(["manager"]), repsOf(), { "|": noCustomers });
    mountScreen();

    expect(optionTexts(await ownerSelect())).toEqual(["Wszyscy handlowcy"]);
  });

  it("one rep gives one option besides 'Wszyscy handlowcy'", async () => {
    stubScreenApi(session(["manager"]), repsOf(ANNA), { "|": noCustomers });
    mountScreen();

    expect(optionTexts(await ownerSelect())).toEqual(["Wszyscy handlowcy", "Anna Testowa"]);
  });

  it("G-6 A: options by display name in Polish order, ties by subject, unnamed last", async () => {
    stubScreenApi(
      session(["manager"]),
      repsOf(
        { subject: "s-07", name: null },
        { subject: "s-01", name: "Marek Testowy" },
        { subject: "s-06", name: "   " },
        { subject: "s-02", name: "Łukasz Testowy" },
        { subject: "s-05", name: "Adam Testowy" },
        { subject: "s-03", name: "Żaneta Testowa" },
        { subject: "s-04", name: "Adam Testowy" },
        { subject: "s-08", name: "Zenon Testowy" },
      ),
      { "|": noCustomers },
    );
    const user = userEvent.setup({ delay: null });
    mountScreen();
    const select = await ownerSelect();

    expect(optionTexts(select)).toEqual([
      "Wszyscy handlowcy",
      "Adam Testowy",
      "Adam Testowy",
      "Łukasz Testowy",
      "Marek Testowy",
      "Zenon Testowy",
      "Żaneta Testowa",
      "Zalogowany użytkownik",
      "Zalogowany użytkownik",
    ]);
    const values = within(select)
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);
    expect(values).toEqual(["", "s-04", "s-05", "s-02", "s-01", "s-08", "s-03", "s-06", "s-07"]);
    await user.selectOptions(select, "s-06");
    expect(select).toHaveValue("s-06");
  });

  it("a rep with a null or blank name shows the unnamed text, and choosing it sends its subject", async () => {
    const { lists } = stubScreenApi(
      session(["manager"]),
      repsOf({ subject: "synthetic-rep-0003", name: null }),
      { "|": noCustomers, "|synthetic-rep-0003": noCustomers },
    );
    const user = userEvent.setup({ delay: null });
    mountScreen();
    const select = await ownerSelect();
    expect(optionTexts(select)).toEqual(["Wszyscy handlowcy", "Zalogowany użytkownik"]);

    await user.selectOptions(select, "Zalogowany użytkownik");

    await waitFor(() => {
      expect(owners(lists).at(-1)).toEqual(["synthetic-rep-0003"]);
    });
  });

  it("markup in a name renders as text, and diacritics show as stored", async () => {
    const markup = "<img src=x onerror=alert(1)>";
    stubScreenApi(
      session(["manager"]),
      repsOf(
        { subject: "synthetic-rep-0004", name: markup },
        { subject: "synthetic-rep-0005", name: "Zażółć Gęślą-Jaźń" },
      ),
      { "|": noCustomers },
    );
    const alert = vi.spyOn(window, "alert").mockImplementation(() => undefined);
    mountScreen();
    const select = await ownerSelect();

    expect(optionTexts(select)).toEqual(["Wszyscy handlowcy", markup, "Zażółć Gęślą-Jaźń"]);
    expect(screen.getByRole("main").querySelector("img")).toBeNull();
    expect(alert).not.toHaveBeenCalled();
  });

  it("a subject holding +&=%# arrives byte-equal in `owner`", async () => {
    const subject = "rep+1&x=y%20#z";
    const { lists } = stubScreenApi(session(["manager"]), repsOf({ subject, name: "Anna Testowa" }), {
      "|": noCustomers,
      [`|${subject}`]: noCustomers,
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();

    await user.selectOptions(await ownerSelect(), "Anna Testowa");

    await waitFor(() => {
      expect(owners(lists).at(-1)).toEqual([subject]);
    });
  });

  it("a late answer for an earlier owner never replaces the answer for the later one", async () => {
    const earlier = deferred<ListReply>();
    const { lists } = stubScreenApi(session(["manager"]), repsOf(ANNA, BOGDAN), {
      "|": noCustomers,
      [`|${ANNA.subject}`]: () => earlier.promise,
      [`|${BOGDAN.subject}`]: listOf("Nowak Farma"),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    const select = await ownerSelect();

    await user.selectOptions(select, "Anna Testowa");
    await user.selectOptions(select, "Bogdan Przykładowy");
    expect(await screen.findByRole("link", { name: "Nowak Farma" })).toBeVisible();

    earlier.resolve(listOf("Kowal Agro"));
    await settle();

    expect(screen.getByRole("link", { name: "Nowak Farma" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Kowal Agro" })).not.toBeInTheDocument();
    expect(owners(filtered(lists))).toEqual([[ANNA.subject], [BOGDAN.subject]]);
  });

  it("contrast: the same late answer is shown when no later owner was chosen", async () => {
    const earlier = deferred<ListReply>();
    stubScreenApi(session(["manager"]), repsOf(ANNA, BOGDAN), {
      "|": noCustomers,
      [`|${ANNA.subject}`]: () => earlier.promise,
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();

    await user.selectOptions(await ownerSelect(), "Anna Testowa");
    earlier.resolve(listOf("Kowal Agro"));
    await settle();

    expect(screen.getByRole("link", { name: "Kowal Agro" })).toBeVisible();
  });

  it("the chosen owner never enters the location or the history", async () => {
    stubScreenApi(session(["manager"]), repsOf(ANNA), {
      "|": noCustomers,
      [`|${ANNA.subject}`]: listOf("Kowal Agro"),
    });
    const pushState = vi.spyOn(window.history, "pushState");
    const replaceState = vi.spyOn(window.history, "replaceState");
    const user = userEvent.setup({ delay: null });
    mountScreen();

    await user.selectOptions(await ownerSelect(), "Anna Testowa");
    await screen.findByRole("link", { name: "Kowal Agro" });

    const href = window.location.href;
    expect(decodeURIComponent(href)).not.toContain(ANNA.subject);
    expect(new URL(href).search).toBe("");
    expect(new URL(href).hash).toBe("");
    expect(JSON.stringify(window.history.state ?? null)).not.toContain(ANNA.subject);
    for (const call of [...pushState.mock.calls, ...replaceState.mock.calls]) {
      expect(JSON.stringify(call)).not.toContain(ANNA.subject);
    }
  });

  it.each([
    ["a refusal", { status: 403, body: { detail: "not permitted" } }],
    ["a server failure", { status: 500, body: { detail: "synthetic failure" } }],
    ["an unreadable answer", { status: 200, raw: '{"items":"x"}' }],
  ] as const)(
    "G-8 A: when the reps list fails (%s) the list loads unfiltered, with no selector",
    async (_label, reply) => {
      const { lists, repsReads } = stubScreenApi(session(["manager"]), reply, {
        "|": listOf("Kowal Agro"),
      });
      mountScreen();

      expect(await screen.findByRole("link", { name: "Kowal Agro" })).toBeVisible();
      await waitFor(() => {
        expect(repsReads.length).toBeGreaterThan(0);
      });
      await settle();

      expect(screen.queryByRole("combobox", { name: "Opiekun klienta" })).not.toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(filtered(lists)).toEqual([]);
    },
  );

  it("G-8 A contrast: the same manager with a reps list that answers sees the selector", async () => {
    stubScreenApi(session(["manager"]), repsOf(ANNA), { "|": listOf("Kowal Agro") });
    mountScreen();

    expect(await ownerSelect()).toBeVisible();
  });
});
