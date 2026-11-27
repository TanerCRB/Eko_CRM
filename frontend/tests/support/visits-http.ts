import { vi } from "vitest";
import type { Problem } from "../../src/api/auth";
import type { CustomerList, ValidationProblem } from "../../src/api/customers";
import type { Visit, VisitCustomer, VisitList } from "../../src/api/visits";

// Bodies are typed by the contracts layer, so a contract change breaks the stubs at compile time.
export type VisitReply =
  | { status: 200; body: VisitList }
  | { status: 201; body: Visit }
  | { status: 200; body: CustomerList }
  | { status: 422; body: ValidationProblem }
  | { status: 401 | 403 | 404 | 409 | 500 | 503; body: Problem }
  // A body outside the contract, written as text so no contracts-layer type vouches for it.
  | { status: 200 | 201; raw: string };

export interface RecordedCall {
  method: string;
  url: string;
  body: unknown;
}

// One reply source per "METHOD url" (query string included); a function can hold the answer back.
export type ReplySource = VisitReply | (() => Promise<VisitReply>);

export const VISITS_URL = "/api/visits";
export const CUSTOMERS_URL = "/api/customers";

export function periodUrl(first: string, last: string): string {
  return `/api/visits/period?first=${first}&last=${last}`;
}

export function stubVisitApi(routes: Record<string, ReplySource>) {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? "GET";
    const sent = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ method, url, body: sent });
    const source = routes[`${method} ${url}`];
    if (source === undefined) {
      throw new Error(`Unexpected request ${method} ${url}`);
    }
    const reply = typeof source === "function" ? await source() : source;
    const text = "raw" in reply ? reply.raw : JSON.stringify(reply.body);
    return new Response(text, {
      status: reply.status,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

// Synthetic values only (ADR-0005).
export const FARM: VisitCustomer = {
  id: "4d0e1b2a-3c4d-4e5f-8a6b-7c8d9e0f1a2b",
  name: "Gospodarstwo Pod Lipą",
  street: "Polna 7",
  postal_code: "00-950",
  town: "Kłodawa",
  voivodeship: null,
  county: null,
};

export const ORCHARD: VisitCustomer = {
  id: "5e1f2c3b-4d5e-4f6a-9b7c-8d9e0f1a2b3c",
  name: "Sad Zielony Jar",
  street: null,
  postal_code: null,
  town: "Grójec",
  voivodeship: null,
  county: null,
};

let sequence = 0;

export function visit(
  starts_at: string,
  ends_at: string,
  state: Visit["state"],
  customer: VisitCustomer = FARM,
  own_address: string | null = null,
): Visit {
  sequence += 1;
  const id = `0a1b2c3d-0000-4000-8000-${String(sequence).padStart(12, "0")}`;
  return { id, customer, starts_at, ends_at, own_address, state };
}

export function listed(...items: Visit[]): VisitReply {
  return { status: 200, body: { items } };
}
