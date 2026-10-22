/* Sheets (dialogs): the decision prompt, archive, new task, note, reassignment. */
import { t, fmtDayLong, fmtTime } from "../i18n.js";
import { S, customer, note, reps, futureVisitsOf, openTasksOf } from "../store.js";
import { esc } from "../ui.js";

/* VIS-10 (delete in the app) and VIS-11 (deleted in Google) share the two answers. */
export function decisionSheet(v, origin) {
  const c = customer(v.customerId);
  return `<form method="dialog" data-form="decision" data-id="${v.id}" data-origin="${origin}">
    <div class="sheet__head"><h2 class="sheet__title">${origin === "google" ? t("decision.titleGoogle") : t("decision.titleApp")}</h2>
      <p class="t-muted"><span class="cap">${t("decision.question", { name: esc(c.name), when: `${fmtDayLong(v.start)}, ${fmtTime(v.start)}` })}</span></p></div>
    <div class="sheet__body">
      <label class="choice"><input type="radio" name="choice" value="reschedule" checked><span class="choice__title">${t("decision.reschedule")}</span><span class="choice__hint">${t("decision.rescheduleHint")}</span></label>
      <label class="choice"><input type="radio" name="choice" value="cancel"><span class="choice__title">${t("decision.cancel")}</span><span class="choice__hint">${t("decision.cancelHint")}</span></label>
    </div>
    <div class="sheet__foot">
      ${origin === "google" ? `<button class="btn" data-kind="quiet" type="button" data-do="postpone">${t("decision.later")}</button>` : `<button class="btn" data-kind="quiet" type="button" data-do="sheet-close">${t("decision.keep")}</button>`}
      <button class="btn" data-kind="primary" type="submit">${t("action.confirm")}</button></div></form>`;
}

export function archiveSheet(c) {
  const future = futureVisitsOf(c.id).length;
  const open = openTasksOf(c.id).length;
  return `<form method="dialog" data-form="archive" data-id="${c.id}">
    <div class="sheet__head"><h2 class="sheet__title">${t("customer.archiveTitle", { name: esc(c.name) })}</h2></div>
    <div class="sheet__body"><ul class="consequences">
      <li>${future ? t("customer.archiveFuture", { n: future }) : t("customer.archiveNoFuture")}</li>
      <li>${open ? t("customer.archiveTasks", { n: open }) : t("customer.archiveNoTasks")}</li>
      <li>${t("customer.archiveKeep")}</li>
      <li>${t("customer.archiveRestore")}</li></ul></div>
    <div class="sheet__foot"><button class="btn" data-kind="quiet" type="button" data-do="sheet-close">${t("action.cancel")}</button><button class="btn" data-kind="destructive" type="submit">${t("customer.archive")}</button></div></form>`;
}

export function taskSheet(noteId) {
  return `<form method="dialog" data-form="task" data-note="${noteId}">
    <div class="sheet__head"><h2 class="sheet__title">${t("tasks.newTitle")}</h2><p class="t-muted">${t("tasks.newSub")}</p></div>
    <div class="sheet__body">
      <div class="field"><label class="field__label" for="tk-text">${t("tasks.desc")}</label><input class="input" id="tk-text" name="text" required autofocus></div>
      <div class="field"><label class="field__label" for="tk-due">${t("tasks.dueOpt")} <small>(${t("form.optional")})</small></label><input class="input" id="tk-due" name="due" type="date"><span class="field__hint">${t("tasks.dueHint")}</span></div>
    </div>
    <div class="sheet__foot"><button class="btn" data-kind="quiet" type="button" data-do="sheet-close">${t("action.cancel")}</button><button class="btn" data-kind="primary" type="submit">${t("tasks.add")}</button></div></form>`;
}

export function noteSheet({ noteId, customerId }) {
  const n = noteId ? note(noteId) : null;
  return `<form method="dialog" data-form="note-sheet" data-note="${noteId ?? ""}" data-customer="${customerId ?? ""}">
    <div class="sheet__head"><h2 class="sheet__title">${n ? t("note.editTitle") : t("note.managerTitle")}</h2>${n ? "" : `<p class="t-muted">${t("note.managerSub")}</p>`}</div>
    <div class="sheet__body"><div class="field"><label class="field__label" for="nt-text">${t("note.text")}</label><textarea class="textarea" id="nt-text" name="text" required autofocus>${n ? esc(n.text) : ""}</textarea></div></div>
    <div class="sheet__foot"><button class="btn" data-kind="quiet" type="button" data-do="sheet-close">${t("action.cancel")}</button><button class="btn" data-kind="primary" type="submit">${n ? t("note.save") : t("note.add")}</button></div></form>`;
}

export function reassignSheet(ids) {
  const future = ids.reduce((s, id) => s + futureVisitsOf(id).length, 0);
  const open = ids.reduce((s, id) => s + openTasksOf(id).length, 0);
  return `<form method="dialog" data-form="reassign">
    <div class="sheet__head"><h2 class="sheet__title">${t("team.sheetTitle", { n: ids.length })}</h2></div>
    <div class="sheet__body">
      <div class="field"><label class="field__label" for="rs-to">${t("team.newOwner")}</label><select class="select" id="rs-to" name="to">${reps().map((r) => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select></div>
      <ul class="consequences"><li>${t("team.moveVisits", { n: future })}</li><li>${t("team.moveTasks", { n: open })}</li><li>${t("team.keepPast")}</li></ul></div>
    <div class="sheet__foot"><button class="btn" data-kind="quiet" type="button" data-do="sheet-close">${t("action.cancel")}</button><button class="btn" data-kind="primary" type="submit">${t("team.submit")}</button></div></form>`;
}
