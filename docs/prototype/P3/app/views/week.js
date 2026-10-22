/* The week: home screen. A rep sees their seven days; the manager sees lanes per rep. */
import { t, fmtTime, fmtDow, fmtDayLong, fmtDayShort, fmtDateFull } from "../i18n.js";
import { icon } from "../icons.js";
import * as R from "../rules.js";
import { S, me, isManager, visibleVisits, reminders, reps, customer, stateOf, userName } from "../store.js";
import { shell } from "./shell.js";
import { esc, flags, taskRow, section, empty, mapsUrl, relDay, visitRow } from "../ui.js";

const weekDays = () => { const from = R.addDays(R.startOfWeek(S.NOW), 7 * S.ui.weekOffset); return Array.from({ length: 7 }, (_, i) => R.addDays(from, i)); };
function rangeLabel(days) {
  const [a, b] = [days[0], days[6]];
  // "19–25 października 2026": the genitive comes from the full-date formatter.
  return a.getMonth() === b.getMonth() ? `${a.getDate()}–${fmtDateFull(b)}` : `${fmtDayShort(a)} – ${fmtDateFull(b)}`;
}
const onDay = (visits, d) => visits.filter((v) => R.sameDay(v.start, d)).sort((a, b) => a.start.localeCompare(b.start));

function visitBlock(v, showOwner) {
  const st = stateOf(v);
  const c = customer(v.customerId);
  return `<a class="visit" data-state="${st}" ${v.unsynced ? "data-unsynced" : ""} href="#/wizyty/${v.id}">
    <span class="visit__time">${fmtTime(v.start)}–${fmtTime(v.end)}</span>
    <span class="visit__name">${esc(c.name)}</span>
    <span class="visit__meta">${showOwner ? `<span>${esc(userName(v.ownerId))}</span>` : ""}<span>${t("state." + st)}</span>${flags(v)}</span></a>`;
}

function weekHead(days) {
  return `<div class="week-head">
    <h1 class="week-head__range">${rangeLabel(days)}</h1>
    <div class="week-head__nav">
      <button class="btn" data-kind="quiet" data-size="icon" data-do="week-shift" data-arg="-1" aria-label="${t("week.prev")}">${icon("prev")}</button>
      <button class="btn" data-kind="quiet" data-size="small" data-do="week-shift" data-arg="0" ${S.ui.weekOffset === 0 ? "disabled" : ""}>${t("week.thisWeek")}</button>
      <button class="btn" data-kind="quiet" data-size="icon" data-do="week-shift" data-arg="1" aria-label="${t("week.next")}">${icon("next")}</button>
    </div></div>`;
}

function daystrip(days, visits) {
  return `<div class="daystrip" role="group">${days.map((d) => { const n = onDay(visits, d).length; const iso = R.isoDate(d); return `
    <button class="daystrip__day" data-do="pick-day" data-arg="${iso}" aria-pressed="${S.ui.selectedDay === iso}" ${R.sameDay(d, S.NOW) ? "data-today" : ""}>
      <span class="daystrip__dow">${fmtDow(d)}</span><span class="daystrip__n">${d.getDate()}</span>
      <span class="daystrip__dots" aria-label="${t("week.visits", { n })}">${"<i></i>".repeat(Math.min(n, 4))}</span></button>`; }).join("")}</div>`;
}

function nextCard(mine) {
  const next = mine.filter((v) => stateOf(v) === "planned").sort((a, b) => a.start.localeCompare(b.start))[0];
  if (!next) return `<div class="next"><span class="t-meta">${t("week.nextVisit")}</span><p>${t("week.noNext")}</p></div>`;
  const c = customer(next.customerId);
  const phone = c.phones.find((p) => p.primary) ?? c.phones[0];
  const place = next.place || R.addressLine(c.address);
  return `<div class="next">
    <span class="t-meta">${t("week.nextVisit")}</span>
    <span class="next__when">${relDay(next.start)}, ${fmtTime(next.start)}–${fmtTime(next.end)}</span>
    <a class="next__name t-name" href="#/wizyty/${next.id}">${esc(c.name)}</a>
    <span class="t-meta">${esc(place)}</span>
    <div class="btn-row">
      ${phone ? `<a class="btn" href="tel:${phone.value}">${icon("phone")}${t("week.call")}</a>` : ""}
      ${place ? `<a class="btn" href="${mapsUrl(place)}" target="_blank" rel="noopener">${icon("pin")}${t("week.navigate")}</a>` : ""}
      <a class="btn" data-kind="quiet" href="#/wizyty/${next.id}">${t("week.details")}</a>
    </div></div>`;
}

function tasksPanel() {
  const rem = reminders().sort((a, b) => a.due.localeCompare(b.due));
  return section(t("week.tasksTitle"), rem.length ? rem.map(taskRow).join("") : `<p class="t-muted measure">${t("week.noTasks")}</p>`, rem.length ? `<span class="count">${rem.length}</span>` : "");
}

export function weekView() {
  const days = weekDays();
  if (isManager()) return managerWeek(days);
  const mine = visibleVisits().filter((v) => v.ownerId === me().id);
  const sel = days.find((d) => R.isoDate(d) === S.ui.selectedDay) ?? days[0];
  const selList = onDay(mine, sel);
  return shell("tydzien", `
    <div class="page__head">${weekHead(days)}<a class="btn" data-kind="primary" href="#/wizyty/nowa">${icon("plus")}${t("week.plan")}</a></div>
    <div class="board-desktop">
      <div class="week">${days.map((d) => { const list = onDay(mine, d); const past = R.endOfDay(d) < S.NOW; return `
        <div class="week__day" ${R.sameDay(d, S.NOW) ? "data-today" : ""} ${past ? "data-past" : ""}>
          <div class="week__head"><span class="week__dow">${fmtDow(d)}</span><span class="week__date">${d.getDate()}</span>${R.sameDay(d, S.NOW) ? `<span class="week__today">${t("week.today")}</span>` : ""}</div>
          <div class="week__body">${list.length ? list.map((v) => visitBlock(v, false)).join("") : `<span class="week__drop">${t("week.free")}</span>`}</div>
        </div>`; }).join("")}</div>
    </div>
    <div class="board-phone">
      ${daystrip(days, mine)}
      ${section(`<span class="cap">${fmtDayLong(sel)}</span>`, selList.length ? `<ul class="rows">${selList.map(visitRow).join("")}</ul>` : `<p class="t-muted">${t("week.free")}</p>`)}
    </div>
    <div class="two-col">${tasksPanel()}<div>${nextCard(mine)}</div></div>`);
}

function managerWeek(days) {
  const all = visibleVisits();
  const pick = S.ui.lanesRep && S.ui.selectedDay ? { rep: S.ui.lanesRep, day: days.find((d) => R.isoDate(d) === S.ui.selectedDay) } : null;
  const cell = (r, d) => {
    const list = onDay(all.filter((v) => v.ownerId === r.id), d);
    const counts = {};
    list.forEach((v) => { const s = stateOf(v); counts[s] = (counts[s] ?? 0) + 1; });
    const iso = R.isoDate(d);
    return `<a class="lanes__cell" href="#/tydzien" data-do="lanes-pick" data-rep="${r.id}" data-arg="${iso}" aria-label="${esc(r.name)}, ${fmtDayLong(d)}: ${t("week.visits", { n: list.length })}">
      ${["held", "planned", "cancelled", "awaiting"].filter((s) => counts[s]).map((s) => `<span class="lanes__n" data-state="${s}" title="${t("state." + s)}">${counts[s]}</span>`).join("") || `<span class="t-meta">–</span>`}</a>`;
  };
  const picked = pick && pick.day ? onDay(all.filter((v) => v.ownerId === pick.rep), pick.day) : [];
  const sel = days.find((d) => R.isoDate(d) === S.ui.selectedDay) ?? days[0];
  const phoneList = onDay(all, sel);
  return shell("tydzien", `
    <div class="page__head">${weekHead(days)}</div>
    <div class="board-desktop">
      <p class="t-muted measure">${t("week.teamSub")}</p>
      <div class="lanes" style="margin-top:12px">
        <div class="lanes__corner">${t("week.teamTitle")}</div>
        ${days.map((d) => `<div class="lanes__dow" ${R.sameDay(d, S.NOW) ? "data-today" : ""}><span class="cap">${fmtDow(d)}</span> ${d.getDate()}</div>`).join("")}
        ${reps().map((r) => `<div class="lanes__rep">${esc(r.name)}</div>${days.map((d) => cell(r, d)).join("")}`).join("")}
      </div>
      ${pick && pick.day ? section(`${esc(userName(pick.rep))}, <span class="cap">${fmtDayLong(pick.day)}</span>`, picked.length ? `<ul class="rows">${picked.map(visitRow).join("")}</ul>` : `<p class="t-muted">${t("week.lanesEmpty")}</p>`) : ""}
    </div>
    <div class="board-phone">
      ${daystrip(days, all)}
      ${section(`<span class="cap">${fmtDayLong(sel)}</span>`, phoneList.length ? `<div class="stack" data-gap="small">${phoneList.map((v) => visitBlock(v, true)).join("")}</div>` : `<p class="t-muted">${t("week.lanesEmpty")}</p>`)}
    </div>
    ${tasksPanel()}`);
}
