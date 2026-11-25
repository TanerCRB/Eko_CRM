import { redirectToLogin } from "./navigation";

export type ApiResponse =
  | { kind: "ok"; status: number; body: unknown }
  | { kind: "unauthenticated" }
  | { kind: "unavailable" }
  // `body` only on 422, whose answer names fields, and on 409, whose `detail` names the conflict;
  // no other refusal's body is read.
  | { kind: "failed"; status: number; body?: unknown };

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT";
  // Sent as JSON; absent means no body and no Content-Type.
  body?: unknown;
  // "report" leaves a 401 to the caller; every other request starts a login on 401.
  onUnauthenticated?: "redirect" | "report";
}

// The one way the SPA talks to the API: the browser sends the HttpOnly session cookie itself.
export async function apiRequest(
  path: `/api/${string}`,
  { method = "GET", body: payload, onUnauthenticated = "redirect" }: RequestOptions = {},
): Promise<ApiResponse> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const init: RequestInit = { method, credentials: "same-origin", headers };
  if (payload !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(payload);
  }
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    return { kind: "unavailable" };
  }
  // Read every body to the end, even when only the status matters: Chromium never finishes a
  // fetch whose body is left unread, so the page would never settle.
  let text: string | undefined;
  try {
    text = await response.text();
  } catch {
    text = undefined;
  }
  if (response.status === 401) {
    if (onUnauthenticated === "redirect") {
      redirectToLogin();
    }
    return { kind: "unauthenticated" };
  }
  if (response.status === 503) {
    return { kind: "unavailable" };
  }
  if (response.status === 422 || response.status === 409) {
    return { kind: "failed", status: response.status, body: parseJson(text) };
  }
  if (!response.ok) {
    return { kind: "failed", status: response.status };
  }
  return { kind: "ok", status: response.status, body: parseJson(text) };
}

function parseJson(text: string | undefined): unknown {
  if (text === undefined) {
    return undefined;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}
