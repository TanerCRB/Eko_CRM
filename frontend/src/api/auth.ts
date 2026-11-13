import { apiRequest } from "./client";

// Shapes of backend/app/api/auth.py (SessionInfo, LoggedOut, Problem); unknown extra fields are
// ignored so a backend that adds one does not lock users out during a rolling deployment.
export interface SessionInfo {
  subject: string;
  name: string | null;
}

export interface LoggedOut {
  status: "logged_out";
}

export interface Problem {
  detail: string;
}

export type SessionRead =
  | { kind: "authenticated"; session: SessionInfo }
  | { kind: "unauthenticated" }
  | { kind: "unavailable" }
  | { kind: "invalid" };

export type LogoutResult = { kind: "loggedOut" } | { kind: "alreadyLoggedOut" } | { kind: "failed" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseSessionInfo(body: unknown): SessionInfo | null {
  if (!isRecord(body)) {
    return null;
  }
  const { subject, name } = body;
  if (typeof subject !== "string" || subject === "") {
    return null;
  }
  if (name !== null && typeof name !== "string") {
    return null;
  }
  return { subject, name };
}

function isLoggedOut(body: unknown): body is LoggedOut {
  return isRecord(body) && body["status"] === "logged_out";
}

// The caller starts the login on "unauthenticated", so a superseded check cannot start a second one.
export async function readSession(): Promise<SessionRead> {
  const response = await apiRequest("/api/auth/session", { onUnauthenticated: "report" });
  if (response.kind !== "ok") {
    return response.kind === "failed" ? { kind: "invalid" } : { kind: response.kind };
  }
  const session = parseSessionInfo(response.body);
  return session === null ? { kind: "invalid" } : { kind: "authenticated", session };
}

export async function logout(): Promise<LogoutResult> {
  const response = await apiRequest("/api/auth/logout", {
    method: "POST",
    onUnauthenticated: "report",
  });
  if (response.kind === "unauthenticated") {
    return { kind: "alreadyLoggedOut" };
  }
  return response.kind === "ok" && isLoggedOut(response.body)
    ? { kind: "loggedOut" }
    : { kind: "failed" };
}
