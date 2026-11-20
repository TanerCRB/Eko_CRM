import { apiRequest } from "./client";

// Shape of backend/app/api/reference.py (`voivodeship_list`, VoivodeshipList), written by hand
// and checked against the OpenAPI document by the EKO-1-35 check
// (backend/tests/support/frontend_contract.py). The lists come only from this answer, so
// the form offers exactly the names the server validates with (Q-3 A, Q-4 A).

export interface VoivodeshipEntry {
  name: string;
  counties: string[];
}

export interface VoivodeshipList {
  as_of: string;
  voivodeships: VoivodeshipEntry[];
}

export type VoivodeshipsResult =
  | { kind: "listed"; voivodeships: VoivodeshipEntry[] }
  | { kind: "failed" };

export const VOIVODESHIPS_PATH = "/api/reference/voivodeships";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseEntry(value: unknown): VoivodeshipEntry | null {
  if (!isRecord(value)) {
    return null;
  }
  const { name, counties } = value;
  if (typeof name !== "string" || !Array.isArray(counties)) {
    return null;
  }
  const names: string[] = [];
  for (const county of counties) {
    if (typeof county !== "string") {
      return null;
    }
    names.push(county);
  }
  return { name, counties: names };
}

// An empty list is refused too: the register always has voivodeships, and an empty select would
// look like a deliberate "nothing to pick".
export function parseVoivodeships(body: unknown): VoivodeshipEntry[] | null {
  if (!isRecord(body) || !Array.isArray(body["voivodeships"])) {
    return null;
  }
  const entries: VoivodeshipEntry[] = [];
  for (const value of body["voivodeships"]) {
    const entry = parseEntry(value);
    if (entry === null) {
      return null;
    }
    entries.push(entry);
  }
  return entries.length === 0 ? null : entries;
}

export async function readVoivodeships(): Promise<VoivodeshipsResult> {
  const response = await apiRequest(VOIVODESHIPS_PATH);
  if (response.kind !== "ok") {
    return { kind: "failed" };
  }
  const voivodeships = parseVoivodeships(response.body);
  return voivodeships === null ? { kind: "failed" } : { kind: "listed", voivodeships };
}
