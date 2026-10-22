/* Tasks, team (reassignment), dashboard, account, login. */
import { t, fmtDateFull } from "../i18n.js";
import { icon, brandMark } from "../icons.js";
import * as R from "../rules.js";
import { S, me, isManager, visibleTasks, reps, customer, userName, futureVisitsOf, openTasksOf } from "../store.js";
import { shell, navItems } from "./shell.js";
import { notFound } from "./customers.js";
import { esc, taskRow, section, empty } from "../ui.js";

/* ---------- Tasks (ACT-*) ---------- */
export function tasksView() {
  const tab = S.ui.tasksTab;
  let list = visibleTasks();
  if (tab === "open") list = list.filter(R.isOpen);
  if (tab === "late") list = list.filter((a) => R.isLate(a, S.NOW));
  list = list.sort((a, b) => (a.due ?? "9999").localeCompare(b.due ?? "9999"));
  return shell("zadania", `
    <div class="page__head"><div class="page__titles"><h1 class="page__title">${t("tasks.title")}</h1><p class="page__sub">${isManager() ? t("tasks.subManager") : t("tasks.subRep")}</p></div></div>
    <div class="tabs" role="group">${[["open", "tasks.open"], ["late", "tasks.late"], ["all", "tasks.all"]].map(([k, l]) => `<button class="tabs__tab" data-do="tab" data-key="tasksTab" data-value="${k}" aria-pressed="${tab === k}">${t(l)}</button>`).join("")}</div>
    <div style="max-width:860px">${list.length ? list.map(taskRow).join("") : empty(tab === "late" ? t("tasks.noneLate") : t("tasks.none"))}</div>`);
}

/* ---------- Team: reassignment (CUS-10) ---------- */
export function teamView() {
  if (!isManager()) return notFound("tydzien");
  const from = S.ui.teamOwner;
  const list = S.customers.filter((c) => !c.archived && (from === "all" || c.ownerId === from)).sort((a, b) => a.name.localeCompare(b.name, "pl"));
  const sel = [...S.selected].filter((id) => list.some((c) => c.id === id));
  return shell("zespol", `
    <div class="page__head"><div class="page__titles"><h1 class="page__title">${t("team.title")}</h1><p class="page__sub measure">${t("team.sub")}</p></div></div>
    <div class="toolbar">
      <select class="select" data-filter="teamOwner" style="width:auto" aria-label="${t("team.colOwner")}"><option value="all">${t("team.allReps")}</option>${reps().map((r) => `<option value="${r.id}" ${from === r.id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select>
      <span class="t-meta" style="margin-left:auto">${sel.length ? t("team.selected", { n: sel.length }) : t("team.selectHint")}</span>
      <button class="btn" data-kind="primary" data-do="reassign" ${sel.length ? "" : "disabled"}>${icon("team")}${t("team.reassign")}</button></div>
    <div class="table-scroll"><table class="table">
      <thead><tr><th><span class="visually-hidden">${t("team.selectHint")}</span></th><th>${t("team.colCustomer")}</th><th>${t("team.colTown")}</th><th>${t("team.colOwner")}</th><th data-num>${t("team.colFuture")}</th><th data-num>${t("team.colOpen")}</th></tr></thead>
      <tbody>${list.map((c) => `<tr><td><input type="checkbox" class="check-box" data-select="${c.id}" ${S.selected.has(c.id) ? "checked" : ""} aria-label="${t("team.select", { name: esc(c.name) })}" style="width:18px;height:18px;accent-color:var(--primary)"></td>
        <td><a href="#/klienci/${c.id}">${esc(c.name)}</a></td><td>${esc(c.address.town)}</td><td>${esc(userName(c.ownerId))}</td><td data-num>${futureVisitsOf(c.id).length}</td><td data-num>${openTasksOf(c.id).length}</td></tr>`).join("")}</tbody></table></div>`);
}

/* ---------- Dashboard (DSH-*, after MVP) ---------- */
export function dashboardView() {
  const p = S.ui.period;
  const [from, to] = R.periodRange(p, S.NOW);
  const scope = isManager() ? S.visits : S.visits.filter((v) => v.ownerId === S.meId); // DSH-4, DSH-5
  const tot = R.countVisits(scope, from, to, S.NOW);
  const tile = (k, label, val) => `<div class="tile" data-state="${k}"><span class="tile__value">${val}</span><span class="tile__label">${label}</span></div>`;
  const share = (c) => (c.planned ? Math.round((100 * c.held) / c.planned) : 0);
  const rowOf = (name, c, total) => `<tr ${total ? "data-total" : ""}><td>${esc(name)}</td><td data-num>${c.planned}</td><td data-num>${c.held}</td><td data-num>${c.moved}</td><td data-num>${c.cancelled}</td><td data-num>${c.awaiting}</td>
    <td><div class="bar" role="img" aria-label="${share(c)}%"><i style="width:${share(c)}%"></i></div></td></tr>`;
  return shell("pulpit", `
    <div class="page__head"><div class="page__titles"><h1 class="page__title">${t("dashboard.title")}</h1><p class="page__sub">${fmtDateFull(from)} – ${fmtDateFull(to)}. ${isManager() ? t("dashboard.scopeTeam") : t("dashboard.scopeMine")}</p></div><span class="flag">${t("dashboard.laterTag")}</span></div>
    <div class="tabs" role="group">${["today", "week", "month", "quarter", "year"].map((k) => `<button class="tabs__tab" data-do="tab" data-key="period" data-value="${k}" aria-pressed="${p === k}">${t("dashboard." + k)}</button>`).join("")}</div>
    <div class="tiles">${tile("planned", t("dashboard.planned"), tot.planned)}${tile("held", t("dashboard.held"), tot.held)}${tile("moved", t("dashboard.moved"), tot.moved)}${tile("cancelled", t("dashboard.cancelled"), tot.cancelled)}${tile("awaiting", t("dashboard.awaiting"), tot.awaiting)}</div>
    ${isManager() ? `<div class="table-scroll"><table class="table" aria-label="${t("dashboard.tableLabel")}"><thead><tr><th>${t("dashboard.colRep")}</th><th data-num>${t("dashboard.planned")}</th><th data-num>${t("dashboard.held")}</th><th data-num>${t("dashboard.moved")}</th><th data-num>${t("dashboard.cancelled")}</th><th data-num>${t("dashboard.awaiting")}</th><th>${t("dashboard.colShare")}</th></tr></thead>
      <tbody>${reps().map((r) => rowOf(r.name, R.countVisits(S.visits.filter((v) => v.ownerId === r.id), from, to, S.NOW), false)).join("")}${rowOf(t("dashboard.total"), tot, true)}</tbody></table></div>` : ""}
    <p class="t-meta measure">${t("dashboard.rule")}</p>`);
}

/* ---------- Account and Google (VIS-7, VIS-8) ---------- */
export function accountView() {
  const u = me();
  const stateKey = { linked: "held", expired: "late", none: "todo" }[u.google];
  return shell("konto", `
    <div class="page__head"><h1 class="page__title">${t("account.title")}</h1></div>
    ${section(t("account.google"), `
      <p class="measure">${t("account.body")}</p>
      ${u.google === "linked" ? `<dl class="kv"><dt>${t("account.acct")}</dt><dd>${esc(u.name.split(" ")[0].toLowerCase())}.demo@gmail.com</dd><dt>${t("account.calendar")}</dt><dd>${t("account.primaryCal")}</dd></dl>
        <p class="t-meta measure">${t("account.unlinkHint")}</p><div><button class="btn" data-do="google-disconnect">${t("account.unlink")}</button></div>`
      : `<p class="t-meta measure">${u.google === "expired" ? t("account.expiredHint") : t("account.noneHint")}</p><div><button class="btn" data-kind="primary" data-do="google-connect">${u.google === "expired" ? t("account.reconnect") : t("account.connect")}</button></div>`}`,
      `<span class="state" data-state="${stateKey}">${t("account." + u.google)}</span>`)}
    ${section(t("account.moreTitle"), `<nav class="menu">
      ${navItems().filter((n) => n.key === "zespol" || n.key === "pulpit").map((n) => `<a class="menu__link" href="#/${n.key}">${icon(n.icon)}${t(n.label)}${n.later ? `<span class="nav__later t-meta">${t("nav.later")}</span>` : ""}</a>`).join("")}
      <a class="menu__link" href="#/logowanie" data-do="logout">${icon("logout")}${t("nav.logout")}</a></nav>`)}`);
}

/* ---------- Login (ACC-1, ACC-2, ACC-3) ---------- */
export function loginView() {
  return `<div class="login">
    <div class="login__band"><div class="login__band-in">
      <span class="brand">${brandMark}${t("app.name")}</span>
      <h1 class="login__claim">${t("login.claim")}</h1>
      <p class="login__claimSub">${t("login.claimSub")}</p></div></div>
    <div class="login__main"><div class="login__card">
      <form class="stack" data-form="login">
        <h2 class="t-h2">${t("login.title")}</h2>
        <p class="t-muted">${t("login.noGoogle")}</p>
        <div class="field"><label class="field__label" for="lg-user">${t("login.user")}</label><input class="input" id="lg-user" autocomplete="username"></div>
        <div class="field"><label class="field__label" for="lg-pass">${t("login.password")}</label><input class="input" id="lg-pass" type="password" autocomplete="current-password"><a class="field__hint" href="#/logowanie" data-do="forgot">${t("login.forgot")}</a></div>
        <div><button class="btn" data-kind="primary" type="submit">${t("login.submit")}</button></div>
      </form>
      <div class="login__people"><span class="t-meta">${t("login.demoPick")}</span>
        ${S.users.map((u) => `<button class="btn" data-do="login" data-id="${u.id}"><span class="person" data-role="${u.role}" data-size="small">${u.name.split(" ").map((p) => p[0]).join("")}</span>${esc(u.name)} <small>${t("role." + u.role)}</small></button>`).join("")}</div>
    </div></div></div>`;
}
