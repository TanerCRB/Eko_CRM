/**
 * Eko_CRM prototype P3 — domain rules, typed. Mirror of ../app/rules.js for `frontend/src/domain/`.
 *
 * Rules return codes, never sentences: the string catalogue (handoff/pl.json, keys `err.*`,
 * `conflict.*`, `warn.*`) turns a code into words in the active language. The server stays the
 * authority (CUS-3, CUS-6, ACT-2, ACC-4); this layer gives forms instant feedback.
 * Not wired into a build and not tested: the stack is decided in EKO-1-01.
 */

export type Role = "rep" | "manager" | "administrator";
export type GoogleLink = "linked" | "expired" | "none";
export interface Viewer { id: string; role: Role }

export interface Contact { value: string; who: string; primary?: boolean }
export interface Address { street: string; postalCode: string; town: string; voivodeship: string; county: string; country: string }
export interface Customer {
  id: string | null; ownerId: string; name: string; nip: string; address: Address;
  phones: Contact[]; emails: Contact[]; archived: boolean;
}

/** Stored facts; the state is derived (glossary). */
export interface Visit {
  id: string; customerId: string; ownerId: string;
  start: string; end: string; // ISO; production computes in Europe/Warsaw
  cancelled: boolean; deletedInGoogle: boolean;
  moved: boolean;    // flag, VIS-9: start changed at least once
  unsynced: boolean; // flag, VIS-7: not yet mirrored to Google
  place: string;
}
export type VisitState = "planned" | "held" | "cancelled" | "awaiting";

export type TaskStatus = "todo" | "progress" | "done" | "cancelled";
export interface Task {
  id: string; noteId: string; customerId: string; ownerId: string; authorId: string;
  text: string; due: string | null; status: TaskStatus; log: { by: string; to: TaskStatus }[];
}

export type Check<T> = { ok: true; value: T } | { ok: false; code: string };

export const POLAND = "Polska";
export const VOIVODESHIPS = [
  "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "łódzkie", "małopolskie",
  "mazowieckie", "opolskie", "podkarpackie", "podlaskie", "pomorskie", "śląskie",
  "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie",
] as const;
/** County register per voivodeship: the API serves the full TERYT list; the prototype has a sample. */
export type CountyIndex = Record<string, readonly string[]>;

/* ---------- NIP (CUS-5) ---------- */
const NIP_WEIGHTS = [6, 5, 7, 2, 3, 4, 5, 6, 7];
export const normalizeNip = (raw: string): string => raw.replace(/^\s*PL/i, "").replace(/[\s-]/g, "");
export function nipCheckDigit(nine: string): number | null {
  const sum = NIP_WEIGHTS.reduce((acc, w, i) => acc + w * Number(nine[i]), 0) % 11;
  return sum === 10 ? null : sum;
}
export function checkNip(raw: string, country: string): Check<string> {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, value: "" };
  if (country !== POLAND) return { ok: true, value: trimmed };
  const v = normalizeNip(trimmed);
  if (!/^\d{10}$/.test(v)) return { ok: false, code: "nipDigits" };
  if (nipCheckDigit(v) !== Number(v[9])) return { ok: false, code: "nipChecksum" };
  return { ok: true, value: v };
}
export const formatNip = (v: string): string => (v.length === 10 ? `${v.slice(0, 3)}-${v.slice(3, 6)}-${v.slice(6, 8)}-${v.slice(8)}` : v);

/* ---------- Address (CUS-3, CUS-4) ---------- */
export type AddressCodes = Partial<Record<"postalCode" | "voivodeship" | "county", string>>;
export function checkAddress(a: Address, counties: CountyIndex): AddressCodes {
  const codes: AddressCodes = {};
  if (a.country !== POLAND) return codes;
  if (a.postalCode && !/^\d{2}-\d{3}$/.test(a.postalCode)) codes.postalCode = "postal";
  if (a.voivodeship && !(VOIVODESHIPS as readonly string[]).includes(a.voivodeship)) codes.voivodeship = "voivodeship";
  if (a.county) {
    if (!a.voivodeship) codes.county = "countyNoVoivodeship";
    else if (counties[a.voivodeship] && !counties[a.voivodeship].includes(a.county)) codes.county = "countyMismatch";
  }
  return codes;
}
export const addressLine = (a: Address): string =>
  [a.street, [a.postalCode, a.town].filter(Boolean).join(" "), a.country !== POLAND ? a.country : ""].filter(Boolean).join(", ");

/* ---------- Contacts (CUS-8) ---------- */
export function normalizePhone(raw: string): string {
  let v = raw.replace(/[\s()./-]/g, "");
  if (!v) return "";
  if (v.startsWith("00")) v = "+" + v.slice(2);
  if (!v.startsWith("+")) v = "+48" + v;
  return v;
}
export const checkPhone = (raw: string): Check<string> => { const v = normalizePhone(raw); return /^\+\d{8,15}$/.test(v) ? { ok: true, value: v } : { ok: false, code: "phone" }; };
export const formatPhone = (v: string): string => { const m = /^\+48(\d{3})(\d{3})(\d{3})$/.exec(v); return m ? `+48 ${m[1]} ${m[2]} ${m[3]}` : v; };
export const checkEmail = (raw: string): Check<string> => { const v = raw.trim(); return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) ? { ok: true, value: v.toLowerCase() } : { ok: false, code: "email" }; };

/* ---------- Customer draft (CUS-2, CUS-6, CUS-7, ACC-8) ---------- */
export interface CustomerCheck {
  codes: Record<string, string>;
  warnings: { code: "samePhone" | "sameEmail" | "sameNameTown"; name: string; town?: string }[];
  conflict: null | { code: "nipRep" | "nipManager"; customerId: string | null };
}
export function checkCustomer(draft: Customer, others: Customer[], viewer: Viewer, counties: CountyIndex): CustomerCheck {
  const codes: Record<string, string> = {};
  if (!draft.name.trim()) codes.name = "nameRequired";
  if (!draft.address.country) codes.country = "countryRequired";
  Object.assign(codes, checkAddress(draft.address, counties));
  const nip = checkNip(draft.nip, draft.address.country);
  if (!nip.ok) codes.nip = nip.code;
  draft.phones.forEach((p, i) => { if (p.value && !checkPhone(p.value).ok) codes[`phone${i}`] = "phone"; });
  draft.emails.forEach((e, i) => { if (e.value && !checkEmail(e.value).ok) codes[`email${i}`] = "email"; });

  let conflict: CustomerCheck["conflict"] = null;
  if (nip.ok && nip.value && draft.address.country === POLAND) {
    const hit = others.find((c) => c.nip === nip.value);
    // ACC-8: a rep learns nothing about the other customer or its owner.
    if (hit) conflict = viewer.role === "manager" ? { code: "nipManager", customerId: hit.id } : { code: "nipRep", customerId: null };
  }
  // CUS-7: duplicates are warned within the viewer's scope only.
  const scope = viewer.role === "manager" ? others : others.filter((c) => c.ownerId === viewer.id);
  const key = (s: string) => s.trim().toLowerCase();
  const phones = draft.phones.map((p) => normalizePhone(p.value)).filter(Boolean);
  const emails = draft.emails.map((e) => key(e.value)).filter(Boolean);
  const warnings: CustomerCheck["warnings"] = [];
  for (const c of scope) {
    if (c.phones.some((p) => phones.includes(p.value))) warnings.push({ code: "samePhone", name: c.name });
    if (c.emails.some((e) => emails.includes(e.value))) warnings.push({ code: "sameEmail", name: c.name });
    if (key(c.name) === key(draft.name) && key(c.address.town) && key(c.address.town) === key(draft.address.town)) warnings.push({ code: "sameNameTown", name: c.name, town: c.address.town });
  }
  return { codes, warnings, conflict };
}

/* ---------- Visit state (glossary) ---------- */
export function visitState(v: Visit, now: Date): VisitState {
  if (v.cancelled) return "cancelled";
  if (v.deletedInGoogle) return "awaiting";
  return new Date(v.end) <= now ? "held" : "planned";
}

/* ---------- Task status (ACT-2, ACT-3, ACT-4, ACC-5) ---------- */
export const TASK_TRANSITIONS: Record<TaskStatus, readonly TaskStatus[]> = {
  todo: ["progress", "done", "cancelled"],
  progress: ["done", "cancelled", "todo"],
  done: ["todo"],
  cancelled: ["todo"],
};
/** The manager may only close (done / cancelled) someone else's task. */
export function taskTransitions(task: Task, viewer: Viewer): TaskStatus[] {
  const next = [...TASK_TRANSITIONS[task.status]];
  if (task.ownerId === viewer.id) return next;
  if (viewer.role === "manager") return next.filter((s) => s === "done" || s === "cancelled");
  return [];
}
const closed = (t: Task) => t.status === "done" || t.status === "cancelled";
export const isOpen = (t: Task): boolean => !closed(t);
/** Computed, never stored (ACT-3). */
export const isLate = (t: Task, now: Date): boolean => Boolean(t.due) && !closed(t) && endOfDay(t.due as string) < now;
/** In-app reminder: due today or earlier, open, with a due date (ACT-4). */
export const isReminder = (t: Task, now: Date): boolean => Boolean(t.due) && !closed(t) && startOfDay(t.due as string) <= now;

/* ---------- Dashboard (DSH-2, DSH-3) ---------- */
export interface VisitCounts { planned: number; held: number; moved: number; cancelled: number; awaiting: number }
export function countVisits(visits: Visit[], from: Date, to: Date, now: Date): VisitCounts {
  const c: VisitCounts = { planned: 0, held: 0, moved: 0, cancelled: 0, awaiting: 0 };
  for (const v of visits) {
    const start = new Date(v.start);
    if (start < from || start > to) continue;
    const s = visitState(v, now);
    if (s === "cancelled") c.cancelled += 1;
    else if (s === "awaiting") c.awaiting += 1;
    else { c.planned += 1; if (s === "held") c.held += 1; }
    if (v.moved) c.moved += 1;
  }
  return c;
}

/* ---------- Dates: production must use Europe/Warsaw, not the browser zone ---------- */
export function startOfDay(d: string | Date): Date { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
export function endOfDay(d: string | Date): Date { const x = new Date(d); x.setHours(23, 59, 59, 999); return x; }
export function startOfWeek(d: string | Date): Date { const x = startOfDay(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; }
export function addDays(d: string | Date, n: number): Date { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

/* ---------- Polish plural rule for the catalogue (one, few, many) ---------- */
export function pluralIndex(n: number): 0 | 1 | 2 {
  const abs = Math.abs(n);
  if (abs === 1) return 0;
  const m10 = abs % 10, m100 = abs % 100;
  if (m10 >= 2 && m10 <= 4 && !(m100 >= 12 && m100 <= 14)) return 1;
  return 2;
}
