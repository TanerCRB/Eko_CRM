/* App shell: band with navigation, page-level notices, demo popover. */
import { t, fmtTime } from "../i18n.js";
import { icon, brandMark } from "../icons.js";
import { S, me, isManager, reminders, awaiting, pendingSync, customer } from "../store.js";
import { esc, person, notice, when } from "../ui.js";

export const NAV = [
  { key: "tydzien", label: "nav.week", icon: "week" },
  { key: "klienci", label: "nav.customers", icon: "customers" },
  { key: "wizyty", label: "nav.visits", icon: "visits" },
  { key: "zadania", label: "nav.tasks", icon: "tasks", badge: true },
  { key: "zespol", label: "nav.team", icon: "team", manager: true },
  { key: "pulpit", label: "nav.dashboard", icon: "dashboard", later: true },
  { key: "konto", label: "nav.account", icon: "account" },
];
export const navItems = () => NAV.filter((n) => !n.manager || isManager());
const badge = (n) => (n.badge && reminders().length ? `<span class="count">${reminders().length}</span>` : "");

export function shell(active, content) {
  const u = me();
  return `
    <a class="visually-hidden" href="#main">${t("app.skip")}</a>
    <header class="band"><div class="band__in">
      <a class="brand" href="#/tydzien">${brandMark}${t("app.name")}</a>
      <nav class="nav" aria-label="${t("nav.menu")}">
        ${navItems().map((n) => `<a class="nav__link" href="#/${n.key}" ${active === n.key ? 'aria-current="page"' : ""}>${t(n.label)}${n.later ? `<span class="nav__later">${t("nav.later")}</span>` : ""}${badge(n)}</a>`).join("")}
      </nav>
      <div class="band__right">
        <button class="btn" data-kind="band" data-size="small" popovertarget="demo-pop" aria-label="${t("demo.title")}">${icon("demo", "small")}${t("demo.title")}</button>
        <a class="band__me" href="#/konto" title="${t("nav.account")}">
          <span class="google-dot" data-link="${u.google}" aria-hidden="true"></span>
          ${person(u, "small")}
          <span><span class="band__me-name">${esc(u.name)}</span><br><span class="band__me-role">${t("role." + u.role)}</span></span>
        </a>
        <button class="btn menu-btn" data-kind="band" data-size="icon" data-do="menu" aria-label="${t("nav.menu")}">${icon("menu")}</button>
      </div>
    </div></header>
    <main class="page" id="main" tabindex="-1">
      ${notices()}
      ${content}
    </main>
    ${demoPopover()}`;
}

/* VIS-8 reconnect notice and VIS-11 decision bar: on every page, for the owner only. */
export function notices() {
  const u = me();
  const out = [];
  const pending = pendingSync(u.id).length;
  if (u.google === "expired") {
    out.push(notice("blocked", "cloudOff", t("notice.expiredTitle"), `${t("notice.expiredBody")} ${pending ? t("notice.expiredPending", { n: pending }) : ""}`,
      `<button class="btn" data-kind="primary" data-size="small" data-do="google-connect">${t("notice.reconnect")}</button>`));
  } else if (u.google === "none" && u.role === "rep") {
    out.push(notice("hint", "cloud", t("notice.noneTitle"), t("notice.noneBody"), `<a class="btn" data-size="small" href="#/konto">${t("notice.connect")}</a>`));
  }
  const aw = awaiting();
  if (aw.length) {
    out.push(notice("decision", "alert", t("notice.decisionTitle", { n: aw.length }),
      aw.map((v) => `${esc(customer(v.customerId).name)}, ${when(v.start)}`).join("; "),
      `<button class="btn" data-kind="primary" data-size="small" data-do="decide" data-id="${aw[0].id}">${t("notice.decide")}</button>`));
  }
  return out.length ? `<div class="notices">${out.join("")}</div>` : "";
}

function demoPopover() {
  return `<div class="popover" id="demo-pop" popover>
    <strong>${t("demo.title")}</strong>
    <span class="t-meta">${t("demo.clock", { time: fmtTime(S.NOW) })}</span>
    <div class="stack" data-gap="small"><span class="t-meta">${t("demo.as")}</span>
      ${S.users.map((u) => `<button class="btn" data-size="small" ${u.id === S.meId ? 'data-kind="primary"' : ""} data-do="login" data-id="${u.id}">${esc(u.name)} <small>${t("role." + u.role)}</small></button>`).join("")}</div>
    <div class="btn-row">
      <button class="btn" data-size="small" data-do="sim-delete">${t("demo.simDelete")}</button>
      <button class="btn" data-size="small" data-do="sim-expire">${t("demo.simExpire")}</button>
      <button class="btn" data-size="small" data-do="theme">${t("demo.theme")}</button>
      <button class="btn" data-size="small" data-kind="destructive" data-do="reset">${t("demo.reset")}</button>
    </div></div>`;
}

export function menuSheet(active) {
  return `<div class="sheet__head"><h2 class="sheet__title">${t("nav.menu")}</h2></div>
    <nav class="sheet__body menu" aria-label="${t("nav.menu")}">
      ${navItems().map((n) => `<a class="menu__link" href="#/${n.key}" data-do="menu-go" ${active === n.key ? 'aria-current="page"' : ""}>${icon(n.icon)}${t(n.label)}${n.later ? `<span class="nav__later t-meta">${t("nav.later")}</span>` : ""}${badge(n)}</a>`).join("")}
      <a class="menu__link" href="#/logowanie" data-do="logout">${icon("logout")}${t("nav.logout")}</a>
    </nav>
    <div class="sheet__foot"><button class="btn" data-kind="quiet" data-do="sheet-close">${t("action.close")}</button></div>`;
}
