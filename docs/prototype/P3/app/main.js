/*
 * Eko_CRM prototype P3 — boot, router, event wiring.
 * Hash routes with Polish paths (#/tydzien, #/klienci/:id, …). One render per state change;
 * the customer form validates in place so typing never loses focus.
 */
import { t, fmtTime } from "./i18n.js";
import * as R from "./rules.js";
import * as store from "./store.js";
import { S } from "./store.js";
import { toast, openSheet, closeSheet, eventPreview, esc } from "./ui.js";
import { menuSheet } from "./views/shell.js";
import { decisionSheet, archiveSheet, taskSheet, noteSheet, reassignSheet } from "./views/sheets.js";
import { weekView } from "./views/week.js";
import { customersView, customerView, customerFormView, bindDraft, validateForm } from "./views/customers.js";
import { visitsView, visitView, visitFormView } from "./views/visits.js";
import { tasksView, teamView, dashboardView, accountView, loginView } from "./views/misc.js";

const root = document.getElementById("app");
const go = (hash) => { location.hash = hash; };

function route() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, qs] = h.split("?");
  return { parts: path.split("/").filter(Boolean), query: new URLSearchParams(qs ?? "") };
}

export function render() {
  if (!S.meId) { root.innerHTML = loginView(); return; }
  const { parts, query } = route();
  const [a, b, c] = parts;
  let html;
  if (a === "klienci" && b === "nowy") html = customerFormView(null);
  else if (a === "klienci" && b && c === "edycja") html = customerFormView(b);
  else if (a === "klienci" && b) html = customerView(b);
  else if (a === "klienci") html = customersView();
  else if (a === "wizyty" && b === "nowa") html = visitFormView(null, query.get("klient"));
  else if (a === "wizyty" && b && c === "edycja") html = visitFormView(b);
  else if (a === "wizyty" && b) html = visitView(b);
  else if (a === "wizyty") html = visitsView();
  else if (a === "zadania") html = tasksView();
  else if (a === "zespol") html = teamView();
  else if (a === "pulpit") html = dashboardView();
  else if (a === "konto") html = accountView();
  else html = weekView();
  root.innerHTML = html;
  const onForm = a === "klienci" && (b === "nowy" || c === "edycja");
  if (!onForm) S.ui.draft = null;
  else { const f = root.querySelector('form[data-form="customer"]'); if (f) validateForm(f, false); }
  const active = parts[0] ?? "tydzien";
  root.dataset.active = active;
}

/* VIS-11: after login the prompt opens once; "later" leaves the bar on every page. */
function promptIfNeeded() {
  const aw = store.awaiting();
  if (S.meId && aw.length && !S.postponed && !document.getElementById("sheet").open) openSheet(decisionSheet(aw[0], "google"), "decision");
}

/* ---------- Click actions ---------- */
const actions = {
  login(el) { store.login(el.dataset.id); document.getElementById("demo-pop")?.hidePopover?.(); if (!location.hash || location.hash.includes("logowanie")) go("#/tydzien"); render(); promptIfNeeded(); },
  logout(el, e) { e.preventDefault(); closeSheet(); store.logout(); go("#/logowanie"); render(); },
  forgot(el, e) { e.preventDefault(); toast(t("login.forgotDemo")); },
  menu() { openSheet(menuSheet(root.dataset.active)); },
  "menu-go"() { closeSheet(); },
  "sheet-close"() { closeSheet(); },
  theme() { const r = document.documentElement; const dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; r.dataset.theme = dark ? "light" : "dark"; },
  reset() { store.reset(S.meId); document.getElementById("demo-pop")?.hidePopover?.(); render(); toast(t("demo.resetDone")); },
  "sim-delete"() {
    const v = store.simulateGoogleDelete();
    document.getElementById("demo-pop")?.hidePopover?.();
    if (!v) return toast(t("demo.noPlanned"));
    render(); toast(t("demo.simDeleteDone", { name: t("visitForm.eventTitle", { name: store.customer(v.customerId).name }) })); promptIfNeeded();
  },
  "sim-expire"() { store.simulateExpire(); document.getElementById("demo-pop")?.hidePopover?.(); render(); toast(t("demo.simExpireDone")); },
  tab(el) { const k = el.dataset.key; S.ui[k] = k === "archived" ? Boolean(el.dataset.value) : el.dataset.value; render(); },
  "week-shift"(el) { const n = Number(el.dataset.arg); S.ui.weekOffset = n === 0 ? 0 : S.ui.weekOffset + n; S.ui.lanesRep = null; render(); },
  "pick-day"(el) { S.ui.selectedDay = el.dataset.arg; render(); },
  "lanes-pick"(el, e) { e.preventDefault(); S.ui.lanesRep = el.dataset.rep; S.ui.selectedDay = el.dataset.arg; render(); },
  decide(el) { openSheet(decisionSheet(store.visit(el.dataset.id), "google"), "decision"); },
  postpone() { store.postponeDecision(); closeSheet(); toast(t("decision.postponed")); },
  "visit-delete"(el) { openSheet(decisionSheet(store.visit(el.dataset.id), "app"), "decision"); },
  "not-held"(el) { store.markNotHeld(el.dataset.id); render(); toast(t("visit.notHeldDone")); },
  archive(el) { openSheet(archiveSheet(store.customer(el.dataset.id))); },
  restore(el) { store.restoreCustomer(el.dataset.id); render(); toast(t("customer.restored")); },
  copy(el) { navigator.clipboard?.writeText(el.dataset.arg).then(() => toast(t("customer.copied")), () => toast(el.dataset.arg)); },
  "task-new"(el) { openSheet(taskSheet(el.dataset.id)); },
  "note-edit"(el) { openSheet(noteSheet({ noteId: el.dataset.id })); },
  "note-manager"(el) { openSheet(noteSheet({ customerId: el.dataset.id })); },
  "contact-add"(el) { const form = el.closest("form"); bindDraft(form); const list = el.dataset.kindList; S.ui.draft[list].push({ value: "", who: "", primary: list === "phones" && !S.ui.draft.phones.length }); render(); },
  "contact-remove"(el) { const form = el.closest("form"); bindDraft(form); S.ui.draft[el.dataset.kindList].splice(Number(el.dataset.index), 1); render(); },
  reassign() { openSheet(reassignSheet([...S.selected])); },
  "google-connect"() { const n = store.connectGoogle(); render(); toast(n ? t("account.connectedSynced", { n }) : t("account.connected")); },
  "google-disconnect"() { store.disconnectGoogle(); render(); toast(t("account.unlinked")); },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-do]");
  if (!el) return;
  const fn = actions[el.dataset.do];
  if (fn) fn(el, e);
});

/* ---------- Forms ---------- */
const forms = {
  login() { toast(t("login.demoSubmit")); },
  customer(form) {
    const res = validateForm(form, true);
    if (Object.keys(res.codes).length || res.conflict) {
      form.querySelector('[aria-invalid="true"]')?.focus();
      toast(res.conflict ? t("form.nipBlocked") : t("form.fixFields"));
      return;
    }
    const out = store.saveCustomer(S.ui.draft);
    if (!out.ok) return toast(t("form.fixFields"));
    S.ui.draft = null;
    go(`#/klienci/${out.id}`);
    toast(out.created ? t("form.savedNew") : t("form.savedEdit"));
  },
  visit(form, fd) {
    const id = form.dataset.id;
    const customerId = id ? store.visit(id).customerId : fd.get("customerId");
    if (!customerId) { toast(t("visitForm.pickCustomerToast")); form.querySelector("#v-c").focus(); return; }
    const start = new Date(`${fd.get("date")}T${fd.get("time")}:00`);
    if (Number.isNaN(start.getTime())) return toast(t("visitForm.pickTimeToast"));
    const end = new Date(start.getTime() + Number(fd.get("dur")) * 60000);
    const payload = { customerId, start: start.toISOString(), end: end.toISOString(), place: fd.get("place") };
    const out = id ? store.moveVisit(id, payload) : store.planVisit(payload);
    if (!out.ok) return;
    go(`#/wizyty/${id || out.id}`);
    toast(t(id ? (out.unsynced ? "visitForm.movedUnsync" : "visitForm.movedSync") : (out.unsynced ? "visitForm.plannedUnsync" : "visitForm.plannedSync")));
  },
  decision(form, fd) {
    const id = form.dataset.id;
    closeSheet();
    const out = store.decideVisit(id, fd.get("choice"));
    if (!out.ok) return;
    if (out.cancelled) { render(); toast(t("decision.cancelled")); }
    else { go(`#/wizyty/${id}/edycja`); toast(t("decision.pickNew")); }
  },
  archive(form) { store.archiveCustomer(form.dataset.id); closeSheet(); render(); toast(t("customer.archived")); },
  note(form, fd) {
    const text = String(fd.get("text") ?? "").trim();
    if (!text) return toast(t("note.empty"));
    const v = store.visit(form.dataset.visit);
    store.addNote({ visitId: v.id, customerId: v.customerId, text });
    render(); toast(t("note.added"));
  },
  "note-sheet"(form, fd) {
    const text = String(fd.get("text") ?? "").trim();
    if (!text) return;
    if (form.dataset.note) store.editNote(form.dataset.note, text);
    else store.addNote({ visitId: null, customerId: form.dataset.customer, text });
    closeSheet(); render(); toast(form.dataset.note ? t("note.saved") : t("note.added"));
  },
  task(form, fd) {
    const text = String(fd.get("text") ?? "").trim();
    if (!text) { form.querySelector("#tk-text").setAttribute("aria-invalid", "true"); return; }
    store.addTask({ noteId: form.dataset.note, text, due: fd.get("due") });
    closeSheet(); render(); toast(t("tasks.added"));
  },
  reassign(form, fd) {
    const ids = [...S.selected];
    const to = fd.get("to");
    store.reassign(ids, to);
    closeSheet(); render(); toast(t("team.done", { n: ids.length, name: store.userName(to) }));
  },
};

document.addEventListener("submit", (e) => {
  const form = e.target;
  const fn = forms[form.dataset.form];
  if (!fn) return;
  e.preventDefault();
  fn(form, new FormData(form));
});

/* ---------- Change and input ---------- */
document.addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.taskStatus) {
    const to = el.value;
    if (!to) return;
    if (!store.setTaskStatus(el.dataset.taskStatus, to)) return toast(t("tasks.notAllowed"));
    render(); toast(t("tasks.statusChanged", { status: t("status." + to) }));
    return;
  }
  if (el.dataset.select) { if (el.checked) S.selected.add(el.dataset.select); else S.selected.delete(el.dataset.select); render(); return; }
  if (el.dataset.filter && el.dataset.filter !== "q") { S.ui[el.dataset.filter] = el.value; render(); return; }
  const cform = el.closest('form[data-form="customer"]');
  if (cform) {
    el.dataset.touched = "1";
    if (el.hasAttribute("data-rerender")) {
      bindDraft(cform);
      if (el.dataset.bind === "address.voivodeship") S.ui.draft.address.county = "";
      render();
    } else validateForm(cform, false);
    return;
  }
  const vform = el.closest('form[data-form="visit"]');
  if (vform && (el.name === "customerId" || el.name === "place")) {
    document.querySelector('[data-slot="event"]').innerHTML = eventPreview(vform.querySelector("#v-c").value, vform.querySelector("#v-p").value, store.googleLinked());
  }
});

document.addEventListener("input", (e) => {
  const el = e.target;
  if (el.dataset.filter === "q") {
    S.ui.q = el.value;
    const pos = el.selectionStart;
    render();
    const again = document.querySelector('[data-filter="q"]');
    again.focus(); again.setSelectionRange(pos, pos);
    return;
  }
  const cform = el.closest('form[data-form="customer"]');
  if (cform) validateForm(cform, false);
});
document.addEventListener("focusout", (e) => {
  const cform = e.target.closest?.('form[data-form="customer"]');
  if (cform && e.target.matches(".input")) { e.target.dataset.touched = "1"; validateForm(cform, false); }
});

window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });
render();
