import { apiRequest } from "./client";

// Shapes of backend/app/api/customers.py (CustomerCreate, ContactIn, CustomerOut, CustomerList),
// written by hand and checked against the OpenAPI document by the backend's contract check
// (EKO-1-35). Unknown extra fields in an answer are ignored, so a backend that adds one does not
// break the SPA during a rolling deployment. The answer's `kind` and `country` are plain strings.

export type ContactKind = "phone" | "email";

export interface ContactInput {
  kind: ContactKind;
  value: string;
  note: string | null;
  primary: boolean;
}

export interface CustomerInput {
  name: string;
  country: string;
  contacts: ContactInput[];
}

export interface ContactRecord {
  kind: string;
  value: string;
  note: string | null;
  primary: boolean;
}

export interface CustomerRecord {
  id: string;
  name: string;
  country: string;
  contacts: ContactRecord[];
}

export interface CustomerSummary {
  id: string;
  name: string;
  country: string;
}

export interface CustomerList {
  items: CustomerSummary[];
}

// FastAPI's 422 answer; only `loc` is read, never `msg` or `input` (which echoes the value).
// The document does not require `detail`; without it the request as a whole is named as rejected.
export interface ValidationProblem {
  detail?: { type: string; loc: (string | number)[]; msg: string }[];
}

// Which field a rejection names, by its place in the request.
export type RejectedField =
  | { field: "name" }
  | { field: "country" }
  | { field: "contacts" }
  | { field: "contact"; index: number; part: "kind" | "value" | "note" | "primary" }
  | { field: "request" };

export type CreateResult =
  | { kind: "created"; customer: CustomerRecord }
  | { kind: "rejected"; fields: RejectedField[] }
  | { kind: "refused" }
  | { kind: "failed" };

export type ReadResult =
  | { kind: "found"; customer: CustomerRecord }
  | { kind: "notFound" }
  | { kind: "failed" };

export type ListResult = { kind: "listed"; customers: CustomerSummary[] } | { kind: "failed" };

const CUSTOMER_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Only an opaque identifier ever goes into a path (ADR-0005-C13).
export function isCustomerId(value: string): boolean {
  return CUSTOMER_ID.test(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseContact(value: unknown): ContactRecord | null {
  if (!isRecord(value)) {
    return null;
  }
  const { kind, value: contactValue, note, primary } = value;
  if (typeof kind !== "string" || typeof contactValue !== "string" || typeof primary !== "boolean") {
    return null;
  }
  if (note !== null && typeof note !== "string") {
    return null;
  }
  return { kind, value: contactValue, note, primary };
}

function parseSummary(value: unknown): CustomerSummary | null {
  if (!isRecord(value)) {
    return null;
  }
  const { id, name, country } = value;
  if (typeof id !== "string" || !isCustomerId(id)) {
    return null;
  }
  if (typeof name !== "string" || typeof country !== "string") {
    return null;
  }
  return { id, name, country };
}

export function parseCustomer(value: unknown): CustomerRecord | null {
  const summary = parseSummary(value);
  if (summary === null || !isRecord(value) || !Array.isArray(value["contacts"])) {
    return null;
  }
  const contacts: ContactRecord[] = [];
  for (const entry of value["contacts"]) {
    const contact = parseContact(entry);
    if (contact === null) {
      return null;
    }
    contacts.push(contact);
  }
  return { ...summary, contacts };
}

export function parseCustomerList(value: unknown): CustomerSummary[] | null {
  if (!isRecord(value) || !Array.isArray(value["items"])) {
    return null;
  }
  const customers: CustomerSummary[] = [];
  for (const entry of value["items"]) {
    const summary = parseSummary(entry);
    if (summary === null) {
      return null;
    }
    customers.push(summary);
  }
  return customers;
}

const CONTACT_PARTS = ["kind", "value", "note", "primary"] as const;

function rejectedField(loc: unknown): RejectedField {
  if (!Array.isArray(loc) || loc[0] !== "body") {
    return { field: "request" };
  }
  const [, top, index, part] = loc as unknown[];
  if (top === "name" && loc.length === 2) {
    return { field: "name" };
  }
  if (top === "country" && loc.length === 2) {
    return { field: "country" };
  }
  if (top === "contacts" && loc.length === 2) {
    return { field: "contacts" };
  }
  if (top === "contacts" && typeof index === "number") {
    const known = CONTACT_PARTS.find((candidate) => candidate === part);
    return known === undefined ? { field: "request" } : { field: "contact", index, part: known };
  }
  return { field: "request" };
}

export function parseRejection(body: unknown): RejectedField[] {
  if (!isRecord(body) || !Array.isArray(body["detail"]) || body["detail"].length === 0) {
    return [{ field: "request" }];
  }
  return body["detail"].map((entry: unknown) =>
    rejectedField(isRecord(entry) ? entry["loc"] : undefined),
  );
}

export async function createCustomer(input: CustomerInput): Promise<CreateResult> {
  const response = await apiRequest("/api/customers", { method: "POST", body: input });
  if (response.kind === "ok") {
    const customer = parseCustomer(response.body);
    return customer === null ? { kind: "failed" } : { kind: "created", customer };
  }
  if (response.kind === "failed" && response.status === 422) {
    return { kind: "rejected", fields: parseRejection(response.body) };
  }
  if (response.kind === "failed" && response.status === 403) {
    return { kind: "refused" };
  }
  return { kind: "failed" };
}

export async function readCustomer(id: string): Promise<ReadResult> {
  if (!isCustomerId(id)) {
    return { kind: "notFound" };
  }
  const response = await apiRequest(`/api/customers/${id}`);
  if (response.kind === "ok") {
    const customer = parseCustomer(response.body);
    return customer === null ? { kind: "failed" } : { kind: "found", customer };
  }
  if (response.kind === "failed" && response.status === 404) {
    return { kind: "notFound" };
  }
  return { kind: "failed" };
}

export async function listCustomers(): Promise<ListResult> {
  const response = await apiRequest("/api/customers");
  if (response.kind !== "ok") {
    return { kind: "failed" };
  }
  const customers = parseCustomerList(response.body);
  return customers === null ? { kind: "failed" } : { kind: "listed", customers };
}
