/*
 * Eko_CRM prototype P3 — domain rules (pure functions, no DOM, no strings for people).
 * Every check returns a code (e.g. "nipChecksum"); the view turns codes into words through the
 * string catalogue, so rules stay language-free. The server stays the authority (CUS-3, CUS-6,
 * ACT-2, ACC-4); these give the form instant feedback. Mirrored as handoff/rules.ts.
 * Identifiers refer to docs/product/project-brief.md.
 */

export const POLAND = "Polska";

export const VOIVODESHIPS = [
  "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "łódzkie", "małopolskie",
  "mazowieckie", "opolskie", "podkarpackie", "podlaskie", "pomorskie", "śląskie",
  "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie",
];

/** Sample of the TERYT county register; production loads the full list (380) from the API. */
export const COUNTIES = {
  "kujawsko-pomorskie": ["aleksandrowski", "brodnicki", "bydgoski", "chełmiński", "golubsko-dobrzyński", "grudziądzki", "inowrocławski", "lipnowski", "mogileński", "nakielski", "radziejowski", "rypiński", "sępoleński", "świecki", "toruński", "tucholski", "wąbrzeski", "włocławski", "żniński"],
  "mazowieckie": ["ciechanowski", "gostyniński", "mławski", "płocki", "płoński", "sierpecki", "sochaczewski", "żuromiński"],
  "łódzkie": ["kutnowski", "łęczycki", "łowicki", "poddębicki", "zgierski"],
  "wielkopolskie": ["gnieźnieński", "kolski", "koniński", "słupecki", "wrzesiński"],
  "pomorskie": ["kwidzyński", "malborski", "starogardzki", "tczewski"],
};

/* ---------- NIP (CUS-5) ---------- */
const NIP_WEIGHTS = [6, 5, 7, 2, 3, 4, 5, 6, 7];
export const normalizeNip = (raw) => String(raw ?? "").replace(/^\s*PL/i, "").replace(/[\s-]/g, "");
export function nipCheckDigit(nine) {
  const sum = NIP_WEIGHTS.reduce((acc, w, i) => acc + w * Number(nine[i]), 0) % 11;
  return sum === 10 ? null : sum;
}
/** @returns {{ok:true, value:string} | {ok:false, code:string}} */
export function checkNip(raw, country) {
  const trimmed = String(raw ?? "").trim();
  if (!trimmed) return { ok: true, value: "" };
  if (country !== POLAND) return { ok: true, value: trimmed };
  const v = normalizeNip(trimmed);
  if (!/^\d{10}$/.test(v)) return { ok: false, code: "nipDigits" };
  if (nipCheckDigit(v) !== Number(v[9])) return { ok: false, code: "nipChecksum" };
  return { ok: true, value: v };
}
export const formatNip = (v) => (v && v.length === 10 ? `${v.slice(0, 3)}-${v.slice(3, 6)}-${v.slice(6, 8)}-${v.slice(8)}` : v || "");

/* ---------- Address (CUS-3, CUS-4) ---------- */
export function checkAddress(a) {
  const codes = {};
  if (a.country !== POLAND) return codes;
  if (a.postalCode && !/^\d{2}-\d{3}$/.test(a.postalCode)) codes.postalCode = "postal";
  if (a.voivodeship && !VOIVODESHIPS.includes(a.voivodeship)) codes.voivodeship = "voivodeship";
  if (a.county) {
    if (!a.voivodeship) codes.county = "countyNoVoivodeship";
    else if (COUNTIES[a.voivodeship] && !COUNTIES[a.voivodeship].includes(a.county)) codes.county = "countyMismatch";
  }
  return codes;
}
export const addressLine = (a) => [a.street, [a.postalCode, a.town].filter(Boolean).join(" "), a.country !== POLAND ? a.country : ""].filter(Boolean).join(", ");

/* ---------- Contacts (CUS-8) ---------- */
export function normalizePhone(raw) {
  let v = String(raw ?? "").replace(/[\s()./-]/g, "");
  if (!v) return "";
  if (v.startsWith("00")) v = "+" + v.slice(2);
  if (!v.startsWith("+")) v = "+48" + v;
  return v;
}
export const checkPhone = (raw) => { const v = normalizePhone(raw); return /^\+\d{8,15}$/.test(v) ? { ok: true, value: v } : { ok: false, code: "phone" }; };
export const formatPhone = (v) => { const m = /^\+48(\d{3})(\d{3})(\d{3})$/.exec(v ?? ""); return m ? `+48 ${m[1]} ${m[2]} ${m[3]}` : v ?? ""; };
export const checkEmail = (raw) => { const v = String(raw ?? "").trim(); return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) ? { ok: true, value: v.toLowerCase() } : { ok: false, code: "email" }; };

/* ---------- Customer draft (CUS-2, CUS-6, CUS-7, ACC-8) ---------- */
/**
 * @param draft   the form's draft
 * @param others  every other customer the server knows (uniqueness is company-wide)
 * @param viewer  {id, role}
 * @returns {{codes:object, warnings:Array<{code:string, name:string, town?:string}>, conflict:null|{code:string, customerId:string|null}}}
 */
export function checkCustomer(draft, others, viewer) {
  const codes = {};
  if (!draft.name?.trim()) codes.name = "nameRequired";
  if (!draft.address.country) codes.country = "countryRequired";
  Object.assign(codes, checkAddress(draft.address));
  const nip = checkNip(draft.nip, draft.address.country);
  if (!nip.ok) codes.nip = nip.code;
  draft.phones.forEach((p, i) => { if (p.value && !checkPhone(p.value).ok) codes[`phone${i}`] = "phone"; });
  draft.emails.forEach((e, i) => { if (e.value && !checkEmail(e.value).ok) codes[`email${i}`] = "email"; });

  let conflict = null;
  if (nip.ok && nip.value && draft.address.country === POLAND) {
    const hit = others.find((c) => c.nip === nip.value);
    // ACC-8: a rep learns nothing about the other customer or its owner.
    if (hit) conflict = viewer.role === "manager" ? { code: "nipManager", customerId: hit.id } : { code: "nipRep", customerId: null };
  }

  // CUS-7: duplicates are warned within the viewer's scope only.
  const scope = viewer.role === "manager" ? others : others.filter((c) => c.ownerId === viewer.id);
  const key = (s) => String(s ?? "").trim().toLowerCase();
  const phones = draft.phones.map((p) => normalizePhone(p.value)).filter(Boolean);
  const emails = draft.emails.map((e) => key(e.value)).filter(Boolean);
  const warnings = [];
  for (const c of scope) {
    if (c.phones.some((p) => phones.includes(p.value))) warnings.push({ code: "samePhone", name: c.name });
    if (c.emails.some((e) => emails.includes(e.value))) warnings.push({ code: "sameEmail", name: c.name });
    if (key(c.name) === key(draft.name) && key(c.address.town) && key(c.address.town) === key(draft.address.town)) warnings.push({ code: "sameNameTown", name: c.name, town: c.address.town });
  }
  return { codes, warnings, conflict };
}

/* ---------- Visit state (glossary, VIS-*) ---------- */
/** Derived every time it is read; only `cancelled` and `deletedInGoogle` are stored. */
export function visitState(v, now) {
  if (v.cancelled) return "cancelled";
  if (v.deletedInGoogle) return "awaiting";
  return new Date(v.end) <= now ? "held" : "planned";
}

/* ---------- Task status (ACT-2, ACT-3, ACT-4, ACC-5) ---------- */
export const TASK_TRANSITIONS = {
  todo: ["progress", "done", "cancelled"],
  progress: ["done", "cancelled", "todo"],
  done: ["todo"],
  cancelled: ["todo"],
};
export function taskTransitions(task, viewer) {
  const next = TASK_TRANSITIONS[task.status] ?? [];
  if (task.ownerId === viewer.id) return next;
  if (viewer.role === "manager") return next.filter((s) => s === "done" || s === "cancelled");
  return [];
}
const closed = (task) => task.status === "done" || task.status === "cancelled";
export const isLate = (task, now) => Boolean(task.due) && !closed(task) && endOfDay(task.due) < now;
export const isReminder = (task, now) => Boolean(task.due) && !closed(task) && startOfDay(task.due) <= now;
export const isOpen = (task) => !closed(task);

/* ---------- Dashboard (DSH-2, DSH-3) ---------- */
export function countVisits(visits, from, to, now) {
  const c = { planned: 0, held: 0, moved: 0, cancelled: 0, awaiting: 0 };
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

/* ---------- Dates (prototype: browser zone; production: Europe/Warsaw) ---------- */
export function startOfDay(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
export function endOfDay(d) { const x = new Date(d); x.setHours(23, 59, 59, 999); return x; }
export function startOfWeek(d) { const x = startOfDay(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; }
export function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
export const sameDay = (a, b) => startOfDay(a).getTime() === startOfDay(b).getTime();
export const isoDate = (d) => { const x = new Date(d); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`; };
export function periodRange(preset, now) {
  const from = startOfDay(now);
  let to = endOfDay(now);
  if (preset === "week") { from.setTime(startOfWeek(now).getTime()); to = endOfDay(addDays(from, 6)); }
  if (preset === "month") { from.setDate(1); to = endOfDay(new Date(from.getFullYear(), from.getMonth() + 1, 0)); }
  if (preset === "quarter") { from.setMonth(Math.floor(from.getMonth() / 3) * 3, 1); to = endOfDay(new Date(from.getFullYear(), from.getMonth() + 3, 0)); }
  if (preset === "year") { from.setMonth(0, 1); to = endOfDay(new Date(from.getFullYear(), 11, 31)); }
  return [from, to];
}
