import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionInfo } from "../../../src/api/auth";
import type { CustomerList } from "../../../src/api/customers";
import { pageNavigation } from "../../../src/api/navigation";
import type { RepList } from "../../../src/api/reps";
import { mount } from "../../../src/mount";
import { CUSTOMERS_URL, deferred, type OlderCustomerList } from "../../support/customers-http";
import { SESSION_URL } from "../../support/http";

// EKO-3-05 K-07, the list: the state filter sends `state` beside `q` and `owner`, an answer for
// an earlier state never replaces a newer one, and each item's marker comes from its own
// `archived`, never from the `state` that was asked for. Names are invented (ADR-0005).

const REPS_URL = "/api/reps";
const ID_A = "6a7b8c9d-0000-4000-8000-0000000000a1";
const ID_B = "6a7b8c9d-0000-4000-8000-0000000000b2";
const ID_C = "6a7b8c9d-0000-4000-8000-0000000000c3";
const ANNA = { subject: "synthetic-rep-0001", name: "Anna Testowa" };
const MARKER = "Zarchiwizowany";

type ListBody = CustomerList | OlderCustomerList;
type ListSource = ListBody | (() => Promise<ListBody>);

function session(roles: SessionInfo["roles"]): SessionInfo {
  return { subject: "synthetic-staff-0005", name: "Ewa Przykładowa", roles };
}

// Lists are routed by the decoded `q`, `owner` and `state` they carry ("" for one not carried),
// written "q|owner|state", so a test states what it expects, not how the SPA encodes it.
function stubScreen(roles: SessionInfo["roles"], byQuery: Record<string, ListSource>) {
  const lists: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const url = new URL(href, "http://spa.test");
      const method = init?.method ?? "GET";
      let body: unknown;
      if (method === "GET" && url.pathname === SESSION_URL) {
        body = session(roles);
      } else if (method === "GET" && url.pathname === REPS_URL) {
        const reps: RepList = { items: [ANNA] };
        body = reps;
      } else if (method === "GET" && url.pathname === CUSTOMERS_URL) {
        lists.push(url);
        const key = ["q", "owner", "state"].map((name) => url.searchParams.get(name) ?? "").join("|");
        const source = byQuery[key];
        if (source === undefined) {
          throw new Error(`Unexpected list request ${href}`);
        }
        body = typeof source === "function" ? await source() : source;
      } else {
        throw new Error(`Unexpected request ${method} ${href}`);
      }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return { lists };
}

function listOf(...items: [string, string, boolean | undefined][]): ListBody {
  if (items.every(([, , archived]) => archived !== undefined)) {
    return {
      items: items.map(([id, name, archived]) => ({ id, name, country: "PL", archived: archived === true })),
    };
  }
  const older: OlderCustomerList = { items: items.map(([id, name]) => ({ id, name, country: "PL" })) };
  return older;
}

let unmount: (() => void) | undefined;

function mountScreen() {
  document.body.innerHTML = '<div id="root"></div>';
  act(() => {
    unmount = mount(document);
  });
}

function stateButton(name: "Aktywni" | "Archiwum" | "Wszyscy") {
  return within(screen.getByRole("group", { name: "Status klienta" })).getByRole("button", { name });
}

function states(lists: readonly URL[]) {
  return lists.map((url) => url.searchParams.getAll("state"));
}

function line(name: string): HTMLElement {
  const link = screen.getByRole("link", { name });
  const item = link.closest("li");
  if (item === null) {
    throw new Error(`no list item for ${name}`);
  }
  return item;
}

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.history.replaceState(null, "", "/klienci");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  act(() => unmount?.());
  unmount = undefined;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("K-07 filter: the state control sends `state` and keeps `q` and `owner`", () => {
  it("Archiwum sends state=archived, Wszyscy state=both, and Aktywni state=active", async () => {
    const { lists } = stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      "||archived": listOf([ID_B, "Nowak Farma", true]),
      "||both": listOf([ID_A, "Kowal Agro", false], [ID_B, "Nowak Farma", true]),
      "||active": listOf([ID_A, "Kowal Agro", false]),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    expect(stateButton("Aktywni")).toHaveAttribute("aria-pressed", "true");
    expect(stateButton("Archiwum")).toHaveAttribute("aria-pressed", "false");

    await user.click(stateButton("Archiwum"));
    expect(await screen.findByRole("link", { name: "Nowak Farma" })).toBeVisible();
    expect(states(lists).at(-1)).toEqual(["archived"]);
    expect(stateButton("Archiwum")).toHaveAttribute("aria-pressed", "true");

    await user.click(stateButton("Wszyscy"));
    await waitFor(() => {
      expect(screen.getAllByRole("link", { name: /Kowal Agro|Nowak Farma/ })).toHaveLength(2);
    });
    expect(states(lists).at(-1)).toEqual(["both"]);

    await user.click(stateButton("Aktywni"));
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Nowak Farma" })).not.toBeInTheDocument();
    });
    expect(states(lists).at(-1)).toEqual(["active"]);
    expect(stateButton("Aktywni")).toHaveAttribute("aria-pressed", "true");
  });

  it("D-4 S-F2 A: before any pick the first list request carries no `state`, also with a term", async () => {
    const { lists } = stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      "kowal||": listOf([ID_A, "Kowal Agro", false]),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    const first = lists[0];
    expect(first?.search).toBe("");
    expect(first?.searchParams.has("state")).toBe(false);

    await user.type(screen.getByRole("searchbox", { name: "Szukaj klientów" }), "kowal{Enter}");
    await waitFor(() => {
      expect(lists.at(-1)?.searchParams.get("q")).toBe("kowal");
    });
    expect([...(lists.at(-1)?.searchParams.keys() ?? [])]).toEqual(["q"]);
    for (const url of lists) {
      expect(url.searchParams.has("state")).toBe(false);
    }
  });

  it("D-4 S-F2 A: picking Aktywni after another state sends exactly state=active", async () => {
    const { lists } = stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      "||archived": listOf([ID_B, "Nowak Farma", true]),
      "||active": listOf([ID_C, "Aktywny Wybrany", false]),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.click(stateButton("Archiwum"));
    await screen.findByRole("link", { name: "Nowak Farma" });
    const before = lists.length;

    await user.click(stateButton("Aktywni"));

    expect(await screen.findByRole("link", { name: "Aktywny Wybrany" })).toBeVisible();
    const picked = lists.slice(before);
    expect(picked).toHaveLength(1);
    expect(picked[0]?.searchParams.getAll("state")).toEqual(["active"]);
    expect([...(picked[0]?.searchParams.keys() ?? [])]).toEqual(["state"]);
  });

  it("a search term and an owner are sent alongside `state`, and a new term keeps the state", async () => {
    const { lists } = stubScreen(["manager"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      [`|${ANNA.subject}|`]: listOf([ID_A, "Kowal Agro", false]),
      [`kowal|${ANNA.subject}|`]: listOf([ID_A, "Kowal Agro", false]),
      [`kowal|${ANNA.subject}|archived`]: listOf([ID_B, "Kowalski Sad", true]),
      [`nowak|${ANNA.subject}|archived`]: listOf([ID_C, "Nowak Sad", true]),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Opiekun klienta" }),
      ANNA.name,
    );
    await user.type(screen.getByRole("searchbox", { name: "Szukaj klientów" }), "kowal{Enter}");
    await waitFor(() => {
      expect(lists.at(-1)?.searchParams.get("q")).toBe("kowal");
    });

    await user.click(stateButton("Archiwum"));

    expect(await screen.findByRole("link", { name: "Kowalski Sad" })).toBeVisible();
    const sent = lists.at(-1);
    expect(sent?.searchParams.getAll("q")).toEqual(["kowal"]);
    expect(sent?.searchParams.getAll("owner")).toEqual([ANNA.subject]);
    expect(sent?.searchParams.getAll("state")).toEqual(["archived"]);

    const search = screen.getByRole("searchbox", { name: "Szukaj klientów" });
    await user.clear(search);
    await user.type(search, "nowak{Enter}");

    expect(await screen.findByRole("link", { name: "Nowak Sad" })).toBeVisible();
    expect(lists.at(-1)?.searchParams.getAll("state")).toEqual(["archived"]);
    expect(lists.at(-1)?.searchParams.getAll("owner")).toEqual([ANNA.subject]);
  });

  it("edge: a late answer for an earlier `state` never replaces the newer one", async () => {
    const heldArchived = deferred<ListBody>();
    stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      "||archived": () => heldArchived.promise,
      "||both": listOf([ID_A, "Kowal Agro", false], [ID_C, "Wszyscy Razem", false]),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    await user.click(stateButton("Archiwum"));
    await user.click(stateButton("Wszyscy"));
    expect(await screen.findByRole("link", { name: "Wszyscy Razem" })).toBeVisible();
    await act(async () => {
      heldArchived.resolve(listOf([ID_B, "Spóźniony Archiwalny", true]));
      await new Promise((done) => setTimeout(done, 50));
    });

    expect(screen.queryByRole("link", { name: "Spóźniony Archiwalny" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Wszyscy Razem" })).toBeVisible();
    expect(stateButton("Wszyscy")).toHaveAttribute("aria-pressed", "true");
  });

  it("edge: an empty archived list says nothing matches and points at the state filter", async () => {
    stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      "||archived": { items: [] },
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    await user.click(stateButton("Archiwum"));

    expect(await screen.findByRole("heading", { name: "Nie znaleziono klientów" })).toBeVisible();
    expect(screen.getByText("Zmień filtr statusu lub wyszukiwanie.")).toBeVisible();
    expect(screen.queryByText("Nie masz jeszcze klientów")).not.toBeInTheDocument();
  });
});

describe("K-07 markers: each item's state comes from its own `archived`", () => {
  it("an item with archived: true is marked, the same item with archived: false is not", async () => {
    stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", true], [ID_B, "Nowak Farma", false]),
    });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    expect(within(line("Kowal Agro")).getByText(MARKER)).toBeVisible();
    expect(within(line("Nowak Farma")).queryByText(MARKER)).not.toBeInTheDocument();
  });

  it("contrast: under state=archived an item answered archived: false shows no marker (M-x2)", async () => {
    stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      "||archived": listOf([ID_B, "Nowak Farma", false], [ID_C, "Sad Zamknięty", true]),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    await user.click(stateButton("Archiwum"));

    await screen.findByRole("link", { name: "Nowak Farma" });
    expect(within(line("Nowak Farma")).queryByText(MARKER)).not.toBeInTheDocument();
    expect(within(line("Sad Zamknięty")).getByText(MARKER)).toBeVisible();
  });

  it("edge: an answer without `archived`, from an older backend, is not shown as archived", async () => {
    const user = userEvent.setup({ delay: null });
    stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", undefined]),
      "||archived": listOf([ID_B, "Nowak Farma", undefined]),
    });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    expect(within(line("Kowal Agro")).queryByText(MARKER)).not.toBeInTheDocument();

    await user.click(stateButton("Archiwum"));

    await screen.findByRole("link", { name: "Nowak Farma" });
    expect(within(line("Nowak Farma")).queryByText(MARKER)).not.toBeInTheDocument();
  });

  it("edge: markup in an archived item's name renders as text", async () => {
    stubScreen(["rep"], { "||": listOf([ID_A, "<b>Żółw</b>", true]) });
    mountScreen();

    expect(await screen.findByRole("link", { name: "<b>Żółw</b>" })).toBeVisible();
    expect(screen.getByRole("main").querySelector("b")).toBeNull();
  });
});

describe("K-07 storage: no field value and no `state` enters the location or browser storage", () => {
  it("picking states and searching leaves the location bare and browser storage empty", async () => {
    const seen: string[] = [];
    stubScreen(["rep"], {
      "||": listOf([ID_A, "Kowal Agro", false]),
      "||archived": listOf([ID_B, "Nowak Farma", true]),
      "nowak||archived": listOf([ID_B, "Nowak Farma", true]),
      "nowak||both": listOf([ID_B, "Nowak Farma", true]),
    });
    const user = userEvent.setup({ delay: null });
    mountScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    seen.push(window.location.href);

    await user.click(stateButton("Archiwum"));
    await screen.findByRole("link", { name: "Nowak Farma" });
    seen.push(window.location.href);
    await user.type(screen.getByRole("searchbox", { name: "Szukaj klientów" }), "nowak{Enter}");
    await user.click(stateButton("Wszyscy"));
    await waitFor(() => {
      expect(stateButton("Wszyscy")).toHaveAttribute("aria-pressed", "true");
    });
    seen.push(window.location.href);

    for (const href of seen) {
      const decoded = decodeURIComponent(href);
      for (const value of ["archived", "both", "active", "nowak", "Nowak Farma", "state"]) {
        expect(decoded).not.toContain(value);
      }
      expect(new URL(href).search).toBe("");
      expect(new URL(href).hash).toBe("");
    }
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
  });
});
