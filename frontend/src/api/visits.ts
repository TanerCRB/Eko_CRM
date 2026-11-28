import { isCalendarDate, isInstant } from "../time/warsaw";
import { apiRequest } from "./client";
import { isCustomerId } from "./customers";

// Shapes of backend/app/api/visits.py (WallTimeIn, VisitCreate, VisitCustomerOut, VisitOut,
// VisitList, the period query), written by hand and checked against the OpenAPI document by the
// backend's contract check (EKO-1-35). A wall time crosses exactly as typed, a Europe/Warsaw date
// `YYYY-MM-DD` and a time `HH:MM` with no offset (ADR-0001 Constraint 3): this client never turns
// it into an instant. Answers are read as unknown until each item passes `parseVisit`. The 422 is
// FastAPI's shared HTTPValidationError, mirrored once as `ValidationProblem` in customers.ts; only
// its `type` and `loc` are read here, never `msg`.

export interface WallTimeInput {
  date: string;
  time: string;
}

// `own_address` is left out when not given; `null` mirrors the document.
export interface VisitInput {
  customer_id: string;
  start: WallTimeInput;
  end: WallTimeInput;
  own_address?: string | null;
}

// The customer's current address (G-8 A), shown when the visit has no own address.
export interface VisitCustomer {
  id: string;
  name: string;
  street: string | null;
  postal_code: string | null;
  town: string | null;
  voivodeship: string | null;
  county: string | null;
}

// `starts_at`/`ends_at` are RFC 3339 instants, shown only through `time/warsaw.ts`; `state` is the
// server's, derived from its clock (K-05), never recomputed here.
export interface Visit {
  id: string;
  customer: VisitCustomer;
  starts_at: string;
  ends_at: string;
  own_address: string | null;
  state: "planned" | "held";
}

export interface VisitList {
  items: Visit[];
}

// Both inclusive Europe/Warsaw dates; a day is `first` = `last`.
export interface VisitPeriodQuery {
  first: string;
  last: string;
}

// Not exported, as `EditResult` in customers.ts: the contract check compares every exported type.
type VisitsResult = { kind: "listed"; visits: Visit[] } | { kind: "failed" };

type WallTimeSide = "start" | "end";

// Which field a 422 names. The two DST reasons of ADR-0002-C15 stay apart.
type PlanRejection =
  | { field: "customer" }
  | { field: WallTimeSide; reason: "nonexistent" | "ambiguous" | "invalid" }
  | { field: WallTimeSide; part: "date" | "time" }
  | { field: "end"; reason: "notAfterStart" }
  | { field: "ownAddress" }
  | { field: "request" };

type PlanResult =
  | { kind: "planned"; visit: Visit }
  | { kind: "rejected"; fields: PlanRejection[] }
  | { kind: "notFound" }
  | { kind: "restoreFirst" }
  | { kind: "refused" }
  | { kind: "failed" };

// The machine values the backend pins for the two refusals (backend/app/api/visits.py).
const NONEXISTENT_TYPE = "nonexistent_local_time";
const AMBIGUOUS_TYPE = "ambiguous_local_time";
const RESTORE_FIRST_DETAIL = "restore it first";
const ADDRESS_PARTS = ["street", "postal_code", "town", "voivodeship", "county"] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isText(value: unknown): value is string {
  return typeof value === "string";
}

function isOptionalText(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function parseCustomer(value: unknown): VisitCustomer | null {
  if (!isRecord(value)) {
    return null;
  }
  const { id, name } = value;
  if (!isText(id) || !isCustomerId(id) || !isText(name)) {
    return null;
  }
  const parts = ADDRESS_PARTS.map((part) => value[part]);
  if (!parts.every(isOptionalText)) {
    return null;
  }
  const [street, postal_code, town, voivodeship, county] = parts;
  return {
    id,
    name,
    street: street ?? null,
    postal_code: postal_code ?? null,
    town: town ?? null,
    voivodeship: voivodeship ?? null,
    county: county ?? null,
  };
}

function parseVisit(value: unknown): Visit | null {
  if (!isRecord(value)) {
    return null;
  }
  const { id, starts_at, ends_at, own_address, state } = value;
  const customer = parseCustomer(value["customer"]);
  if (!isText(id) || !isCustomerId(id) || customer === null) {
    return null;
  }
  if (!isText(starts_at) || !isInstant(starts_at) || !isText(ends_at) || !isInstant(ends_at)) {
    return null;
  }
  if (!isOptionalText(own_address) || (state !== "planned" && state !== "held")) {
    return null;
  }
  return { id, customer, starts_at, ends_at, own_address, state };
}

function parseVisitList(value: unknown): Visit[] | null {
  if (!isRecord(value) || !Array.isArray(value["items"])) {
    return null;
  }
  const visits: Visit[] = [];
  for (const entry of value["items"]) {
    const parsed = parseVisit(entry);
    if (parsed === null) {
      return null;
    }
    visits.push(parsed);
  }
  return visits;
}

async function readList(path: `/api/${string}`): Promise<VisitsResult> {
  const response = await apiRequest(path);
  if (response.kind !== "ok") {
    return { kind: "failed" };
  }
  const visits = parseVisitList(response.body);
  return visits === null ? { kind: "failed" } : { kind: "listed", visits };
}

// Every visit the caller may read, past and future.
export function listVisits(): Promise<VisitsResult> {
  return readList("/api/visits");
}

// The dates go into the request's query only, never into the SPA's location (ADR-0005-C13).
export function listVisitPeriod(query: VisitPeriodQuery): Promise<VisitsResult> {
  if (!isCalendarDate(query.first) || !isCalendarDate(query.last)) {
    return Promise.resolve({ kind: "failed" });
  }
  const params = new URLSearchParams({ first: query.first, last: query.last });
  return readList(`/api/visits/period?${params.toString()}`);
}

function rejectedField(entry: unknown): PlanRejection {
  if (!isRecord(entry) || !Array.isArray(entry["loc"]) || entry["loc"][0] !== "body") {
    return { field: "request" };
  }
  const type = entry["type"];
  const loc: unknown[] = entry["loc"];
  const [, top, part] = loc;
  if (top === "customer_id" && loc.length === 2) {
    return { field: "customer" };
  }
  if (top === "own_address" && loc.length === 2) {
    return { field: "ownAddress" };
  }
  if (top !== "start" && top !== "end") {
    return { field: "request" };
  }
  if (loc.length === 3 && (part === "date" || part === "time")) {
    return { field: top, part };
  }
  if (loc.length !== 2) {
    return { field: "request" };
  }
  if (type === NONEXISTENT_TYPE) {
    return { field: top, reason: "nonexistent" };
  }
  if (type === AMBIGUOUS_TYPE) {
    return { field: top, reason: "ambiguous" };
  }
  if (top === "end" && type === "value_error") {
    return { field: "end", reason: "notAfterStart" };
  }
  return { field: top, reason: "invalid" };
}

function parseRejection(body: unknown): PlanRejection[] {
  if (!isRecord(body) || !Array.isArray(body["detail"]) || body["detail"].length === 0) {
    return [{ field: "request" }];
  }
  return body["detail"].map(rejectedField);
}

// No idempotency key: the contract has none, and a repeat after a timeout makes a second visit
// (Out of scope); the form sends one create per submit.
export async function planVisit(input: VisitInput): Promise<PlanResult> {
  const response = await apiRequest("/api/visits", { method: "POST", body: input });
  if (response.kind === "ok") {
    const visit = parseVisit(response.body);
    return visit === null ? { kind: "failed" } : { kind: "planned", visit };
  }
  if (response.kind !== "failed") {
    return { kind: "failed" };
  }
  if (response.status === 422) {
    return { kind: "rejected", fields: parseRejection(response.body) };
  }
  if (response.status === 404) {
    return { kind: "notFound" };
  }
  if (response.status === 403) {
    return { kind: "refused" };
  }
  if (response.status === 409 && isRecord(response.body)) {
    return response.body["detail"] === RESTORE_FIRST_DETAIL
      ? { kind: "restoreFirst" }
      : { kind: "failed" };
  }
  return { kind: "failed" };
}
