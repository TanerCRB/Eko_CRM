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

// The address parts and the tax ID (EKO-3-02): optional on create, a part not given is left out of
// the request. `tax_id` is one field; the server places it as a NIP or a foreign tax ID by country.
export const ADDRESS_PARTS = [
  "street",
  "postal_code",
  "town",
  "voivodeship",
  "county",
  "tax_id",
] as const;

// Not exported: the backend's contract check (EKO-1-35) fails an exported type it does not compare.
type AddressPart = (typeof ADDRESS_PARTS)[number];

// Written out field by field, not composed, so the contract check can read it; `null` mirrors the
// document, the form never sends it (a part left empty is left out).
export interface CustomerInput {
  name: string;
  country: string;
  contacts: ContactInput[];
  street?: string | null;
  postal_code?: string | null;
  town?: string | null;
  voivodeship?: string | null;
  county?: string | null;
  tax_id?: string | null;
}

export interface ContactRecord {
  kind: string;
  value: string;
  note: string | null;
  primary: boolean;
}

// A backend from before EKO-3-02 sends no address parts during a rolling deployment;
// `parseCustomer` reads a missing part as `null` (not given), so the parsed record always has them.
// `archived` (EKO-3-05) is the stored state; a backend from before it sends none, read as active.
export interface CustomerRecord {
  id: string;
  name: string;
  country: string;
  contacts: ContactRecord[];
  street: string | null;
  postal_code: string | null;
  town: string | null;
  voivodeship: string | null;
  county: string | null;
  tax_id: string | null;
  archived: boolean;
}

// `archived` is each item's stored state, never the `state` the list was asked for.
export interface CustomerSummary {
  id: string;
  name: string;
  country: string;
  archived: boolean;
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
  | { field: AddressPart }
  | { field: "request" };

export type CreateResult =
  | { kind: "created"; customer: CustomerRecord }
  | { kind: "rejected"; fields: RejectedField[] }
  | { kind: "refused" }
  | { kind: "failed" };

// Not exported (the contract check compares every exported type); the edit's answer as the form
// reads it. "notFound": the id exists nowhere the caller may see (ADR-0003-C33); "restoreFirst":
// the customer is archived and must be restored before its data can change (EKO-3-05 S-2 A).
type EditResult =
  | { kind: "saved"; customer: CustomerRecord }
  | { kind: "rejected"; fields: RejectedField[] }
  | { kind: "refused" }
  | { kind: "notFound" }
  | { kind: "restoreFirst" }
  | { kind: "failed" };

// Archive and restore answer the customer as it now is; not exported, as `EditResult`.
type StateChangeResult =
  | { kind: "changed"; customer: CustomerRecord }
  | { kind: "notFound" }
  | { kind: "failed" };

export type ReadResult =
  | { kind: "found"; customer: CustomerRecord }
  | { kind: "notFound" }
  | { kind: "failed" };

// The list operation's query parameters (EKO-3-04 Q-6, EKO-3-08): `listPath` sends exactly these
// keys, each through its entry in `LIST_QUERY_VALUES`, which fails to compile if one is missing.
// `state` (EKO-3-05 Q-5): absent means active on the server, as an empty value does.
export interface CustomerListQuery {
  q?: string;
  owner?: string;
  state?: "active" | "archived" | "both";
}

// "rejected": the server refused the query (422); its body is not read, so no value comes back.
export type ListResult =
  | { kind: "listed"; customers: CustomerSummary[] }
  | { kind: "rejected" }
  | { kind: "failed" };

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
  const { id, name, country, archived } = value;
  if (typeof id !== "string" || !isCustomerId(id)) {
    return null;
  }
  if (typeof name !== "string" || typeof country !== "string") {
    return null;
  }
  // Missing means a backend from before EKO-3-05, where nothing could be archived.
  if (archived !== undefined && typeof archived !== "boolean") {
    return null;
  }
  return { id, name, country, archived: archived === true };
}

export function parseCustomer(value: unknown): CustomerRecord | null {
  const summary = parseSummary(value);
  if (summary === null || !isRecord(value) || !Array.isArray(value["contacts"])) {
    return null;
  }
  const address: Record<AddressPart, string | null> = {
    street: null,
    postal_code: null,
    town: null,
    voivodeship: null,
    county: null,
    tax_id: null,
  };
  for (const part of ADDRESS_PARTS) {
    const given = value[part];
    if (typeof given === "string") {
      address[part] = given;
    } else if (given !== undefined && given !== null) {
      return null;
    }
  }
  const contacts: ContactRecord[] = [];
  for (const entry of value["contacts"]) {
    const contact = parseContact(entry);
    if (contact === null) {
      return null;
    }
    contacts.push(contact);
  }
  return { ...summary, ...address, contacts };
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
  const addressPart = ADDRESS_PARTS.find((candidate) => candidate === top);
  if (addressPart !== undefined && loc.length === 2) {
    return { field: addressPart };
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

// The edit states the whole customer in the create body (G-6 A): `PUT` replaces what is stored.
export async function editCustomer(id: string, input: CustomerInput): Promise<EditResult> {
  if (!isCustomerId(id)) {
    return { kind: "notFound" };
  }
  const response = await apiRequest(`/api/customers/${id}`, { method: "PUT", body: input });
  if (response.kind === "ok") {
    const customer = parseCustomer(response.body);
    return customer === null ? { kind: "failed" } : { kind: "saved", customer };
  }
  if (response.kind === "failed" && response.status === 422) {
    return { kind: "rejected", fields: parseRejection(response.body) };
  }
  if (response.kind === "failed" && response.status === 403) {
    return { kind: "refused" };
  }
  if (response.kind === "failed" && response.status === 404) {
    return { kind: "notFound" };
  }
  if (response.kind === "failed" && response.status === 409 && isRestoreFirst(response.body)) {
    return { kind: "restoreFirst" };
  }
  return { kind: "failed" };
}

// Compared byte for byte: any other 409 is a conflict the SPA does not know how to resolve.
const RESTORE_FIRST_DETAIL = "restore it first";

function isRestoreFirst(body: unknown): boolean {
  return isRecord(body) && body["detail"] === RESTORE_FIRST_DETAIL;
}

async function changeState(id: string, change: "archive" | "restore"): Promise<StateChangeResult> {
  if (!isCustomerId(id)) {
    return { kind: "notFound" };
  }
  const response = await apiRequest(`/api/customers/${id}/${change}`, { method: "POST" });
  if (response.kind === "ok") {
    const customer = parseCustomer(response.body);
    return customer === null ? { kind: "failed" } : { kind: "changed", customer };
  }
  if (response.kind === "failed" && response.status === 404) {
    return { kind: "notFound" };
  }
  return { kind: "failed" };
}

// Both send no body; a repeat answers the same customer, so a retry is harmless (K-04).
export function archiveCustomer(id: string): Promise<StateChangeResult> {
  return changeState(id, "archive");
}

export function restoreCustomer(id: string): Promise<StateChangeResult> {
  return changeState(id, "restore");
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

// What each parameter sends, `null` leaving it out: a blank term is no term; the owner is an opaque
// subject, sent byte-equal, and empty means every owner the caller may see.
const LIST_QUERY_VALUES: {
  [K in keyof Required<CustomerListQuery>]: (given: string) => string | null;
} = {
  q: (given) => {
    const term = given.trim();
    return term === "" ? null : term;
  },
  owner: (given) => (given === "" ? null : given),
  // The closed set is the type's, so a given value is always one the server accepts.
  state: (given) => given,
};

function isListQueryName(name: string): name is keyof CustomerListQuery {
  return name in LIST_QUERY_VALUES;
}

// The parameters go into the request's query string only, never into the SPA's location
// (ADR-0005-C13); with none given the request is the unfiltered list.
function listPath(query: CustomerListQuery): `/api/${string}` {
  const params = new URLSearchParams();
  for (const name of Object.keys(LIST_QUERY_VALUES).filter(isListQueryName)) {
    const given = query[name];
    const value = given === undefined ? null : LIST_QUERY_VALUES[name](given);
    if (value !== null) {
      params.set(name, value);
    }
  }
  const search = params.toString();
  return search === "" ? "/api/customers" : `/api/customers?${search}`;
}

export async function listCustomers(query: CustomerListQuery = {}): Promise<ListResult> {
  const response = await apiRequest(listPath(query));
  if (response.kind === "failed" && response.status === 422) {
    return { kind: "rejected" };
  }
  if (response.kind !== "ok") {
    return { kind: "failed" };
  }
  const customers = parseCustomerList(response.body);
  return customers === null ? { kind: "failed" } : { kind: "listed", customers };
}
