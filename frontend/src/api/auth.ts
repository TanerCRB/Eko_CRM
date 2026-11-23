import { apiRequest } from "./client";

// Shapes of backend/app/api/auth.py (SessionInfo, LoggedOut, Problem); unknown extra fields are
// ignored so a backend that adds one does not lock users out during a rolling deployment.

// Not exported: the backend's contract check (EKO-1-35) fails an exported type it does not compare.
type Role = "administrator" | "manager" | "rep";

// `roles` (EKO-3-08) is always present once parsed: a backend from before it sends none, read as
// no roles, so nothing role-dependent is shown. The server still decides every request itself.
export interface SessionInfo {
  subject: string;
  name: string | null;
  roles: Role[];
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
  // Authenticated but holding no application role (ADR-0003 roles addendum, 2026-11-16).
  | { kind: "noRole" }
  | { kind: "unavailable" }
  | { kind: "invalid" };

export type LogoutResult = { kind: "loggedOut" } | { kind: "alreadyLoggedOut" } | { kind: "failed" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const ROLES: readonly Role[] = ["administrator", "manager", "rep"];

function isRole(value: string): value is Role {
  return ROLES.some((role) => role === value);
}

// A role name this SPA does not know is left out, so a backend that adds one locks nobody out.
function parseRoles(value: unknown): Role[] | null {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value) || !value.every((entry) => typeof entry === "string")) {
    return null;
  }
  return value.filter(isRole);
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
  const roles = parseRoles(body["roles"]);
  return roles === null ? null : { subject, name, roles };
}

function isLoggedOut(body: unknown): body is LoggedOut {
  return isRecord(body) && body["status"] === "logged_out";
}

// The caller starts the login on "unauthenticated", so a superseded check cannot start a second one.
export async function readSession(): Promise<SessionRead> {
  const response = await apiRequest("/api/auth/session", { onUnauthenticated: "report" });
  if (response.kind === "failed") {
    // The status alone decides; a 403 body is never read, so it cannot name a subject.
    return response.status === 403 ? { kind: "noRole" } : { kind: "invalid" };
  }
  if (response.kind !== "ok") {
    return { kind: response.kind };
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
