import { redirectToLogin } from "./navigation";

export type ApiResponse =
  | { kind: "ok"; status: number; body: unknown }
  | { kind: "unauthenticated" }
  | { kind: "unavailable" }
  | { kind: "failed"; status: number };

export interface RequestOptions {
  method?: "GET" | "POST";
  // "report" leaves a 401 to the caller; every other request starts a login on 401.
  onUnauthenticated?: "redirect" | "report";
}

// The one way the SPA talks to the API: the browser sends the HttpOnly session cookie itself.
export async function apiRequest(
  path: `/api/${string}`,
  { method = "GET", onUnauthenticated = "redirect" }: RequestOptions = {},
): Promise<ApiResponse> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    return { kind: "unavailable" };
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
  if (!response.ok) {
    return { kind: "failed", status: response.status };
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  return { kind: "ok", status: response.status, body };
}
