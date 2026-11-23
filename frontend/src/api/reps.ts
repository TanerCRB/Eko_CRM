import { apiRequest } from "./client";

// Shapes of backend/app/api/reps.py (`rep_list`, RepList, RepEntry), written by hand and checked
// against the OpenAPI document by the EKO-1-35 check (backend/tests/support/frontend_contract.py).
// Manager-only: the server refuses anyone else, so the SPA asks only for a manager's session.

export interface RepEntry {
  subject: string;
  name: string | null;
}

export interface RepList {
  items: RepEntry[];
}

export type RepsResult = { kind: "listed"; reps: RepEntry[] } | { kind: "failed" };

export const REPS_PATH = "/api/reps";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseEntry(value: unknown): RepEntry | null {
  if (!isRecord(value)) {
    return null;
  }
  const { subject, name } = value;
  if (typeof subject !== "string" || subject === "") {
    return null;
  }
  if (name !== null && typeof name !== "string") {
    return null;
  }
  return { subject, name };
}

// A subject named twice is refused too: the subject is the entry's identity, so the selector
// would hold two options for one choice.
function parseRepList(body: unknown): RepEntry[] | null {
  if (!isRecord(body) || !Array.isArray(body["items"])) {
    return null;
  }
  const reps: RepEntry[] = [];
  const seen = new Set<string>();
  for (const value of body["items"]) {
    const entry = parseEntry(value);
    if (entry === null || seen.has(entry.subject)) {
      return null;
    }
    seen.add(entry.subject);
    reps.push(entry);
  }
  return reps;
}

// Any refusal is a failure, a 403 included: a session whose token lost `manager` is refused.
export async function readReps(): Promise<RepsResult> {
  const response = await apiRequest(REPS_PATH);
  if (response.kind !== "ok") {
    return { kind: "failed" };
  }
  const reps = parseRepList(response.body);
  return reps === null ? { kind: "failed" } : { kind: "listed", reps };
}
