/**
 * Eko_CRM domain rules for the frontend — prototype P1 handoff.
 *
 * Typed version of ../js/domain.js, meant as a starting point for `frontend/src/domain/`.
 * These give instant form feedback only; the server stays the authority (CUS-3, ACT-2, ACC-4).
 * Requirement identifiers refer to docs/product/project-brief.md.
 * Not wired into a build and not tested yet: the stack is decided in EKO-1-01.
 */

/* ---------- Types ---------- */

export type Role = "rep" | "manager" | "administrator";
export type GoogleLink = "linked" | "expired" | "none";

export interface Viewer {
  id: string;
  role: Role;
}

export interface Contact {
  value: string;
  /** Who this number or address reaches, e.g. "żona", "biuro" (CUS-1). */
  note: string;
  primary?: boolean;
}

export interface Address {
  street: string;
  postalCode: string;
  town: string;
  voivodeship: string;
  county: string;
  country: string;
}

export interface Customer {
  id: string | null;
  ownerId: string;
  name: string;
  nip: string;
  address: Address;
  phones: Contact[];
  emails: Contact[];
  archived: boolean;
}

/** Stored facts; the visit state is derived from them (glossary). */
export interface Visit {
  id: string;
  customerId: string;
  ownerId: string;
  start: string; // ISO, Europe/Warsaw in production
  end: string;
  cancelled: boolean;
  deletedInGoogle: boolean;
  /** Flag: start changed at least once (VIS-9). */
  moved: boolean;
  /** Flag: not yet mirrored to Google (VIS-7). */
  unsynced: boolean;
  place: string;
}

export type VisitState = "planned" | "held" | "cancelled" | "awaiting";

export type ActionStatus = "todo" | "inprogress" | "done" | "cancelled";

export interface Action {
  id: string;
  noteId: string;
  customerId: string;
  ownerId: string;
  authorId: string;
  desc: string;
  due: string | null; // YYYY-MM-DD
  status: ActionStatus;
  history: { by: string; to: ActionStatus }[];
}

export type Result<T> = { ok: true; value: T } | { ok: false; error: string };

/* ---------- Reference data ---------- */

export const VOIVODESHIPS = [
  "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "łódzkie", "małopolskie",
  "mazowieckie", "opolskie", "podkarpackie", "podlaskie", "pomorskie", "śląskie",
  "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie",
] as const;

/** Counties per voivodeship: load the full TERYT register from the API; the prototype has a sample. */
export type CountyIndex = Record<string, readonly string[]>;

export const VISIT_STATE_LABEL: Record<VisitState, string> = {
  planned: "Zaplanowana",
  held: "Odbyta",
  cancelled: "Odwołana",
  awaiting: "Czeka na decyzję",
};

export const ACTION_STATUS_LABEL: Record<ActionStatus, string> = {
  todo: "Do zrobienia",
  inprogress: "W toku",
  done: "Zrobione",
  cancelled: "Anulowane",
};

/* ---------- NIP (CUS-5) ---------- */

const NIP_WEIGHTS = [6, 5, 7, 2, 3, 4, 5, 6, 7];
const POLAND = "Polska";

export function normalizeNip(raw: string): string {
  return raw.replace(/^\s*PL/i, "").replace(/[\s-]/g, "");
}

export function validateNip(raw: string, country: string): Result<string> {
  if (!raw.trim()) return { ok: true, value: "" };
  if (country !== POLAND) return { ok: true, value: raw.trim() }; // foreign tax ID: free text
  const v = normalizeNip(raw);
  if (!/^\d{10}$/.test(v)) return { ok: false, error: "NIP ma 10 cyfr. Myślniki, spacje i prefiks PL są pomijane." };
  const sum = NIP_WEIGHTS.reduce((s, w, i) => s + w * Number(v[i]), 0) % 11;
  if (sum === 10 || sum !== Number(v[9])) return { ok: false, error: "Ten NIP ma błędną cyfrę kontrolną. Sprawdź, czy nie ma literówki." };
  return { ok: true, value: v };
}

export function formatNip(v: string): string {
  return v.length === 10 ? `${v.slice(0, 3)}-${v.slice(3, 6)}-${v.slice(6, 8)}-${v.slice(8)}` : v;
}

/* ---------- Address (CUS-3, CUS-4) ---------- */

export type AddressErrors = Partial<Record<"postalCode" | "voivodeship" | "county", string>>;

export function validateAddress(a: Address, counties: CountyIndex): AddressErrors {
  const errors: AddressErrors = {};
  if (a.country !== POLAND) return errors;
  if (a.postalCode && !/^\d{2}-\d{3}$/.test(a.postalCode)) errors.postalCode = "Kod pocztowy w formacie 00-000.";
  if (a.voivodeship && !(VOIVODESHIPS as readonly string[]).includes(a.voivodeship)) errors.voivodeship = "Wybierz jedno z 16 województw.";
  if (a.county) {
    if (!a.voivodeship) errors.county = "Najpierw wybierz województwo.";
    else if (!counties[a.voivodeship]?.includes(a.county)) errors.county = "Ten powiat nie leży w wybranym województwie.";
  }
  return errors;
}

/* ---------- Contacts (CUS-8) ---------- */

export function normalizePhone(raw: string): string {
  let v = raw.replace(/[\s()-]/g, "");
  if (!v) return "";
  if (v.startsWith("00")) v = "+" + v.slice(2);
  if (!v.startsWith("+")) v = "+48" + v;
  return v;
}

export function validatePhone(raw: string): Result<string> {
  const v = normalizePhone(raw);
  return /^\+\d{8,15}$/.test(v) ? { ok: true, value: v } : { ok: false, error: "Numer w formacie międzynarodowym, np. +48 600 100 200." };
}

export function formatPhone(v: string): string {
  const m = /^\+48(\d{3})(\d{3})(\d{3})$/.exec(v);
  return m ? `+48 ${m[1]} ${m[2]} ${m[3]}` : v;
}

export function validateEmail(raw: string): Result<string> {
  const v = raw.trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) ? { ok: true, value: v.toLowerCase() } : { ok: false, error: "Adres e-mail wygląda na niepełny." };
}

/* ---------- Visit state (glossary, VIS-*) ---------- */

export function visitState(v: Visit, now: Date): VisitState {
  if (v.cancelled) return "cancelled";
  if (v.deletedInGoogle) return "awaiting";
  return new Date(v.end) <= now ? "held" : "planned";
}

/* ---------- Action status (ACT-2, ACT-3, ACT-4, ACC-5) ---------- */

export const TRANSITIONS: Record<ActionStatus, readonly ActionStatus[]> = {
  todo: ["inprogress", "done", "cancelled"],
  inprogress: ["done", "cancelled", "todo"],
  done: ["todo"],
  cancelled: ["todo"],
};

/** What the viewer may switch this action to. The manager may only close someone else's action. */
export function allowedTransitions(action: Action, viewer: Viewer): ActionStatus[] {
  const next = [...TRANSITIONS[action.status]];
  if (action.ownerId === viewer.id) return next;
  if (viewer.role === "manager") return next.filter((s) => s === "done" || s === "cancelled");
  return [];
}

const isClosed = (a: Action) => a.status === "done" || a.status === "cancelled";

/** Computed, never stored (ACT-3). */
export function isOverdue(a: Action, now: Date): boolean {
  return !!a.due && !isClosed(a) && endOfDay(a.due) < now;
}

/** In-app reminder: due today or earlier, not closed, has a due date (ACT-4). */
export function isReminder(a: Action, now: Date): boolean {
  return !!a.due && !isClosed(a) && startOfDay(a.due) <= now;
}

/* ---------- Dashboard (DSH-2, DSH-3) ---------- */

export interface DashboardCounts {
  planned: number;
  held: number;
  moved: number;
  cancelled: number;
  awaiting: number;
}

export function dashboardCounts(visits: Visit[], from: Date, to: Date, now: Date): DashboardCounts {
  const c: DashboardCounts = { planned: 0, held: 0, moved: 0, cancelled: 0, awaiting: 0 };
  for (const v of visits) {
    const t = new Date(v.start);
    if (t < from || t > to) continue;
    const s = visitState(v, now);
    if (s === "cancelled") c.cancelled++;
    else if (s === "awaiting") c.awaiting++;
    else {
      c.planned++;
      if (s === "held") c.held++;
    }
    if (v.moved) c.moved++;
  }
  return c;
}

/* ---------- Dates ---------- */
// Production must compute day boundaries in Europe/Warsaw, not the browser zone.

export function startOfDay(d: string | Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export function endOfDay(d: string | Date): Date {
  const x = new Date(d);
  x.setHours(23, 59, 59, 999);
  return x;
}
