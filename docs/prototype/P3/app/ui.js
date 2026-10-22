/*
 * Eko_CRM prototype P3 — shared partials: small HTML builders every view uses.
 * Each one corresponds to a future component (see README, component map).
 */
import { t, fmtTime, fmtDayShort, fmtDayLong } from "./i18n.js";
import { icon } from "./icons.js";
import * as R from "./rules.js";
import { S, user, userName, customer, stateOf, noteTasks, me, visit as getVisit, isManager } from "./store.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
export const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
export const mapsUrl = (q) => "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(q);

/** "dziś", "jutro", "wczoraj" or a short date. */
export function relDay(d) {
  const diff = Math.round((R.startOfDay(d) - R.startOfDay(S.NOW)) / 86400000);
  if (diff === 0) return t("time.today");
  if (diff === 1) return t("time.tomorrow");
  if (diff === -1) return t("time.yesterday");
  return fmtDayShort(d);
}
export const when = (iso) => `${relDay(iso)} ${fmtTime(iso)}`;

/* ---- Chips ---- */
export const stateChip = (state) => `<span class="state" data-state="${state}">${t("state." + state)}</span>`;
export const taskChip = (status) => `<span class="state" data-state="${status}">${t("status." + status)}</span>`;
export const lateChip = () => `<span class="state" data-state="late">${t("tasks.lateChip")}</span>`;
export const managerChip = () => `<span class="state" data-state="manager">${t("role.manager")}</span>`;
export const byManager = (authorId) => user(authorId)?.role === "manager";
export function flags(v) {
  return (v.moved ? `<span class="flag" data-flag="moved">${icon("moved", "small")}${t("flag.moved")}</span>` : "") +
    (v.unsynced ? `<span class="flag" data-flag="unsynced">${icon("cloudOff", "small")}${t("flag.unsynced")}</span>` : "");
}
export const person = (u, size) => `<span class="person" data-role="${u.role}" ${size ? `data-size="${size}"` : ""} title="${esc(u.name)}">${initials(u.name)}</span>`;

/* ---- Notice ---- */
export const notice = (tone, iconName, title, body, action = "") =>
  `<div class="notice" data-tone="${tone}" role="${tone === "decision" || tone === "blocked" ? "alert" : "status"}">${icon(iconName)}<div class="notice__body"><span class="notice__title">${title}</span>${body ? `<span>${body}</span>` : ""}</div>${action}</div>`;

/* ---- Section ---- */
export const section = (title, body, aside = "") => `<section class="section"><div class="section__head"><h2 class="section__title">${title}</h2>${aside}</div>${body}</section>`;

/* ---- Rows ---- */
export function visitRow(v) {
  const c = customer(v.customerId);
  const other = v.ownerId !== S.meId;
  return `<li><a class="row" data-link href="#/wizyty/${v.id}"><span class="row__time">${fmtTime(v.start)}</span>
    <span class="row__main"><span class="row__title">${esc(c.name)}</span><span class="t-meta">${relDay(v.start)}, ${fmtTime(v.start)}–${fmtTime(v.end)}${other ? ` · ${esc(userName(v.ownerId))}` : ""}</span></span>
    <span class="row__aside">${flags(v)}${stateChip(stateOf(v))}</span></a></li>`;
}

export function taskRow(a) {
  const c = customer(a.customerId);
  const late = R.isLate(a, S.NOW);
  const allowed = R.taskTransitions(a, me());
  const last = a.log[a.log.length - 1];
  return `<div class="task" ${late ? "data-late" : ""}>
    <span class="task__desc">${esc(a.text)}</span>
    <span class="row__aside">${late ? lateChip() : ""}${taskChip(a.status)}</span>
    <div class="task__meta">
      <a href="#/klienci/${c.id}">${esc(c.name)}</a>
      <span>${a.due ? t("tasks.due", { when: relDay(a.due + "T12:00:00") }) : t("tasks.noDue")}</span>
      ${a.ownerId !== S.meId ? `<span>${t("tasks.for", { name: esc(userName(a.ownerId)) })}</span>` : ""}
      ${a.authorId !== a.ownerId ? `<span>${t("tasks.by", { name: esc(userName(a.authorId)) })}</span>${byManager(a.authorId) ? managerChip() : ""}` : ""}
      ${last ? `<span>${t("tasks.changedBy", { name: esc(userName(last.by)) })}</span>${byManager(last.by) ? managerChip() : ""}` : ""}
      ${allowed.length ? `<label class="visually-hidden" for="st-${a.id}">${t("tasks.changeStatus")}</label><select class="select" id="st-${a.id}" data-task-status="${a.id}"><option value="">${t("tasks.changeStatus")}</option>${allowed.map((s) => `<option value="${s}">${t("status." + s)}</option>`).join("")}</select>` : ""}
    </div></div>`;
}

export function noteBlock(n) {
  const v = n.visitId ? getVisit(n.visitId) : null;
  const author = user(n.authorId);
  const mine = n.authorId === S.meId;
  return `<article class="note" ${author.role === "manager" ? 'data-by="manager"' : ""}>
    <div class="note__head"><span class="note__author">${esc(author.name)}</span>${author.role === "manager" ? managerChip() : ""}<span>${when(n.at)}</span>${v ? `<a href="#/wizyty/${v.id}">${t("note.visitLink", { date: fmtDayShort(v.start) })}</a>` : ""}
      ${mine ? `<button class="btn" data-kind="quiet" data-size="small" data-do="note-edit" data-id="${n.id}">${t("note.edit")}</button>` : ""}</div>
    <p class="note__text">${esc(n.text)}</p>
    ${noteTasks(n.id).map(taskRow).join("")}
    ${mine ? `<div><button class="btn" data-size="small" data-do="task-new" data-id="${n.id}">${icon("plus", "small")}${t("note.addTask")}</button></div>` : ""}
  </article>`;
}

/* VIS-3: what the calendar event will carry. */
export function eventPreview(customerId, place, linked) {
  const c = customer(customerId);
  if (!c) return `<p class="t-muted">${t("visitForm.previewPick")}</p>`;
  const phone = c.phones.find((p) => p.primary) ?? c.phones[0];
  return `<div class="event"><span class="event__title">${t("visitForm.eventTitle", { name: esc(c.name) })}</span>
    <span class="event__line">${icon("pin", "small")}${esc(place || R.addressLine(c.address) || t("visitForm.noAddress"))}</span>
    <span class="event__line">${icon("phone", "small")}${phone ? R.formatPhone(phone.value) : t("visitForm.noPhone")}</span></div>
    <p class="t-meta">${t("visitForm.previewNoAttendee")}</p>
    ${linked ? "" : `<p class="t-meta">${t("visitForm.previewUnsynced")}</p>`}`;
}

export const empty = (title, body, action = "") => `<div class="empty"><h2 class="empty__title">${title}</h2>${body ? `<p class="t-muted">${body}</p>` : ""}${action}</div>`;

/* ---- Toast and sheet (DOM) ---- */
export function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = msg;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => el.remove(), 4500);
}
const sheetEl = () => document.getElementById("sheet");
export function openSheet(html, tone) {
  const d = sheetEl();
  d.dataset.tone = tone ?? "";
  d.innerHTML = html;
  if (!d.open) d.showModal();
  const first = d.querySelector("[autofocus], input, select, textarea, button");
  if (first) first.focus();
}
export function closeSheet() { const d = sheetEl(); if (d.open) d.close(); }

export { fmtTime, fmtDayShort, fmtDayLong, isManager };
