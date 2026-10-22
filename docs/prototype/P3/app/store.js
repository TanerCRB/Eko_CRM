/*
 * Eko_CRM prototype P3 — in-memory store: state, queries, mutations.
 * The mutations play the server: they enforce what the brief puts on the API (ACC-4, ACC-5,
 * CUS-6, CUS-9, CUS-10, VIS-9 to VIS-13, ACT-1, ACT-2) and return plain results; views turn
 * results into words. Nothing here touches the DOM.
 */
import { makeSeed } from "../data/seed.js";
import * as R from "./rules.js";

export let S = null;

export function reset(keepMeId = null) {
  const seed = makeSeed();
  S = {
    ...seed,
    meId: keepMeId,
    postponed: false,
    ui: {
      q: "", owner: "all", archived: false, visitsTab: "upcoming", tasksTab: "open", period: "week",
      teamOwner: "all", weekOffset: 0, selectedDay: R.isoDate(seed.NOW), draft: null, lanesRep: null,
    },
    selected: new Set(),
  };
}
reset();

const uid = (p) => p + Math.random().toString(36).slice(2, 8);

/* ---------- Queries ---------- */
export const me = () => S.users.find((u) => u.id === S.meId) ?? null;
export const isManager = () => me()?.role === "manager";
export const user = (id) => S.users.find((u) => u.id === id);
export const userName = (id) => user(id)?.name ?? "";
export const customer = (id) => S.customers.find((c) => c.id === id);
export const visit = (id) => S.visits.find((v) => v.id === id);
export const note = (id) => S.notes.find((n) => n.id === id);
export const task = (id) => S.tasks.find((a) => a.id === id);
export const reps = () => S.users.filter((u) => u.role === "rep");
export const stateOf = (v) => R.visitState(v, S.NOW);

/* ACC-4: what the viewer may read. A rep gets nothing about another rep's record. */
export const canSeeCustomer = (c) => Boolean(c) && (isManager() || c.ownerId === S.meId);
export const canSeeVisit = (v) => Boolean(v) && (isManager() || v.ownerId === S.meId);
export const visibleCustomers = () => S.customers.filter(canSeeCustomer);
export const visibleVisits = () => S.visits.filter(canSeeVisit);
export const visibleTasks = () => S.tasks.filter((a) => isManager() || a.ownerId === S.meId);
export const reminders = () => S.tasks.filter((a) => a.ownerId === S.meId && R.isReminder(a, S.NOW));
/* VIS-11: only the owner ever sees the prompt. */
export const awaiting = () => S.visits.filter((v) => v.ownerId === S.meId && stateOf(v) === "awaiting");
export const pendingSync = (ownerId) => S.visits.filter((v) => v.ownerId === ownerId && v.unsynced);
export const googleLinked = () => me()?.google === "linked";
export const customerVisits = (cid) => S.visits.filter((v) => v.customerId === cid && canSeeVisit(v));
export const customerNotes = (cid) => S.notes.filter((n) => n.customerId === cid);
export const noteTasks = (nid) => S.tasks.filter((a) => a.noteId === nid);
export const openTasksOf = (cid) => S.tasks.filter((a) => a.customerId === cid && R.isOpen(a));
export const futureVisitsOf = (cid) => S.visits.filter((v) => v.customerId === cid && new Date(v.start) > S.NOW && !v.cancelled);

/* ---------- Session ---------- */
export function login(id) { S.meId = id; S.postponed = false; S.selected.clear(); S.ui.owner = "all"; S.ui.draft = null; S.ui.weekOffset = 0; S.ui.selectedDay = R.isoDate(S.NOW); }
export function logout() { S.meId = null; S.ui.draft = null; }

/* ---------- Customers ---------- */
export function emptyDraft() {
  return { id: null, ownerId: S.meId, name: "", nip: "", address: { street: "", postalCode: "", town: "", voivodeship: "", county: "", country: R.POLAND }, phones: [{ value: "", who: "", primary: true }], emails: [] };
}
export function checkDraft(draft) {
  return R.checkCustomer(draft, S.customers.filter((c) => c.id !== draft.id), me());
}
/** @returns {{ok:true, id:string, created:boolean} | {ok:false, reason:"fields"|"conflict"}} */
export function saveCustomer(draft) {
  const res = checkDraft(draft);
  if (Object.keys(res.codes).length) return { ok: false, reason: "fields" };
  if (res.conflict) return { ok: false, reason: "conflict" };
  const clean = {
    ...draft,
    nip: R.checkNip(draft.nip, draft.address.country).value,
    phones: draft.phones.filter((p) => p.value).map((p) => ({ ...p, value: R.normalizePhone(p.value) })),
    emails: draft.emails.filter((e) => e.value).map((e) => ({ ...e, value: R.checkEmail(e.value).value })),
  };
  if (clean.id) { Object.assign(customer(clean.id), clean); return { ok: true, id: clean.id, created: false }; }
  clean.id = uid("c"); clean.archived = false;
  S.customers.push(clean);
  return { ok: true, id: clean.id, created: true };
}
/* CUS-9: future visits cancelled without the prompt, open tasks cancelled, nothing else changes. */
export function archiveCustomer(id) {
  const c = customer(id);
  c.archived = true;
  futureVisitsOf(id).forEach((v) => { v.cancelled = true; v.deletedInGoogle = false; });
  openTasksOf(id).forEach((a) => { a.status = "cancelled"; a.log.push({ by: S.meId, to: "cancelled" }); });
}
export function restoreCustomer(id) { customer(id).archived = false; }
/* CUS-10: the customer, its future visits and open tasks move; past visits and notes stay. */
export function reassign(ids, toId) {
  ids.forEach((cid) => {
    customer(cid).ownerId = toId;
    futureVisitsOf(cid).forEach((v) => { v.ownerId = toId; });
    openTasksOf(cid).forEach((a) => { a.ownerId = toId; });
  });
  S.selected.clear();
}

/* ---------- Visits ---------- */
export function planVisit({ customerId, start, end, place }) {
  const c = customer(customerId);
  if (!c || c.ownerId !== S.meId || c.archived) return { ok: false }; // ACC-7
  const v = { id: uid("v"), customerId, ownerId: S.meId, start, end, cancelled: false, deletedInGoogle: false, moved: false, unsynced: !googleLinked(), place: place ?? "" };
  S.visits.push(v);
  return { ok: true, id: v.id, unsynced: v.unsynced };
}
export function moveVisit(id, { start, end, place }) {
  const v = visit(id);
  if (!v || v.ownerId !== S.meId) return { ok: false };
  if (new Date(v.start).getTime() !== new Date(start).getTime()) v.moved = true; // VIS-9: start only
  Object.assign(v, { start, end, place: place ?? "", deletedInGoogle: false, unsynced: v.unsynced || !googleLinked() });
  return { ok: true, unsynced: v.unsynced };
}
/* VIS-10 / VIS-11: the two answers, from the app or after a deletion in Google. */
export function decideVisit(id, choice) {
  const v = visit(id);
  if (!v || v.ownerId !== S.meId) return { ok: false };
  if (choice === "cancel") { v.cancelled = true; v.deletedInGoogle = false; return { ok: true, cancelled: true }; }
  v.moved = true; v.deletedInGoogle = false; // VIS-11: rescheduling from the prompt counts as moved
  return { ok: true, cancelled: false };
}
export function markNotHeld(id) { const v = visit(id); if (v && v.ownerId === S.meId) v.cancelled = true; } // VIS-13
export function postponeDecision() { S.postponed = true; }

/* ---------- Notes and tasks ---------- */
export function addNote({ visitId, customerId, text }) {
  const n = { id: uid("n"), visitId: visitId ?? null, customerId, authorId: S.meId, at: S.NOW.toISOString(), text };
  S.notes.push(n);
  return n;
}
export function editNote(id, text) { const n = note(id); if (n && n.authorId === S.meId) n.text = text; } // NOT-1, PRH-6
/* ACT-1: owner = note's author; a manager's task goes to the customer's owner. */
export function addTask({ noteId, text, due }) {
  const n = note(noteId);
  if (!n || n.authorId !== S.meId) return null;
  const c = customer(n.customerId);
  const ownerId = isManager() ? c.ownerId : n.authorId;
  const a = { id: uid("a"), noteId, customerId: c.id, ownerId, authorId: S.meId, text, due: due || null, status: "todo", log: [] };
  S.tasks.push(a);
  return a;
}
export function setTaskStatus(id, status) {
  const a = task(id);
  if (!a || !R.taskTransitions(a, me()).includes(status)) return false; // ACT-2, ACC-5
  a.status = status; a.log.push({ by: S.meId, to: status });
  return true;
}

/* ---------- Google (VIS-7, VIS-8) ---------- */
export function connectGoogle() {
  const u = me(); u.google = "linked";
  const pending = pendingSync(u.id);
  pending.forEach((v) => { v.unsynced = false; });
  return pending.length;
}
export function disconnectGoogle() { me().google = "none"; }

/* ---------- Demo switches (not product) ---------- */
export function simulateGoogleDelete() {
  const v = S.visits.filter((x) => x.ownerId === S.meId && stateOf(x) === "planned").sort((a, b) => a.start.localeCompare(b.start))[0];
  if (!v) return null;
  v.deletedInGoogle = true; S.postponed = false;
  return v;
}
export function simulateExpire() { me().google = "expired"; }
