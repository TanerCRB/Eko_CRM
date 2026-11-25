import { vi } from "vitest";
import type { Problem } from "../../src/api/auth";
import type {
  CustomerList,
  CustomerRecord,
  CustomerSummary,
  NipTakenProblem,
  ValidationProblem,
} from "../../src/api/customers";
import type { VoivodeshipList } from "../../src/api/reference";

// Answers of a backend from before EKO-3-05, which sends no `archived` (a rolling deployment).
export type OlderCustomerRecord = Omit<CustomerRecord, "archived">;
export interface OlderCustomerList {
  items: Omit<CustomerSummary, "archived">[];
}

// Bodies are typed by the contracts layer, so a contract change breaks the stubs at compile time.
export type CustomerReply =
  | { status: 200 | 201; body: CustomerRecord }
  | { status: 200; body: CustomerList }
  // Named apart from `body`, so a current-contract stub cannot silently lose `archived`.
  | { status: 200; older: OlderCustomerRecord | OlderCustomerList }
  | { status: 200; body: VoivodeshipList }
  | { status: 422; body: ValidationProblem }
  | { status: 403 | 404 | 409 | 500 | 503; body: Problem }
  | { status: 409; body: NipTakenProblem }
  // A body outside the contract, written as text so no contracts-layer type vouches for it.
  | { status: 200 | 409; raw: string };

export interface RecordedCall {
  method: string;
  url: string;
  body: unknown;
}

// One reply source per "METHOD url"; a function reply can hold the answer back (double click).
export type ReplySource = CustomerReply | (() => Promise<CustomerReply>);

export const CUSTOMERS_URL = "/api/customers";
export const VOIVODESHIPS_URL = "/api/reference/voivodeships";

export function stubCustomerApi(routes: Record<string, ReplySource>) {
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
    const text =
      "raw" in reply
        ? reply.raw
        : JSON.stringify("older" in reply ? reply.older : reply.body);
    return new Response(text, {
      status: reply.status,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

// Serves the replies in order, one per request; a request past the last one fails the test.
export function inOrder(...replies: CustomerReply[]): () => Promise<CustomerReply> {
  const queue = [...replies];
  return () => {
    const reply = queue.shift();
    return reply === undefined
      ? Promise.reject(new Error("more requests than replies"))
      : Promise.resolve(reply);
  };
}

export function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}
