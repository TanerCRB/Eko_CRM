import { vi } from "vitest";
import type { LoggedOut, Problem, SessionInfo } from "../../src/api/auth";

// Bodies are typed by the contracts layer, so a contract change breaks the stubs at compile time.
export type Reply =
  | { status: 200; body: SessionInfo | LoggedOut }
  | { status: 401 | 403 | 500 | 503; body: Problem }
  | { status: 200; raw: string }
  | "network-error";

export interface Call {
  url: string;
  init: RequestInit | undefined;
}

export function respond(reply: Reply): Promise<Response> {
  if (reply === "network-error") {
    return Promise.reject(new TypeError("Failed to fetch"));
  }
  const text = "raw" in reply ? reply.raw : JSON.stringify(reply.body);
  return Promise.resolve(
    new Response(text, { status: reply.status, headers: { "content-type": "application/json" } }),
  );
}

// Replies are served in order per URL; the last one repeats.
export function stubFetch(replies: Record<string, readonly Reply[]>) {
  const calls: Call[] = [];
  const served = new Map<string, number>();
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    calls.push({ url, init });
    const queue = replies[url];
    if (queue === undefined || queue.length === 0) {
      return Promise.reject(new Error(`Unexpected request to ${url}`));
    }
    const index = served.get(url) ?? 0;
    served.set(url, index + 1);
    const reply = queue[Math.min(index, queue.length - 1)];
    if (reply === undefined) {
      return Promise.reject(new Error(`No reply for ${url}`));
    }
    return respond(reply);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export const SESSION_URL = "/api/auth/session";
export const LOGOUT_URL = "/api/auth/logout";

export const unauthenticated: Reply = { status: 401, body: { detail: "not authenticated" } };
export const unavailable: Reply = { status: 503, body: { detail: "temporarily unavailable" } };

export function signedIn(name: string | null, subject = "synthetic-subject-0001"): Reply {
  return { status: 200, body: { subject, name } };
}
