import { act, screen, within } from "@testing-library/react";
import { vi } from "vitest";
import type { Problem, SessionInfo } from "../../src/api/auth";
import type { CustomerList, CustomerSummary } from "../../src/api/customers";
import type { RepList } from "../../src/api/reps";
import { mount } from "../../src/mount";
import { CUSTOMERS_URL } from "./customers-http";
import { SESSION_URL } from "./http";

// The Customers screen with its list requests routed by the decoded `q`, `owner` and `state`
// they carry ("" for one not carried), written "q|owner|state" (EKO-3-10). Names are invented.

export const REPS_URL = "/api/reps";
export const ANNA = { subject: "synthetic-rep-0101", name: "Anna Testowa" };

export type ListAnswer =
  | CustomerList
  | { status: 500; body: Problem }
  | { status: 200; raw: string }
  | "network-error";
export type ListSource = ListAnswer | (() => Promise<ListAnswer>);

let lastId = 0;

// Each call gives fresh identifiers, so two lists never share an item by accident.
export function listOf(...items: [string, boolean][]): CustomerList {
  return {
    items: items.map(([name, archived]): CustomerSummary => {
      lastId += 1;
      const suffix = String(lastId).padStart(12, "0");
      return { id: `5e6f7a8b-0000-4000-8000-${suffix}`, name, country: "PL", archived };
    }),
  };
}

export const NOTHING: CustomerList = { items: [] };

export function stubListScreen(roles: SessionInfo["roles"], byQuery: Record<string, ListSource>) {
  const lists: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const url = new URL(href, "http://spa.test");
      const method = init?.method ?? "GET";
      const json = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" },
        });
      if (method === "GET" && url.pathname === SESSION_URL) {
        const session: SessionInfo = { subject: "synthetic-staff-0110", name: "Ewa Przykładowa", roles };
        return json(session);
      }
      if (method === "GET" && url.pathname === REPS_URL) {
        const reps: RepList = { items: [ANNA] };
        return json(reps);
      }
      if (method === "GET" && url.pathname === CUSTOMERS_URL) {
        lists.push(url);
        const key = ["q", "owner", "state"].map((name) => url.searchParams.get(name) ?? "").join("|");
        const source = byQuery[key];
        if (source === undefined) {
          throw new Error(`Unexpected list request ${href}`);
        }
        const answer = typeof source === "function" ? await source() : source;
        if (answer === "network-error") {
          throw new TypeError("Failed to fetch");
        }
        if ("raw" in answer) {
          return new Response(answer.raw, {
            status: answer.status,
            headers: { "content-type": "application/json" },
          });
        }
        return "status" in answer ? json(answer.body, answer.status) : json(answer);
      }
      throw new Error(`Unexpected request ${method} ${href}`);
    }),
  );
  return { lists };
}

let unmount: (() => void) | undefined;

export function mountListScreen() {
  window.history.replaceState(null, "", "/klienci");
  document.body.innerHTML = '<div id="root"></div>';
  act(() => {
    unmount = mount(document);
  });
}

export function unmountListScreen() {
  act(() => unmount?.());
  unmount = undefined;
  document.body.innerHTML = "";
}

export function stateButton(name: "Aktywni" | "Archiwum" | "Wszyscy") {
  return within(screen.getByRole("group", { name: "Status klienta" })).getByRole("button", { name });
}

export function searchBox() {
  return screen.getByRole("searchbox", { name: "Szukaj klientów" });
}

// Lets every answer already released travel through the client and into the screen.
export async function settle() {
  await act(async () => {
    await new Promise((done) => setTimeout(done, 50));
  });
}

export const FIRST_TITLE = "Nie masz jeszcze klientów";
export const FIRST_TEXT = "Dodaj pierwszego klienta, aby zapisać jego dane kontaktowe.";
export const POINTER_TITLE = "Brak aktywnych klientów";
export const POINTER_TEXT =
  "Zarchiwizowanych klientów zobaczysz po wybraniu filtru Archiwum lub Wszyscy.";
export const NO_MATCH_TITLE = "Nie znaleziono klientów";
