/* Visits: list, detail, plan / move form. */
import { t, fmtTime, fmtDayLong } from "../i18n.js";
import { icon } from "../icons.js";
import * as R from "../rules.js";
import { S, me, isManager, visibleVisits, visit, customer, canSeeVisit, userName, stateOf, googleLinked } from "../store.js";
import { shell } from "./shell.js";
import { notFound } from "./customers.js";
import { esc, stateChip, flags, noteBlock, visitRow, section, empty, eventPreview } from "../ui.js";

export function visitsView() {
  const tab = S.ui.visitsTab;
  const all = visibleVisits();
  const list = (tab === "upcoming" ? all.filter((v) => new Date(v.end) > S.NOW && !v.cancelled) : all.filter((v) => new Date(v.end) <= S.NOW || v.cancelled))
    .sort((a, b) => (tab === "upcoming" ? a.start.localeCompare(b.start) : b.start.localeCompare(a.start)));
  return shell("wizyty", `
    <div class="page__head"><div class="page__titles"><h1 class="page__title">${t("visits.title")}</h1><p class="page__sub">${isManager() ? t("visits.subManager") : t("visits.subRep")}</p></div>
      ${isManager() ? "" : `<a class="btn" data-kind="primary" href="#/wizyty/nowa">${icon("plus")}${t("week.plan")}</a>`}</div>
    <div class="tabs" role="group"><button class="tabs__tab" data-do="tab" data-key="visitsTab" data-value="upcoming" aria-pressed="${tab === "upcoming"}">${t("visits.upcoming")}</button><button class="tabs__tab" data-do="tab" data-key="visitsTab" data-value="past" aria-pressed="${tab === "past"}">${t("visits.past")}</button></div>
    ${list.length ? `<ul class="rows">${list.map(visitRow).join("")}</ul>` : empty(t("visits.none"))}`);
}

export function visitView(id) {
  const v = visit(id);
  if (!canSeeVisit(v)) return notFound("wizyty");
  const c = customer(v.customerId);
  const st = stateOf(v);
  const own = v.ownerId === S.meId;
  const notes = S.notes.filter((n) => n.visitId === v.id).sort((a, b) => b.at.localeCompare(a.at));
  return shell("wizyty", `
    <a class="crumb" href="#/wizyty">${icon("back", "small")}${t("visits.title")}</a>
    <div class="page__head"><div class="page__titles">
      <div class="btn-row">${stateChip(st)}${flags(v)}</div>
      <h1 class="page__title">${esc(c.name)}</h1>
      <p class="page__sub"><span class="cap">${fmtDayLong(v.start)}</span>, ${fmtTime(v.start)}–${fmtTime(v.end)}${own ? "" : ` · ${esc(userName(v.ownerId))}`}</p></div>
      ${own && st !== "cancelled" ? `<div class="btn-row">
        ${st === "awaiting" ? `<button class="btn" data-kind="primary" data-do="decide" data-id="${v.id}">${t("visit.decide")}</button>` : `<a class="btn" href="#/wizyty/${v.id}/edycja">${icon("moved")}${t("visit.move")}</a>`}
        ${st === "held" ? `<button class="btn" data-do="not-held" data-id="${v.id}">${t("visit.notHeld")}</button>` : ""}
        ${st === "planned" ? `<button class="btn" data-kind="quiet" data-do="visit-delete" data-id="${v.id}">${t("visit.delete")}</button>` : ""}
      </div>` : ""}</div>
    ${!own && isManager() ? `<p class="t-muted measure">${t("visit.ownerOnly", { name: esc(userName(v.ownerId)) })}</p>` : ""}
    <div class="two-col">
      ${section(t("visit.notesTitle"), `
        ${notes.map(noteBlock).join("") || `<p class="t-muted">${t("visit.noNotes")}</p>`}
        ${own || isManager() ? `<form class="stack" data-gap="small" data-form="note" data-visit="${v.id}" style="padding-top:12px">
          <div class="field"><label class="field__label" for="n-text">${t("visit.newNote")}</label><textarea class="textarea" id="n-text" name="text" placeholder="${t("visit.notePlaceholder")}"></textarea></div>
          <div><button class="btn" data-kind="primary" type="submit">${t("visit.addNote")}</button></div></form>` : ""}`)}
      <div class="stack">
        ${section(t("visit.googleTitle"), st === "awaiting" ? `<p>${t("visit.googleDeleted")}</p>` : st === "cancelled" ? `<p class="t-muted">${t("visit.googleCancelled")}</p>` : eventPreview(c.id, v.place, !v.unsynced))}
        ${section(t("visit.customerTitle"), `<div class="stack" data-gap="small"><a class="t-name t-h3" href="#/klienci/${c.id}" style="text-decoration:none;color:inherit">${esc(c.name)}</a><span class="t-meta">${esc(R.addressLine(c.address))}</span>
          ${c.phones[0] ? `<div><a class="btn" data-size="small" href="tel:${c.phones[0].value}">${icon("phone", "small")}${R.formatPhone(c.phones[0].value)}</a></div>` : ""}</div>`)}
      </div>
    </div>`);
}

export function visitFormView(id, preCustomer) {
  const v = id ? visit(id) : null;
  if (id && (!v || v.ownerId !== S.meId)) return notFound("wizyty");
  if (!id && isManager()) return shell("wizyty", empty(t("visits.managerCannotTitle"), t("visits.managerCannotBody"), `<a class="btn" href="#/wizyty">${t("visits.backToVisits")}</a>`));
  const mine = S.customers.filter((c) => c.ownerId === S.meId && !c.archived).sort((a, b) => a.name.localeCompare(b.name, "pl"));
  const selId = v ? v.customerId : preCustomer ?? "";
  const start = v ? new Date(v.start) : (() => { const d = R.addDays(S.NOW, 1); d.setHours(9, 0, 0, 0); return d; })();
  const dur = v ? Math.round((new Date(v.end) - new Date(v.start)) / 60000) : 60;
  const pad = (x) => String(x).padStart(2, "0");
  const back = v ? `#/wizyty/${v.id}` : "#/wizyty";
  return shell("wizyty", `
    <a class="crumb" href="${back}">${icon("back", "small")}${v ? t("visitForm.backToVisit") : t("visits.title")}</a>
    <div class="page__head"><h1 class="page__title">${v ? t("visitForm.editTitle") : t("visitForm.newTitle")}</h1></div>
    <div class="two-col">
      <form class="stack" data-form="visit" data-id="${v ? v.id : ""}">
        <div class="field"><label class="field__label" for="v-c">${t("visitForm.customer")}</label>
          <select class="select" id="v-c" name="customerId" required ${v ? "disabled" : ""}><option value="">${t("visitForm.pickCustomer")}</option>${mine.map((c) => `<option value="${c.id}" ${c.id === selId ? "selected" : ""}>${esc(c.name)}, ${esc(c.address.town)}</option>`).join("")}</select>
          <span class="field__hint">${t("visitForm.onlyMine")}</span></div>
        <div class="form-grid">
          <div class="field"><label class="field__label" for="v-d">${t("visitForm.day")}</label><input class="input" id="v-d" type="date" name="date" value="${R.isoDate(start)}" required></div>
          <div class="field"><label class="field__label" for="v-t">${t("visitForm.time")}</label><input class="input" id="v-t" type="time" name="time" value="${pad(start.getHours())}:${pad(start.getMinutes())}" step="900" required></div>
          <div class="field"><label class="field__label" for="v-dur">${t("visitForm.duration")}</label><select class="select" id="v-dur" name="dur">${[30, 45, 60, 90, 120, 180].map((m) => `<option value="${m}" ${m === dur ? "selected" : ""}>${m < 60 ? t("visitForm.minutes", { n: m }) : t("visitForm.hours", { n: m / 60 })}</option>`).join("")}</select></div>
        </div>
        <div class="field"><label class="field__label" for="v-p">${t("visitForm.place")}</label><input class="input" id="v-p" name="place" value="${esc(v ? v.place : "")}" placeholder="${t("visitForm.placePlaceholder")}"></div>
        ${v ? `<p class="t-meta measure">${t("visitForm.moveHint")}</p>` : ""}
        <div class="btn-row"><button class="btn" data-kind="primary" type="submit">${v ? t("visitForm.submitEdit") : t("visitForm.submitNew")}</button><a class="btn" data-kind="quiet" href="${back}">${t("action.cancel")}</a></div>
      </form>
      ${section(t("visitForm.previewTitle"), `<div data-slot="event">${eventPreview(selId, v ? v.place : "", googleLinked())}</div>`)}
    </div>`);
}
