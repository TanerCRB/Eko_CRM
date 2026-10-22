/*
 * Eko_CRM interactive demo — prototype P1.
 * Vanilla JS, hash routing, in-memory state (resettable). No backend: the "server" rules the brief
 * puts on the API (ACC-4, CUS-6, ACT-2, ...) are simulated here so the screens show their outcomes.
 * Screens map to requirements in ../README.md.
 */
(function () {
  "use strict";
  const D = window.EkoDomain;
  const { icon, brandMark } = window.EkoIcons;
  const NOW = window.EkoSeed.NOW;

  /* ================= State ================= */
  const clone = (x) => JSON.parse(JSON.stringify(x));
  let S = freshState();
  function freshState() {
    const s = clone(window.EkoSeed);
    return { ...s, viewerId: null, postponedUntilNav: false, demoOpen: false, draft: null, filters: { q: "", archived: false, owner: "all", actions: "open", period: "week", visits: "upcoming", reassignFrom: "all" }, selected: new Set() };
  }

  const viewer = () => S.users.find((u) => u.id === S.viewerId);
  const isManager = () => viewer() && viewer().role === "manager";
  const userName = (id) => (S.users.find((u) => u.id === id) || {}).name || "—";
  const customer = (id) => S.customers.find((c) => c.id === id);
  const visitState = (v) => D.visitState(v, NOW);

  /* ACC-4: what the viewer may read. */
  const canSeeCustomer = (c) => c && (isManager() || c.ownerId === S.viewerId);
  const canSeeVisit = (v) => v && (isManager() || v.ownerId === S.viewerId);
  const myCustomers = () => S.customers.filter(canSeeCustomer);
  const myVisits = () => S.visits.filter(canSeeVisit);
  const myActions = () => S.actions.filter((a) => isManager() || a.ownerId === S.viewerId);
  const reminders = () => S.actions.filter((a) => a.ownerId === S.viewerId && D.isReminder(a, NOW));
  // VIS-11: only the owner sees the prompt.
  const awaiting = () => S.visits.filter((v) => v.ownerId === S.viewerId && visitState(v) === "awaiting");

  /* ================= Utilities ================= */
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
  const t = (iso) => D.fmtTime.format(new Date(iso));
  const dShort = (iso) => D.fmtDate.format(new Date(iso));
  const sameDay = (a, b) => D.startOfDay(a).getTime() === D.startOfDay(b).getTime();
  const relDay = (iso) => {
    const d = D.startOfDay(iso), n = D.startOfDay(NOW);
    const diff = Math.round((d - n) / 86400000);
    if (diff === 0) return "dziś";
    if (diff === 1) return "jutro";
    if (diff === -1) return "wczoraj";
    return D.fmtDate.format(d);
  };
  const addressLine = (a) => [a.street, [a.postalCode, a.town].filter(Boolean).join(" "), a.country !== "Polska" ? a.country : ""].filter(Boolean).join(", ");
  const mapsUrl = (q) => "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(q);
  const uid = (p) => p + Math.random().toString(36).slice(2, 8);
  const googleLinked = () => viewer().google === "linked";

  function toast(msg) {
    const el = document.createElement("div");
    el.className = "ek-toast";
    el.textContent = msg;
    document.getElementById("toasts").appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  const chip = (state) => `<span class="ek-chip ek-chip--${state}">${D.VISIT_STATE_LABEL[state]}</span>`;
  const statusChip = (s) => `<span class="ek-chip ek-chip--${s === "inprogress" ? "planned" : s}">${D.ACTION_STATUS_LABEL[s]}</span>`;
  const flags = (v) => (v.moved ? `<span class="ek-flag" title="Termin zmieniony co najmniej raz">${icon("moved", "ek-icon--sm")}Przeniesiona</span>` : "") +
    (v.unsynced ? `<span class="ek-flag ek-flag--unsynced" title="Jeszcze nie ma jej w kalendarzu Google">${icon("cloudOff", "ek-icon--sm")}Niezsynchronizowana</span>` : "");
  const managerTag = (authorId) => (S.users.find((u) => u.id === authorId) || {}).role === "manager" ? `<span class="ek-chip ek-chip--manager">Kierownik</span>` : "";

  /* ================= Router ================= */
  function route() {
    const h = location.hash.replace(/^#\/?/, "") || "today";
    const [path, query] = h.split("?");
    return { parts: path.split("/"), query: new URLSearchParams(query || "") };
  }
  const go = (hash) => { location.hash = hash; };

  window.addEventListener("hashchange", () => { S.postponedUntilNav = false; render(); window.scrollTo(0, 0); });

  /* ================= Shell ================= */
  const NAV = [
    { key: "today", label: "Dziś", icon: "today" },
    { key: "customers", label: "Klienci", icon: "customers" },
    { key: "visits", label: "Wizyty", icon: "visits" },
    { key: "actions", label: "Akcje", icon: "actions" },
    { key: "team", label: "Przypisania", icon: "team", manager: true },
    { key: "dashboard", label: "Pulpit", icon: "dashboard", later: true },
    { key: "settings", label: "Konto i kalendarz", icon: "settings" },
  ];

  function shell(active, content) {
    const items = NAV.filter((n) => !n.manager || isManager());
    const count = (k) => (k === "actions" && reminders().length ? `<span class="ek-count">${reminders().length}</span>` : "");
    const u = viewer();
    const tabs = ["today", "customers", "visits", "actions", "settings"].map((k) => NAV.find((n) => n.key === k));
    return `
      <a class="ek-visually-hidden" href="#main">Przejdź do treści</a>
      <div class="app">
        <aside class="rail">
          <a class="brand" href="#/today">${brandMark}Eko CRM</a>
          <nav class="nav" aria-label="Główna">
            ${items.map((n) => `<a class="nav__link" href="#/${n.key}" ${active === n.key ? 'aria-current="page"' : ""}>${icon(n.icon)}${n.label}${n.later ? '<span class="nav__later">po MVP</span>' : ""}${count(n.key)}</a>`).join("")}
          </nav>
          <div class="rail__foot">
            <div class="who"><span class="ek-avatar ${u.role === "manager" ? "ek-avatar--manager" : ""}">${initials(u.name)}</span>
              <div><div class="who__name">${esc(u.name)}</div><div class="who__role">${u.role === "manager" ? "Kierownik" : "Handlowiec"}</div></div></div>
            <button class="ek-btn ek-btn--ghost ek-btn--sm" data-act="logout">${icon("logout", "ek-icon--sm")}Wyloguj</button>
          </div>
        </aside>
        <header class="topbar">
          <a class="brand" href="#/today">${brandMark}Eko CRM</a>
          <span class="ek-avatar ${u.role === "manager" ? "ek-avatar--manager" : ""}" title="${esc(u.name)}">${initials(u.name)}</span>
        </header>
        <main class="main" id="main" tabindex="-1">
          ${notices()}
          ${content}
        </main>
        <nav class="tabbar" aria-label="Główna">
          ${tabs.map((n) => `<a class="tabbar__link" href="#/${n.key}" ${active === n.key || (n.key === "settings" && (active === "team" || active === "dashboard")) ? 'aria-current="page"' : ""}>${icon(n.icon)}${n.key === "settings" ? "Więcej" : n.label}${count(n.key)}</a>`).join("")}
        </nav>
      </div>
      ${demoPanel()}`;
  }

  /* VIS-8 reconnect notice and VIS-11 decision prompt — on every page. */
  function notices() {
    const out = [];
    const u = viewer();
    const pending = S.visits.filter((v) => v.ownerId === u.id && v.unsynced).length;
    if (u.google === "expired") {
      out.push(`<div class="ek-banner ek-banner--warn" role="alert">${icon("cloudOff")}
        <div class="ek-banner__body"><span class="ek-banner__title">Dostęp do kalendarza Google wygasł</span>
        <span>Wizyty zapisują się w aplikacji, ale nie trafiają do kalendarza. ${pending ? `Czeka ${pending} ${pending === 1 ? "zmiana" : "zmiany"}.` : ""} Stany wizyt się nie zmieniają.</span></div>
        <button class="ek-btn ek-btn--sm ek-btn--primary" data-act="google-connect">Połącz ponownie</button></div>`);
    } else if (u.google === "none" && u.role === "rep") {
      out.push(`<div class="ek-banner ek-banner--info">${icon("cloud")}
        <div class="ek-banner__body"><span class="ek-banner__title">Kalendarz Google nie jest połączony</span>
        <span>Wizyty działają bez niego; po połączeniu pojawią się w Twoim kalendarzu.</span></div>
        <a class="ek-btn ek-btn--sm" href="#/settings">Połącz</a></div>`);
    }
    const aw = awaiting();
    if (aw.length) {
      out.push(`<div class="ek-banner ek-banner--decision">${icon("alert")}
        <div class="ek-banner__body"><span class="ek-banner__title">${aw.length === 1 ? "Wizyta usunięta w Google czeka na Twoją decyzję" : `${aw.length} wizyty usunięte w Google czekają na decyzję`}</span>
        <span>${aw.map((v) => `${esc(customer(v.customerId).name)}, ${relDay(v.start)} ${t(v.start)}`).join("; ")}</span></div>
        <button class="ek-btn ek-btn--sm ek-btn--primary" data-act="decide" data-id="${aw[0].id}">Zdecyduj</button></div>`);
    }
    return out.length ? `<div class="notices">${out.join("")}</div>` : "";
  }

  function demoPanel() {
    return `<div class="demo">
      <button class="ek-btn ek-btn--sm demo__toggle" data-act="demo-toggle" aria-expanded="${S.demoOpen}">${icon("demo", "ek-icon--sm")}Demo</button>
      <div class="demo__panel" ${S.demoOpen ? "" : "hidden"}>
        <div class="ek-h3">Sterowanie demo</div>
        <p class="ek-meta">Zegar demo: dziś, ${t(NOW.toISOString())}. Dane są syntetyczne i żyją tylko w tej karcie.</p>
        <div class="ek-field"><span class="ek-field__label">Zalogowany jako</span>
          <div class="stack stack--sm">${S.users.map((u) => `<button class="ek-btn ek-btn--sm ${u.id === S.viewerId ? "ek-btn--primary" : ""}" data-act="switch-user" data-id="${u.id}">${esc(u.name)} — ${u.role === "manager" ? "kierownik" : "handlowiec"}</button>`).join("")}</div></div>
        <div class="ek-btn-row">
          <button class="ek-btn ek-btn--sm" data-act="sim-google-delete">Symuluj usunięcie w Google</button>
          <button class="ek-btn ek-btn--sm" data-act="theme">Motyw jasny/ciemny</button>
          <button class="ek-btn ek-btn--sm ek-btn--danger" data-act="reset">Resetuj dane</button>
        </div>
      </div></div>`;
  }

  /* ================= Screens ================= */

  /* ---- Login (ACC-1, ACC-2, ACC-3) ---- */
  function screenLogin() {
    return `<div class="login"><div class="login__card">
      <a class="brand" href="#/login">${brandMark}Eko CRM</a>
      <div class="stack stack--sm"><h1 class="ek-h1">Zaloguj się</h1>
        <p class="ek-muted">Konto zakłada administrator. Do logowania nie potrzebujesz konta Google.</p></div>
      <form class="stack" data-form="login">
        <div class="ek-field"><label class="ek-field__label" for="lg-user">Login lub e-mail służbowy</label><input class="ek-input" id="lg-user" autocomplete="username"></div>
        <div class="ek-field"><label class="ek-field__label" for="lg-pass">Hasło</label><input class="ek-input" id="lg-pass" type="password" autocomplete="current-password">
          <a class="ek-field__hint" href="#/login" data-act="noop">Nie pamiętasz hasła? Link do zmiany przyjdzie e-mailem.</a></div>
        <button class="ek-btn ek-btn--primary" type="submit">Zaloguj się</button>
      </form>
      <div class="login__or"><span class="ek-meta">Demo: wybierz osobę, bez hasła</span>
        ${S.users.map((u) => `<button class="ek-btn" data-act="switch-user" data-id="${u.id}">${esc(u.name)} — ${u.role === "manager" ? "kierownik" : "handlowiec"}</button>`).join("")}
      </div></div></div>`;
  }

  /* ---- Today: agenda + reminders (ACT-4) ---- */
  function screenToday() {
    const u = viewer();
    const today = myVisits().filter((v) => v.ownerId === u.id && sameDay(v.start, NOW)).sort((a, b) => a.start.localeCompare(b.start));
    const next = today.find((v) => visitState(v) === "planned");
    const rem = reminders();
    const nextCard = next ? (() => {
      const c = customer(next.customerId);
      const primary = c.phones.find((p) => p.primary) || c.phones[0];
      const place = next.place || addressLine(c.address);
      return `<section class="ek-panel" aria-labelledby="next-h"><div class="ek-panel__head"><h2 class="ek-h3" id="next-h">Następna wizyta, ${t(next.start)}</h2>${flags(next)}</div>
        <div class="ek-panel__body stack">
          <a class="ek-h2" href="#/customers/${c.id}" style="text-decoration:none">${esc(c.name)}</a>
          <div class="ek-btn-row">
            ${primary ? `<a class="ek-btn" href="tel:${primary.value}">${icon("phone")}Zadzwoń</a>` : ""}
            ${place ? `<a class="ek-btn" href="${mapsUrl(place)}" target="_blank" rel="noopener">${icon("pin")}Nawiguj</a>` : ""}
            <a class="ek-btn ek-btn--ghost" href="#/visits/${next.id}">Szczegóły</a>
          </div>
          <p class="ek-meta">${esc(place)}</p></div></section>`;
    })() : "";

    return shell("today", `
      <div class="page-head"><div class="today-head"><span class="today-head__clock">${t(NOW.toISOString())}</span><span class="today-head__day">${D.fmtDay.format(NOW)}</span></div>
        ${u.role === "rep" ? `<a class="ek-btn ek-btn--primary" href="#/visits/new">${icon("plus")}Zaplanuj wizytę</a>` : ""}</div>
      <div class="cols">
        <section class="ek-panel" aria-labelledby="ag-h">
          <div class="ek-panel__head"><h2 class="ek-h3" id="ag-h">${today.length ? `Twój dzień: ${today.length} ${today.length === 1 ? "wizyta" : today.length < 5 ? "wizyty" : "wizyt"}` : "Twój dzień"}</h2></div>
          <div class="ek-panel__body">${today.length ? agenda(today) : `<div class="ek-empty"><p>Na dziś nie masz zaplanowanych wizyt.</p>${u.role === "rep" ? `<a class="ek-btn" href="#/visits/new">${icon("plus")}Zaplanuj wizytę</a>` : ""}</div>`}</div>
        </section>
        <div class="stack">
          ${nextCard}
          <section class="ek-panel" aria-labelledby="rem-h">
            <div class="ek-panel__head"><h2 class="ek-h3" id="rem-h">Na dziś i zaległe</h2>${rem.length ? `<span class="ek-count">${rem.length}</span>` : ""}</div>
            <div class="ek-panel__body stack stack--sm">${rem.length ? rem.sort((a, b) => a.due.localeCompare(b.due)).map(actionCard).join("") : `<p class="ek-muted">Nic nie czeka. Akcje bez terminu nie trafiają do przypomnień.</p>`}</div>
          </section>
        </div>
      </div>`);
  }

  /* The signature element: hour rails, visits in their real slot, rapeseed line at now. */
  function agenda(list) {
    const startH = Math.min(7, ...list.map((v) => new Date(v.start).getHours()));
    const endH = Math.max(18, ...list.map((v) => new Date(v.end).getHours() + 1));
    const hourH = 64;
    const y = (iso) => { const d = new Date(iso); return (d.getHours() - startH + d.getMinutes() / 60) * hourH; };
    const hours = [];
    for (let h = startH; h < endH; h++) hours.push(`<div class="ek-agenda__hour"><span class="ek-agenda__label">${String(h).padStart(2, "0")}:00</span></div>`);
    const items = list.map((v) => {
      const st = visitState(v);
      const c = customer(v.customerId);
      const top = y(v.start), height = Math.max(y(v.end) - top - 2, 30);
      return `<a class="ek-agenda__visit ek-agenda__visit--${st} ${v.unsynced ? "ek-agenda__visit--unsynced" : ""}" href="#/visits/${v.id}" style="top:${top + 1}px;height:${height}px">
        <span class="ek-agenda__visit-title">${esc(c.name)}</span>
        ${height > 44 ? `<span class="ek-meta">${t(v.start)}–${t(v.end)} · ${D.VISIT_STATE_LABEL[st]}${v.moved ? " · przeniesiona" : ""}${v.unsynced ? " · niezsynchronizowana" : ""}</span>` : ""}</a>`;
    }).join("");
    const nowY = y(NOW.toISOString());
    return `<div class="ek-agenda" style="--hour-h:${hourH}px" role="list" aria-label="Wizyty dziś">
      ${hours.join("")}${items}
      <div class="ek-agenda__now" style="top:${nowY}px"><span class="ek-agenda__now-label">${t(NOW.toISOString())}</span></div></div>`;
  }

  /* ---- Customers list ---- */
  function screenCustomers() {
    const f = S.filters;
    const q = f.q.trim().toLowerCase();
    const list = myCustomers()
      .filter((c) => c.archived === f.archived)
      .filter((c) => !isManager() || f.owner === "all" || c.ownerId === f.owner)
      .filter((c) => !q || [c.name, c.address.town, c.nip, ...c.phones.map((p) => p.value)].join(" ").toLowerCase().includes(q))
      .sort((a, b) => a.name.localeCompare(b.name, "pl"));
    const reps = S.users.filter((u) => u.role === "rep");
    return shell("customers", `
      <div class="page-head"><div class="page-head__titles"><h1 class="ek-h1">Klienci</h1>
        <p class="ek-muted">${isManager() ? "Wszyscy klienci firmy" : "Twoi klienci"}</p></div>
        <a class="ek-btn ek-btn--primary" href="#/customers/new">${icon("plus")}Dodaj klienta</a></div>
      <div class="toolbar">
        <label class="search"><span class="ek-visually-hidden">Szukaj klientów</span>${icon("search")}<input class="ek-input" data-filter="q" value="${esc(f.q)}" placeholder="Nazwa, miejscowość, NIP lub telefon"></label>
        ${isManager() ? `<select class="ek-select" data-filter="owner" style="width:auto" aria-label="Handlowiec"><option value="all">Wszyscy handlowcy</option>${reps.map((r) => `<option value="${r.id}" ${f.owner === r.id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select>` : ""}
        <div class="ek-seg" role="group" aria-label="Widok">
          <button class="ek-seg__btn" data-act="filter" data-k="archived" data-v="" aria-pressed="${!f.archived}">Aktywni</button>
          <button class="ek-seg__btn" data-act="filter" data-k="archived" data-v="1" aria-pressed="${f.archived}">Zarchiwizowani</button></div>
      </div>
      <section class="ek-panel">${list.length ? `<ul class="ek-list">${list.map((c) => {
        const nextV = S.visits.filter((v) => v.customerId === c.id && visitState(v) === "planned").sort((a, b) => a.start.localeCompare(b.start))[0];
        const open = S.actions.filter((a) => a.customerId === c.id && (a.status === "todo" || a.status === "inprogress")).length;
        return `<li><a class="ek-row ek-row--link" href="#/customers/${c.id}"><span class="ek-avatar">${initials(c.name)}</span>
          <span class="ek-row__main"><span class="ek-row__title">${esc(c.name)}</span><span class="ek-meta">${esc(c.address.town || "bez adresu")}${isManager() ? ` · ${esc(userName(c.ownerId))}` : ""}</span></span>
          <span class="ek-row__aside">${nextV ? `<span class="ek-meta">${relDay(nextV.start)} ${t(nextV.start)}</span>` : ""}${open ? `<span class="ek-chip ek-chip--todo">${open} ${open === 1 ? "akcja" : "akcje"}</span>` : ""}</span></a></li>`;
      }).join("")}</ul>` : `<div class="ek-panel__body"><div class="ek-empty">${f.q ? `<p>Nikt nie pasuje do „${esc(f.q)}”. Sprawdź pisownię albo dodaj nowego klienta.</p>` : f.archived ? "<p>Brak zarchiwizowanych klientów.</p>" : "<p>Nie masz jeszcze klientów.</p>"}<a class="ek-btn" href="#/customers/new">${icon("plus")}Dodaj klienta</a></div></div>`}</section>`);
  }

  function noAccess(active) {
    // ACC-4: same message whether the record exists or not — nothing is disclosed.
    return shell(active, `<div class="ek-empty"><h1 class="ek-h2">Nie znaleziono rekordu</h1><p>Ten rekord nie istnieje albo nie masz do niego dostępu.</p><a class="ek-btn" href="#/${active}">Wróć do listy</a></div>`);
  }

  /* ---- Customer detail ---- */
  function screenCustomer(id) {
    const c = customer(id);
    if (!canSeeCustomer(c)) return noAccess("customers");
    const own = c.ownerId === S.viewerId;
    const visits = S.visits.filter((v) => v.customerId === c.id && canSeeVisit(v)).sort((a, b) => b.start.localeCompare(a.start));
    const notes = S.notes.filter((n) => n.customerId === c.id).sort((a, b) => b.at.localeCompare(a.at));
    const a = c.address;
    return shell("customers", `
      <a class="back" href="#/customers">${icon("back", "ek-icon--sm")}Klienci</a>
      <div class="page-head"><div class="page-head__titles"><h1 class="ek-h1">${esc(c.name)}</h1>
        <p class="ek-muted">${c.archived ? "Zarchiwizowany · " : ""}Opiekun: ${esc(userName(c.ownerId))}</p></div>
        <div class="ek-btn-row">
          ${own && !c.archived ? `<a class="ek-btn ek-btn--primary" href="#/visits/new?customer=${c.id}">${icon("plus")}Zaplanuj wizytę</a>` : ""}
          ${!c.archived ? `<a class="ek-btn" href="#/customers/${c.id}/edit">${icon("edit")}Edytuj</a>` : ""}
          ${c.archived ? `<button class="ek-btn" data-act="restore" data-id="${c.id}">${icon("restore")}Przywróć</button>` : `<button class="ek-btn ek-btn--ghost" data-act="archive" data-id="${c.id}">${icon("archive")}Archiwizuj</button>`}
        </div></div>
      <div class="cols">
        <div class="stack">
          <section class="ek-panel"><div class="ek-panel__head"><h2 class="ek-h3">Notatki i akcje</h2>
            ${isManager() && !own ? `<button class="ek-btn ek-btn--sm" data-act="note-customer" data-id="${c.id}">${icon("note", "ek-icon--sm")}Dodaj notatkę kierownika</button>` : ""}</div>
            <div class="ek-panel__body stack">${notes.length ? notes.map(noteBlock).join("") : `<p class="ek-muted">Notatki dodajesz po wizycie, z jej szczegółów.</p>`}</div></section>
          <section class="ek-panel"><div class="ek-panel__head"><h2 class="ek-h3">Wizyty</h2></div>
            ${visits.length ? `<ul class="ek-list">${visits.map(visitRow).join("")}</ul>` : `<div class="ek-panel__body"><p class="ek-muted">Brak wizyt.</p></div>`}</section>
        </div>
        <div class="stack">
          <section class="ek-panel"><div class="ek-panel__head"><h2 class="ek-h3">Kontakt</h2></div><div class="ek-panel__body">
            ${c.phones.map((p) => `<div class="ek-contact">${icon("phone")}<div><a class="ek-contact__value" href="tel:${p.value}">${D.formatPhone(p.value)}</a>${p.note ? `<div class="ek-contact__note">${esc(p.note)}</div>` : ""}</div>${p.primary ? '<span class="ek-contact__primary">główny</span>' : "<span></span>"}</div>`).join("")}
            ${c.emails.map((e) => `<div class="ek-contact">${icon("mail")}<div><span class="ek-contact__value">${esc(e.value)}</span>${e.note ? `<div class="ek-contact__note">${esc(e.note)}</div>` : ""}</div><button class="ek-btn ek-btn--ghost ek-btn--sm ek-btn--icon" data-act="copy" data-v="${esc(e.value)}" aria-label="Kopiuj adres">${icon("copy", "ek-icon--sm")}</button></div>`).join("")}
            ${!c.phones.length && !c.emails.length ? '<p class="ek-muted">Brak danych kontaktowych.</p>' : ""}
          </div></section>
          <section class="ek-panel"><div class="ek-panel__head"><h2 class="ek-h3">Dane</h2></div><div class="ek-panel__body">
            <dl class="ek-kv">
              <dt>Adres</dt><dd>${esc(addressLine(a)) || "—"}${addressLine(a) ? `<br><a class="ek-meta" href="${mapsUrl(addressLine(a))}" target="_blank" rel="noopener">Otwórz w Mapach Google</a>` : ""}</dd>
              <dt>Województwo</dt><dd>${esc(a.voivodeship) || "—"}</dd>
              <dt>Powiat</dt><dd>${esc(a.county) || "—"}</dd>
              <dt>NIP</dt><dd>${c.nip ? D.formatNip(c.nip) : "—"}</dd>
            </dl></div></section>
        </div>
      </div>`);
  }

  function visitRow(v) {
    const st = visitState(v);
    const c = customer(v.customerId);
    return `<li><a class="ek-row ek-row--link" href="#/visits/${v.id}">${icon("visits")}
      <span class="ek-row__main"><span class="ek-row__title">${relDay(v.start)}, ${t(v.start)}–${t(v.end)}</span><span class="ek-meta">${esc(c.name)}${isManager() ? ` · ${esc(userName(v.ownerId))}` : ""}</span></span>
      <span class="ek-row__aside">${flags(v)}${chip(st)}</span></a></li>`;
  }

  function noteBlock(n) {
    const v = n.visitId && S.visits.find((x) => x.id === n.visitId);
    const acts = S.actions.filter((a) => a.noteId === n.id);
    const author = S.users.find((u) => u.id === n.authorId);
    const canEdit = n.authorId === S.viewerId; // NOT-1, ACC-5: only the author edits
    const canAct = n.authorId === S.viewerId; // ACT-1: actions come from your own note
    return `<article class="ek-note ${author.role === "manager" ? "ek-note--manager" : ""}">
      <div class="ek-note__head"><strong>${esc(author.name)}</strong>${managerTag(n.authorId)}<span>${relDay(n.at)} ${t(n.at)}</span>${v ? `<a href="#/visits/${v.id}">wizyta ${dShort(v.start)}</a>` : ""}
        ${canEdit ? `<button class="ek-btn ek-btn--ghost ek-btn--sm" data-act="note-edit" data-id="${n.id}">Edytuj</button>` : ""}</div>
      <p class="ek-note__text">${esc(n.text)}</p>
      ${acts.length ? `<div class="stack stack--sm">${acts.map(actionCard).join("")}</div>` : ""}
      ${canAct ? `<div><button class="ek-btn ek-btn--sm" data-act="action-new" data-id="${n.id}">${icon("plus", "ek-icon--sm")}Dodaj akcję</button></div>` : ""}
    </article>`;
  }

  function actionCard(a) {
    const overdue = D.isOverdue(a, NOW);
    const c = customer(a.customerId);
    const allowed = D.allowedTransitions(a, viewer());
    const last = a.history[a.history.length - 1];
    return `<div class="ek-action ${overdue ? "ek-action--overdue" : ""}">
      <span class="ek-action__desc">${esc(a.desc)}</span>
      <span class="ek-row__aside">${overdue ? '<span class="ek-chip ek-chip--overdue">Zaległa</span>' : ""}${statusChip(a.status)}</span>
      <div class="ek-action__meta">
        <a href="#/customers/${c.id}">${esc(c.name)}</a>
        <span>${a.due ? `termin ${relDay(a.due + "T12:00:00")}` : "bez terminu"}</span>
        ${a.ownerId !== S.viewerId ? `<span>dla: ${esc(userName(a.ownerId))}</span>` : ""}
        ${a.authorId !== a.ownerId ? `<span>dodał(a): ${esc(userName(a.authorId))}</span>${managerTag(a.authorId)}` : ""}
        ${last ? `<span>status zmienił(a): ${esc(userName(last.by))}</span>${managerTag(last.by)}` : ""}
        ${allowed.length ? `<label class="ek-visually-hidden" for="st-${a.id}">Zmień status</label><select class="ek-select" id="st-${a.id}" data-act-status="${a.id}" style="width:auto;min-height:34px;padding:2px 8px;font-size:13px">
          <option value="">Zmień status…</option>${allowed.map((s) => `<option value="${s}">${D.ACTION_STATUS_LABEL[s]}</option>`).join("")}</select>` : ""}
      </div></div>`;
  }

  /* ---- Customer form (CUS-1 … CUS-8) ---- */
  function emptyDraft() {
    return { id: null, name: "", nip: "", address: { street: "", postalCode: "", town: "", voivodeship: "", county: "", country: "Polska" }, phones: [{ value: "", note: "", primary: true }], emails: [], ownerId: S.viewerId };
  }
  function screenCustomerForm(id) {
    if (id) { const c = customer(id); if (!canSeeCustomer(c)) return noAccess("customers"); }
    if (!S.draft || S.draft.id !== (id || null)) S.draft = id ? clone(customer(id)) : emptyDraft();
    const d = S.draft;
    const a = d.address;
    const counties = D.COUNTIES[a.voivodeship];
    const countries = ["Polska", "Niemcy", "Litwa", "Czechy", "Ukraina", "Inny"];
    return shell("customers", `
      <a class="back" href="${id ? "#/customers/" + id : "#/customers"}">${icon("back", "ek-icon--sm")}${id ? "Wróć do klienta" : "Klienci"}</a>
      <div class="page-head"><h1 class="ek-h1">${id ? "Edytuj klienta" : "Nowy klient"}</h1></div>
      <form class="stack" data-form="customer" novalidate style="max-width:820px">
        <div data-slot="conflict"></div>
        <fieldset class="ek-fieldset"><legend class="ek-fieldset__legend">Klient</legend>
          <div class="ek-form-grid">
            <div class="ek-field ek-form-grid__wide"><label class="ek-field__label" for="f-name">Nazwa</label><input class="ek-input" id="f-name" data-bind="name" value="${esc(d.name)}" autocomplete="off"><div data-err="name"></div></div>
            <div class="ek-field"><label class="ek-field__label" for="f-nip">NIP <span class="ek-muted">(opcjonalnie)</span></label><input class="ek-input" id="f-nip" data-bind="nip" value="${esc(d.nip)}" inputmode="numeric" placeholder="np. 778-104-51-22"><span class="ek-field__hint">${a.country === "Polska" ? "Myślniki, spacje i prefiks PL są usuwane." : "Zagraniczny numer podatkowy — bez sprawdzania."}</span><div data-err="nip"></div></div>
            ${isManager() ? `<div class="ek-field"><label class="ek-field__label" for="f-owner">Opiekun</label><select class="ek-select" id="f-owner" data-bind="ownerId">${S.users.filter((u) => u.role === "rep").map((u) => `<option value="${u.id}" ${d.ownerId === u.id ? "selected" : ""}>${esc(u.name)}</option>`).join("")}</select></div>` : ""}
          </div></fieldset>
        <fieldset class="ek-fieldset"><legend class="ek-fieldset__legend">Adres</legend>
          <div class="ek-form-grid">
            <div class="ek-field"><label class="ek-field__label" for="f-country">Kraj</label><select class="ek-select" id="f-country" data-bind="address.country" data-rerender>${countries.map((x) => `<option ${a.country === x ? "selected" : ""}>${x}</option>`).join("")}</select><div data-err="country"></div></div>
            <div class="ek-field ek-form-grid__wide"><label class="ek-field__label" for="f-street">Ulica i numer lub miejscowość i numer</label><input class="ek-input" id="f-street" data-bind="address.street" value="${esc(a.street)}"></div>
            <div class="ek-field"><label class="ek-field__label" for="f-pc">Kod pocztowy</label><input class="ek-input" id="f-pc" data-bind="address.postalCode" value="${esc(a.postalCode)}" ${a.country === "Polska" ? 'inputmode="numeric" placeholder="00-000"' : ""}><div data-err="postalCode"></div></div>
            <div class="ek-field"><label class="ek-field__label" for="f-town">Poczta / miejscowość</label><input class="ek-input" id="f-town" data-bind="address.town" value="${esc(a.town)}"></div>
            ${a.country === "Polska" ? `
            <div class="ek-field"><label class="ek-field__label" for="f-voi">Województwo</label><select class="ek-select" id="f-voi" data-bind="address.voivodeship" data-rerender><option value="">—</option>${D.VOIVODESHIPS.map((x) => `<option ${a.voivodeship === x ? "selected" : ""}>${x}</option>`).join("")}</select><div data-err="voivodeship"></div></div>
            <div class="ek-field"><label class="ek-field__label" for="f-county">Powiat</label>${counties
              ? `<select class="ek-select" id="f-county" data-bind="address.county"><option value="">—</option>${counties.map((x) => `<option ${a.county === x ? "selected" : ""}>${x}</option>`).join("")}</select>`
              : `<input class="ek-input" id="f-county" data-bind="address.county" value="${esc(a.county)}" ${a.voivodeship ? "" : "disabled"} placeholder="${a.voivodeship ? "" : "najpierw województwo"}">`}<span class="ek-field__hint">Lista powiatów w prototypie jest częściowa.</span><div data-err="county"></div></div>` : ""}
          </div></fieldset>
        <fieldset class="ek-fieldset"><legend class="ek-fieldset__legend">Telefony</legend>
          ${d.phones.map((p, i) => contactRow("phone", p, i)).join("")}
          <div><button class="ek-btn ek-btn--sm" type="button" data-act="contact-add" data-k="phones">${icon("plus", "ek-icon--sm")}Dodaj telefon</button></div></fieldset>
        <fieldset class="ek-fieldset"><legend class="ek-fieldset__legend">E-maile</legend>
          ${d.emails.map((e, i) => contactRow("email", e, i)).join("") || '<p class="ek-meta">Brak adresów e-mail.</p>'}
          <div><button class="ek-btn ek-btn--sm" type="button" data-act="contact-add" data-k="emails">${icon("plus", "ek-icon--sm")}Dodaj e-mail</button></div></fieldset>
        <div data-slot="warnings"></div>
        <div class="ek-btn-row"><button class="ek-btn ek-btn--primary" type="submit">${id ? "Zapisz zmiany" : "Dodaj klienta"}</button><a class="ek-btn ek-btn--ghost" href="${id ? "#/customers/" + id : "#/customers"}">Anuluj</a></div>
      </form>`);
  }
  function contactRow(kind, item, i) {
    const list = kind === "phone" ? "phones" : "emails";
    return `<div class="ek-form-grid" style="align-items:end">
      <div class="ek-field"><label class="ek-field__label" for="f-${kind}${i}">${kind === "phone" ? "Numer" : "Adres e-mail"}</label><input class="ek-input" id="f-${kind}${i}" data-bind="${list}.${i}.value" value="${esc(item.value)}" ${kind === "phone" ? 'inputmode="tel" placeholder="+48 600 100 200"' : 'inputmode="email"'}><div data-err="${kind}${i}"></div></div>
      <div class="ek-field"><label class="ek-field__label" for="f-${kind}n${i}">Do kogo <span class="ek-muted">(opcjonalnie)</span></label><input class="ek-input" id="f-${kind}n${i}" data-bind="${list}.${i}.note" value="${esc(item.note)}" placeholder="np. żona, biuro, wieczorem"></div>
      <div class="ek-btn-row">${kind === "phone" ? `<label class="ek-check"><input type="radio" name="primary" data-primary="${i}" ${item.primary ? "checked" : ""}>Główny</label>` : ""}
        <button class="ek-btn ek-btn--ghost ek-btn--sm" type="button" data-act="contact-remove" data-k="${list}" data-i="${i}">Usuń</button></div></div>`;
  }

  function bindDraft(form) {
    form.querySelectorAll("[data-bind]").forEach((el) => {
      const path = el.dataset.bind.split(".");
      let o = S.draft;
      for (let i = 0; i < path.length - 1; i++) o = o[path[i]];
      o[path[path.length - 1]] = el.value;
    });
    form.querySelectorAll("[data-primary]").forEach((el) => { S.draft.phones[Number(el.dataset.primary)].primary = el.checked; });
  }

  function validateCustomerForm(form, showAll) {
    bindDraft(form);
    const res = D.checkCustomer(S.draft, S.customers, viewer());
    form.querySelectorAll("[data-err]").forEach((slot) => {
      const k = slot.dataset.err;
      const input = slot.parentElement.querySelector(".ek-input, .ek-select");
      const touched = showAll || (input && input.dataset.touched);
      const msg = touched ? res.errors[k] : null;
      slot.innerHTML = msg ? `<span class="ek-field__error">${esc(msg)}</span>` : "";
      if (input) input.setAttribute("aria-invalid", msg ? "true" : "false");
    });
    form.querySelector('[data-slot="conflict"]').innerHTML = res.conflict
      ? `<div class="ek-banner ek-banner--warn" role="alert">${icon("alert")}<div class="ek-banner__body"><span class="ek-banner__title">${esc(res.conflict.message)}</span>${res.conflict.customerId ? `<a href="#/customers/${res.conflict.customerId}">Otwórz istniejącego klienta</a>` : "<span>Zapis jest zablokowany.</span>"}</div></div>` : "";
    form.querySelector('[data-slot="warnings"]').innerHTML = res.warnings.length
      ? `<div class="ek-banner ek-banner--decision">${icon("alert")}<div class="ek-banner__body"><span class="ek-banner__title">Możliwy duplikat — sprawdź przed zapisem</span>${res.warnings.map((w) => `<span>${esc(w)}</span>`).join("")}<span class="ek-meta">To tylko ostrzeżenie; możesz zapisać.</span></div></div>` : "";
    return res;
  }

  function saveCustomer(form) {
    const res = validateCustomerForm(form, true);
    if (Object.keys(res.errors).length || res.conflict) {
      const first = form.querySelector('[aria-invalid="true"]');
      if (first) first.focus();
      toast(res.conflict ? "Nie zapisano: NIP jest już w systemie." : "Popraw zaznaczone pola.");
      return;
    }
    const d = S.draft;
    d.nip = D.validateNip(d.nip, d.address.country).value;
    d.phones = d.phones.filter((p) => p.value).map((p) => ({ ...p, value: D.normalizePhone(p.value) }));
    d.emails = d.emails.filter((e) => e.value).map((e) => ({ ...e, value: D.validateEmail(e.value).value }));
    if (d.id) {
      Object.assign(customer(d.id), d);
      toast("Zapisano zmiany.");
    } else {
      d.id = uid("c"); d.archived = false;
      S.customers.push(d);
      toast("Dodano klienta.");
    }
    const target = d.id;
    S.draft = null;
    go("#/customers/" + target);
  }

  /* ---- Visits list ---- */
  function screenVisits() {
    const f = S.filters.visits;
    const all = myVisits();
    const list = (f === "upcoming" ? all.filter((v) => new Date(v.end) > NOW && !v.cancelled) : all.filter((v) => new Date(v.end) <= NOW || v.cancelled))
      .sort((a, b) => (f === "upcoming" ? a.start.localeCompare(b.start) : b.start.localeCompare(a.start)));
    return shell("visits", `
      <div class="page-head"><div class="page-head__titles"><h1 class="ek-h1">Wizyty</h1><p class="ek-muted">${isManager() ? "Wizyty całego zespołu. Planuje i zmienia je tylko właściciel wizyty." : "Każda wizyta trafia do Twojego kalendarza Google."}</p></div>
        ${!isManager() ? `<a class="ek-btn ek-btn--primary" href="#/visits/new">${icon("plus")}Zaplanuj wizytę</a>` : ""}</div>
      <div class="ek-seg" role="group" aria-label="Zakres"><button class="ek-seg__btn" data-act="filter" data-k="visits" data-v="upcoming" aria-pressed="${f === "upcoming"}">Nadchodzące</button><button class="ek-seg__btn" data-act="filter" data-k="visits" data-v="past" aria-pressed="${f === "past"}">Minione i odwołane</button></div>
      <section class="ek-panel">${list.length ? `<ul class="ek-list">${list.map(visitRow).join("")}</ul>` : `<div class="ek-panel__body"><div class="ek-empty"><p>Brak wizyt w tym widoku.</p></div></div>`}</section>`);
  }

  /* ---- Visit form (plan or move) ---- */
  function screenVisitForm(id, preCustomer) {
    const v = id && S.visits.find((x) => x.id === id);
    if (id && (!v || v.ownerId !== S.viewerId)) return noAccess("visits");
    if (isManager() && !id) return shell("visits", `<div class="ek-empty"><h1 class="ek-h2">Wizyty planuje handlowiec</h1><p>Wizyta żyje w kalendarzu Google jej właściciela, więc tylko on może ją zaplanować, przenieść lub odwołać.</p><a class="ek-btn" href="#/visits">Wróć do wizyt</a></div>`);
    const own = S.customers.filter((c) => c.ownerId === S.viewerId && !c.archived).sort((a, b) => a.name.localeCompare(b.name, "pl"));
    const selId = v ? v.customerId : preCustomer || "";
    const start = v ? new Date(v.start) : (() => { const d = new Date(NOW); d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0); return d; })();
    const dur = v ? Math.round((new Date(v.end) - new Date(v.start)) / 60000) : 60;
    const pad = (x) => String(x).padStart(2, "0");
    const dateVal = `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`;
    const timeVal = `${pad(start.getHours())}:${pad(start.getMinutes())}`;
    return shell("visits", `
      <a class="back" href="${v ? "#/visits/" + v.id : "#/visits"}">${icon("back", "ek-icon--sm")}${v ? "Wróć do wizyty" : "Wizyty"}</a>
      <div class="page-head"><h1 class="ek-h1">${v ? "Przenieś lub zmień wizytę" : "Zaplanuj wizytę"}</h1></div>
      <div class="cols">
        <form class="ek-panel ek-panel__body stack" data-form="visit" data-id="${v ? v.id : ""}">
          <div class="ek-field"><label class="ek-field__label" for="v-c">Klient</label>
            <select class="ek-select" id="v-c" name="customerId" required ${v ? "disabled" : ""}><option value="">Wybierz klienta</option>${own.map((c) => `<option value="${c.id}" ${c.id === selId ? "selected" : ""}>${esc(c.name)} — ${esc(c.address.town)}</option>`).join("")}</select>
            <span class="ek-field__hint">Tylko Twoi aktywni klienci.</span></div>
          <div class="ek-form-grid">
            <div class="ek-field"><label class="ek-field__label" for="v-d">Dzień</label><input class="ek-input" id="v-d" type="date" name="date" value="${dateVal}" required></div>
            <div class="ek-field"><label class="ek-field__label" for="v-t">Godzina</label><input class="ek-input" id="v-t" type="time" name="time" value="${timeVal}" step="900" required></div>
            <div class="ek-field"><label class="ek-field__label" for="v-dur">Czas trwania</label><select class="ek-select" id="v-dur" name="dur">${[30, 45, 60, 90, 120, 180].map((m) => `<option value="${m}" ${m === dur ? "selected" : ""}>${m < 60 ? m + " min" : m / 60 + " h"}</option>`).join("")}</select></div>
          </div>
          <div class="ek-field"><label class="ek-field__label" for="v-p">Miejsce, jeśli inne niż adres klienta</label><input class="ek-input" id="v-p" name="place" value="${esc(v ? v.place : "")}" placeholder="np. pole przy drodze na Rydzynę"></div>
          ${v ? `<p class="ek-meta">Zmiana dnia lub godziny oznaczy wizytę jako przeniesioną. Zmiana miejsca lub długości — nie.</p>` : ""}
          <div class="ek-btn-row"><button class="ek-btn ek-btn--primary" type="submit">${v ? "Zapisz zmiany" : "Zaplanuj wizytę"}</button><a class="ek-btn ek-btn--ghost" href="${v ? "#/visits/" + v.id : "#/visits"}">Anuluj</a></div>
        </form>
        <aside class="ek-panel" aria-labelledby="ev-h"><div class="ek-panel__head"><h2 class="ek-h3" id="ev-h">W Twoim kalendarzu Google</h2></div>
          <div class="ek-panel__body stack" data-slot="event-preview">${eventPreview(selId, v ? v.place : "")}</div></aside>
      </div>`);
  }
  /* VIS-3: what the calendar event will contain. */
  function eventPreview(customerId, place) {
    const c = customer(customerId);
    if (!c) return `<p class="ek-muted">Wybierz klienta, żeby zobaczyć wydarzenie.</p>`;
    const phone = c.phones.find((p) => p.primary) || c.phones[0];
    return `<div class="event-preview"><span class="event-preview__title">Wizyta: ${esc(c.name)}</span>
      <span>${icon("pin", "ek-icon--sm")} ${esc(place || addressLine(c.address) || "bez adresu")}</span>
      <span>${icon("phone", "ek-icon--sm")} ${phone ? D.formatPhone(phone.value) : "brak telefonu"}</span></div>
      <p class="ek-meta">Klient nie jest dodawany jako gość — nikt nie dostaje zaproszenia ani e-maila.</p>
      ${googleLinked() ? "" : `<p class="ek-meta">${icon("cloudOff", "ek-icon--sm")} Kalendarz nie jest połączony: wizyta zapisze się jako niezsynchronizowana.</p>`}`;
  }

  function saveVisit(form) {
    const fd = new FormData(form);
    const id = form.dataset.id;
    const v = id && S.visits.find((x) => x.id === id);
    const customerId = v ? v.customerId : fd.get("customerId");
    if (!customerId) { toast("Wybierz klienta."); form.querySelector("#v-c").focus(); return; }
    const start = new Date(`${fd.get("date")}T${fd.get("time")}:00`);
    if (isNaN(start)) { toast("Podaj dzień i godzinę."); return; }
    const end = new Date(start.getTime() + Number(fd.get("dur")) * 60000);
    const unsynced = !googleLinked();
    if (v) {
      if (new Date(v.start).getTime() !== start.getTime()) v.moved = true; // VIS-9
      Object.assign(v, { start: start.toISOString(), end: end.toISOString(), place: fd.get("place"), unsynced: v.unsynced || unsynced, deletedInGoogle: false });
      toast(unsynced ? "Zapisano. Do kalendarza trafi po ponownym połączeniu." : "Zapisano. Kalendarz Google zaktualizuje się w ciągu minuty.");
      go("#/visits/" + v.id);
    } else {
      const nv = { id: uid("v"), customerId, ownerId: S.viewerId, start: start.toISOString(), end: end.toISOString(), cancelled: false, deletedInGoogle: false, moved: false, unsynced, place: fd.get("place") };
      S.visits.push(nv);
      toast(unsynced ? "Wizyta zaplanowana. Do kalendarza trafi po połączeniu." : "Wizyta zaplanowana. W kalendarzu Google pojawi się w ciągu minuty.");
      go("#/visits/" + nv.id);
    }
  }

  /* ---- Visit detail ---- */
  function screenVisit(id) {
    const v = S.visits.find((x) => x.id === id);
    if (!canSeeVisit(v)) return noAccess("visits");
    const c = customer(v.customerId);
    const st = visitState(v);
    const own = v.ownerId === S.viewerId;
    const notes = S.notes.filter((n) => n.visitId === v.id).sort((a, b) => b.at.localeCompare(a.at));
    return shell("visits", `
      <a class="back" href="#/visits">${icon("back", "ek-icon--sm")}Wizyty</a>
      <div class="page-head"><div class="page-head__titles">
        <div class="ek-btn-row">${chip(st)}${flags(v)}</div>
        <h1 class="ek-h1">${esc(c.name)}</h1>
        <p class="ek-muted">${D.fmtDay.format(new Date(v.start))}, ${t(v.start)}–${t(v.end)}${!own ? ` · ${esc(userName(v.ownerId))}` : ""}</p></div>
        ${own && st !== "cancelled" ? `<div class="ek-btn-row">
          ${st === "awaiting" ? `<button class="ek-btn ek-btn--primary" data-act="decide" data-id="${v.id}">Zdecyduj</button>` : `<a class="ek-btn" href="#/visits/${v.id}/edit">${icon("moved")}Przenieś</a>`}
          ${st === "held" ? `<button class="ek-btn" data-act="not-held" data-id="${v.id}">Nie odbyła się</button>` : ""}
          ${st === "planned" ? `<button class="ek-btn ek-btn--ghost" data-act="visit-delete" data-id="${v.id}">Usuń</button>` : ""}
        </div>` : ""}</div>
      ${!own && isManager() ? `<div class="ek-banner ek-banner--info">${icon("visits")}<div class="ek-banner__body"><span>Wizytę może przenieść lub odwołać tylko ${esc(userName(v.ownerId))} — jest w jej/jego kalendarzu Google.</span></div></div>` : ""}
      <div class="cols">
        <section class="ek-panel"><div class="ek-panel__head"><h2 class="ek-h3">Notatki z wizyty</h2></div>
          <div class="ek-panel__body stack">
            ${notes.map(noteBlock).join("") || '<p class="ek-muted">Brak notatek. Notatkę możesz dodać przy każdym stanie wizyty.</p>'}
            ${own || isManager() ? `<form class="stack stack--sm" data-form="note" data-visit="${v.id}">
              <div class="ek-field"><label class="ek-field__label" for="n-text">Nowa notatka</label><textarea class="ek-textarea" id="n-text" name="text" placeholder="Co ustaliliście? Czego potrzebuje klient?"></textarea></div>
              <div><button class="ek-btn ek-btn--primary" type="submit">Dodaj notatkę</button></div></form>` : ""}
          </div></section>
        <div class="stack">
          <section class="ek-panel"><div class="ek-panel__head"><h2 class="ek-h3">Wydarzenie w Google</h2></div><div class="ek-panel__body stack">
            ${st === "awaiting" ? `<p>Wydarzenie usunięto w kalendarzu Google. Zdecyduj, czy przenieść wizytę, czy ją odwołać.</p>` : st === "cancelled" ? `<p class="ek-muted">Wizyta odwołana; wydarzenia nie ma w kalendarzu.</p>` : eventPreview(c.id, v.place)}
          </div></section>
          <section class="ek-panel"><div class="ek-panel__head"><h2 class="ek-h3">Klient</h2></div><div class="ek-panel__body stack stack--sm">
            <a href="#/customers/${c.id}"><strong>${esc(c.name)}</strong></a><span class="ek-meta">${esc(addressLine(c.address))}</span>
            ${c.phones[0] ? `<div><a class="ek-btn ek-btn--sm" href="tel:${c.phones[0].value}">${icon("phone", "ek-icon--sm")}${D.formatPhone(c.phones[0].value)}</a></div>` : ""}</div></section>
        </div>
      </div>`);
  }

  /* ---- Actions ---- */
  function screenActions() {
    const f = S.filters.actions;
    let list = myActions();
    if (f === "open") list = list.filter((a) => a.status === "todo" || a.status === "inprogress");
    if (f === "overdue") list = list.filter((a) => D.isOverdue(a, NOW));
    list = list.sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999"));
    return shell("actions", `
      <div class="page-head"><div class="page-head__titles"><h1 class="ek-h1">Akcje</h1><p class="ek-muted">${isManager() ? "Akcje całego zespołu. Akcje handlowców możesz tylko zamknąć." : "Twoje zadania z notatek po wizytach."}</p></div></div>
      <div class="ek-seg" role="group" aria-label="Filtr">
        ${[["open", "Otwarte"], ["overdue", "Zaległe"], ["all", "Wszystkie"]].map(([k, l]) => `<button class="ek-seg__btn" data-act="filter" data-k="actions" data-v="${k}" aria-pressed="${f === k}">${l}</button>`).join("")}</div>
      <div class="stack stack--sm" style="max-width:820px">${list.length ? list.map(actionCard).join("") : `<div class="ek-empty"><p>${f === "overdue" ? "Nic nie jest zaległe." : "Brak akcji. Akcję tworzysz z notatki po wizycie."}</p></div>`}</div>`);
  }

  /* ---- Team: reassignment (CUS-10, manager only) ---- */
  function screenTeam() {
    if (!isManager()) return noAccess("today");
    const reps = S.users.filter((u) => u.role === "rep");
    const from = S.filters.reassignFrom;
    const list = S.customers.filter((c) => !c.archived && (from === "all" || c.ownerId === from)).sort((a, b) => a.name.localeCompare(b.name, "pl"));
    const sel = [...S.selected].filter((id) => list.some((c) => c.id === id));
    return shell("team", `
      <div class="page-head"><div class="page-head__titles"><h1 class="ek-h1">Przypisania klientów</h1><p class="ek-muted">Przenieś klientów do innego handlowca. Razem z nimi przechodzą przyszłe wizyty i otwarte akcje.</p></div></div>
      <div class="toolbar"><select class="ek-select" data-filter="reassignFrom" style="width:auto" aria-label="Obecny opiekun"><option value="all">Wszyscy handlowcy</option>${reps.map((r) => `<option value="${r.id}" ${from === r.id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select>
        <span class="ek-meta" style="margin-left:auto">${sel.length ? `Zaznaczono: ${sel.length}` : "Zaznacz klientów na liście"}</span>
        <button class="ek-btn ek-btn--primary" data-act="reassign" ${sel.length ? "" : "disabled"}>${icon("team")}Przenieś zaznaczonych</button></div>
      <section class="ek-panel ek-table-wrap"><table class="ek-table">
        <thead><tr><th><span class="ek-visually-hidden">Zaznacz</span></th><th>Klient</th><th>Miejscowość</th><th>Opiekun</th><th class="ek-num">Przyszłe wizyty</th><th class="ek-num">Otwarte akcje</th></tr></thead>
        <tbody>${list.map((c) => `<tr><td><input type="checkbox" data-select="${c.id}" ${S.selected.has(c.id) ? "checked" : ""} aria-label="Zaznacz ${esc(c.name)}" style="width:18px;height:18px;accent-color:var(--ink)"></td>
          <td><a href="#/customers/${c.id}">${esc(c.name)}</a></td><td>${esc(c.address.town)}</td><td>${esc(userName(c.ownerId))}</td>
          <td class="ek-num">${S.visits.filter((v) => v.customerId === c.id && new Date(v.start) > NOW && !v.cancelled).length}</td>
          <td class="ek-num">${S.actions.filter((a) => a.customerId === c.id && (a.status === "todo" || a.status === "inprogress")).length}</td></tr>`).join("")}</tbody></table></section>`);
  }

  /* ---- Dashboard (DSH-*, after MVP) ---- */
  function periodRange(p) {
    const from = D.startOfDay(NOW), to = D.endOfDay(NOW);
    if (p === "week") { const wd = (from.getDay() + 6) % 7; from.setDate(from.getDate() - wd); to.setTime(D.endOfDay(new Date(from.getTime() + 6 * 86400000)).getTime()); }
    if (p === "month") { from.setDate(1); to.setTime(D.endOfDay(new Date(from.getFullYear(), from.getMonth() + 1, 0)).getTime()); }
    if (p === "quarter") { from.setMonth(Math.floor(from.getMonth() / 3) * 3, 1); to.setTime(D.endOfDay(new Date(from.getFullYear(), from.getMonth() + 3, 0)).getTime()); }
    if (p === "year") { from.setMonth(0, 1); to.setTime(D.endOfDay(new Date(from.getFullYear(), 11, 31)).getTime()); }
    return [from, to];
  }
  function screenDashboard() {
    const p = S.filters.period;
    const [from, to] = periodRange(p);
    // DSH-4/DSH-5: a rep sees only own visits; a visit counts for its owner.
    const scope = isManager() ? S.visits : S.visits.filter((v) => v.ownerId === S.viewerId);
    const tot = D.dashboardCounts(scope, from, to, NOW);
    const reps = S.users.filter((u) => u.role === "rep");
    const stat = (k, label, val) => `<div class="ek-panel ek-stat ek-stat--${k}"><span class="ek-stat__value">${val}</span><span class="ek-stat__label">${label}</span></div>`;
    return shell("dashboard", `
      <div class="page-head"><div class="page-head__titles"><h1 class="ek-h1">Pulpit wizyt</h1><p class="ek-muted">${D.fmtDateLong.format(from)} – ${D.fmtDateLong.format(to)}. ${isManager() ? "Cały zespół." : "Twoje wizyty."}</p></div>
        <span class="ek-flag">Etap po MVP</span></div>
      <div class="ek-seg" role="group" aria-label="Okres">${[["today", "Dziś"], ["week", "Ten tydzień"], ["month", "Ten miesiąc"], ["quarter", "Ten kwartał"], ["year", "Ten rok"]].map(([k, l]) => `<button class="ek-seg__btn" data-act="filter" data-k="period" data-v="${k}" aria-pressed="${p === k}">${l}</button>`).join("")}</div>
      <div class="stats">${stat("planned", "Zaplanowane (z odbytymi)", tot.planned)}${stat("held", "Odbyte", tot.held)}${stat("moved", "Przeniesione", tot.moved)}${stat("cancelled", "Odwołane", tot.cancelled)}${stat("awaiting", "Czekają na decyzję", tot.awaiting)}</div>
      ${isManager() ? `<section class="ek-panel ek-table-wrap"><table class="ek-table"><thead><tr><th>Handlowiec</th><th class="ek-num">Zaplanowane</th><th class="ek-num">Odbyte</th><th class="ek-num">Przeniesione</th><th class="ek-num">Odwołane</th><th class="ek-num">Czekają</th></tr></thead>
        <tbody>${reps.map((r) => { const c = D.dashboardCounts(S.visits.filter((v) => v.ownerId === r.id), from, to, NOW); return `<tr><td>${esc(r.name)}</td><td class="ek-num">${c.planned}</td><td class="ek-num">${c.held}</td><td class="ek-num">${c.moved}</td><td class="ek-num">${c.cancelled}</td><td class="ek-num">${c.awaiting}</td></tr>`; }).join("")}
        <tr><td><strong>Zespół</strong></td><td class="ek-num"><strong>${tot.planned}</strong></td><td class="ek-num"><strong>${tot.held}</strong></td><td class="ek-num"><strong>${tot.moved}</strong></td><td class="ek-num"><strong>${tot.cancelled}</strong></td><td class="ek-num"><strong>${tot.awaiting}</strong></td></tr></tbody></table></section>` : ""}
      <p class="ek-meta">Wizyta liczy się w okresie według aktualnego początku; odwołana — według ostatniego początku przed odwołaniem.</p>`);
  }

  /* ---- Settings: Google link (VIS-7, VIS-8) ---- */
  function screenSettings() {
    const u = viewer();
    const status = { linked: ["Połączony", "held"], expired: ["Dostęp wygasł", "overdue"], none: ["Niepołączony", "todo"] }[u.google];
    return shell("settings", `
      <div class="page-head"><h1 class="ek-h1">Konto i kalendarz</h1></div>
      <nav class="ek-panel" aria-label="Więcej" style="max-width:820px"><ul class="ek-list">
        ${isManager() ? `<li><a class="ek-row ek-row--link" href="#/team">${icon("team")}<span class="ek-row__main"><span class="ek-row__title">Przypisania klientów</span></span><span></span></a></li>` : ""}
        <li><a class="ek-row ek-row--link" href="#/dashboard">${icon("dashboard")}<span class="ek-row__main"><span class="ek-row__title">Pulpit wizyt</span><span class="ek-meta">Etap po MVP</span></span><span></span></a></li>
        <li><a class="ek-row ek-row--link" href="#/login" data-act="logout">${icon("logout")}<span class="ek-row__main"><span class="ek-row__title">Wyloguj</span></span><span></span></a></li>
      </ul></nav>
      <section class="ek-panel" style="max-width:820px"><div class="ek-panel__head"><h2 class="ek-h3">Kalendarz Google</h2><span class="ek-chip ek-chip--${status[1]}">${status[0]}</span></div>
        <div class="ek-panel__body stack">
          <p class="ek-note__text">Eko CRM zapisuje Twoje wizyty w głównym kalendarzu prywatnego konta Gmail. Inne wydarzenia z kalendarza nie są czytane ani zmieniane.</p>
          ${u.google === "linked" ? `<dl class="ek-kv"><dt>Konto</dt><dd>${esc(u.name.split(" ")[0].toLowerCase())}.demo@gmail.com</dd><dt>Kalendarz</dt><dd>główny</dd></dl>
            <p class="ek-meta">Odłączenie nie usuwa wydarzeń z Google. Nowe zmiany będą czekać, aż połączysz konto ponownie.</p>
            <div><button class="ek-btn" data-act="google-disconnect">Odłącz kalendarz</button></div>`
            : `<p class="ek-meta">${u.google === "expired" ? "W trybie testowym Google dostęp wygasa co 7 dni. Połącz ponownie, a zaległe zmiany się zsynchronizują." : "Bez połączenia wizyty działają, ale nie pojawiają się w kalendarzu."}</p>
            <div><button class="ek-btn ek-btn--primary" data-act="google-connect">${u.google === "expired" ? "Połącz ponownie" : "Połącz kalendarz Google"}</button></div>`}
        </div></section>`);
  }

  /* ================= Dialogs ================= */
  const dlg = document.getElementById("dlg");
  function openDialog(html, decision) {
    dlg.className = "ek-dialog" + (decision ? " ek-dialog--decision" : "");
    dlg.innerHTML = html;
    if (!dlg.open) dlg.showModal();
    const f = dlg.querySelector("[autofocus], input, textarea, select, button");
    if (f) f.focus();
  }
  const closeDialog = () => dlg.open && dlg.close();

  /* VIS-10 (delete in app) and VIS-11 (deleted in Google) share the two answers. */
  function decisionDialog(v, origin) {
    const c = customer(v.customerId);
    const title = origin === "google" ? "Wizytę usunięto w kalendarzu Google" : "Usuwasz wizytę";
    openDialog(`<form method="dialog" data-form="decision" data-id="${v.id}" data-origin="${origin}">
      <div class="ek-dialog__head"><h2 class="ek-h2" id="dlg-title">${title}</h2><p class="ek-muted">${esc(c.name)}, ${D.fmtDay.format(new Date(v.start))}, ${t(v.start)}. Co z nią zrobić?</p></div>
      <div class="ek-dialog__body">
        <label class="ek-choice"><input type="radio" name="choice" value="reschedule" checked><span class="ek-choice__title">Przenieś na inny termin</span><span class="ek-choice__hint">Wizyta zostanie oznaczona jako przeniesiona.</span></label>
        <label class="ek-choice"><input type="radio" name="choice" value="cancel"><span class="ek-choice__title">Odwołaj wizytę</span><span class="ek-choice__hint">Liczy się jako odwołana. Notatki zostają przy kliencie.</span></label>
      </div>
      <div class="ek-dialog__foot">${origin === "google" ? `<button class="ek-btn ek-btn--ghost" type="button" data-act="postpone">Zdecyduję później</button>` : `<button class="ek-btn ek-btn--ghost" type="button" data-act="dlg-close">Nie usuwaj</button>`}<button class="ek-btn ek-btn--primary" type="submit">Potwierdź</button></div></form>`, true);
  }

  function archiveDialog(c) {
    const future = S.visits.filter((v) => v.customerId === c.id && new Date(v.start) > NOW && !v.cancelled).length;
    const open = S.actions.filter((a) => a.customerId === c.id && (a.status === "todo" || a.status === "inprogress")).length;
    openDialog(`<form method="dialog" data-form="archive" data-id="${c.id}">
      <div class="ek-dialog__head"><h2 class="ek-h2" id="dlg-title">Archiwizować klienta ${esc(c.name)}?</h2></div>
      <div class="ek-dialog__body"><ul class="stack stack--sm" style="margin:0;padding-left:20px">
        <li>${future ? `${future} ${future === 1 ? "przyszła wizyta zostanie odwołana" : "przyszłe wizyty zostaną odwołane"} i ${future === 1 ? "usunięta" : "usunięte"} z kalendarza Google, bez pytania o nowy termin.` : "Klient nie ma przyszłych wizyt."}</li>
        <li>${open ? `${open} ${open === 1 ? "otwarta akcja zmieni" : "otwarte akcje zmienią"} status na Anulowane.` : "Klient nie ma otwartych akcji."}</li>
        <li>Odbyte wizyty i notatki zostają i dalej liczą się na pulpicie.</li>
        <li>Klienta można później przywrócić.</li></ul></div>
      <div class="ek-dialog__foot"><button class="ek-btn ek-btn--ghost" type="button" data-act="dlg-close">Anuluj</button><button class="ek-btn ek-btn--danger" type="submit">Archiwizuj</button></div></form>`);
  }

  function actionDialog(noteId) {
    openDialog(`<form method="dialog" data-form="action" data-note="${noteId}">
      <div class="ek-dialog__head"><h2 class="ek-h2" id="dlg-title">Nowa akcja</h2><p class="ek-muted">Akcja powstaje z notatki i trafia do przypomnień w dniu terminu.</p></div>
      <div class="ek-dialog__body">
        <div class="ek-field"><label class="ek-field__label" for="a-desc">Co trzeba zrobić</label><input class="ek-input" id="a-desc" name="desc" required autofocus></div>
        <div class="ek-field"><label class="ek-field__label" for="a-due">Termin <span class="ek-muted">(opcjonalnie)</span></label><input class="ek-input" id="a-due" name="due" type="date"><span class="ek-field__hint">Bez terminu akcja nie pojawi się w przypomnieniach.</span></div>
      </div>
      <div class="ek-dialog__foot"><button class="ek-btn ek-btn--ghost" type="button" data-act="dlg-close">Anuluj</button><button class="ek-btn ek-btn--primary" type="submit">Dodaj akcję</button></div></form>`);
  }

  function noteDialog({ noteId, customerId }) {
    const n = noteId && S.notes.find((x) => x.id === noteId);
    openDialog(`<form method="dialog" data-form="note-dlg" data-note="${noteId || ""}" data-customer="${customerId || ""}">
      <div class="ek-dialog__head"><h2 class="ek-h2" id="dlg-title">${n ? "Edytuj notatkę" : "Notatka kierownika"}</h2>${n ? "" : '<p class="ek-muted">Będzie widoczna jako Twoja przy kliencie.</p>'}</div>
      <div class="ek-dialog__body"><div class="ek-field"><label class="ek-field__label" for="nd-text">Treść</label><textarea class="ek-textarea" id="nd-text" name="text" required autofocus>${n ? esc(n.text) : ""}</textarea></div></div>
      <div class="ek-dialog__foot"><button class="ek-btn ek-btn--ghost" type="button" data-act="dlg-close">Anuluj</button><button class="ek-btn ek-btn--primary" type="submit">${n ? "Zapisz notatkę" : "Dodaj notatkę"}</button></div></form>`);
  }

  function reassignDialog() {
    const ids = [...S.selected];
    const reps = S.users.filter((u) => u.role === "rep");
    const future = S.visits.filter((v) => ids.includes(v.customerId) && new Date(v.start) > NOW && !v.cancelled).length;
    const open = S.actions.filter((a) => ids.includes(a.customerId) && (a.status === "todo" || a.status === "inprogress")).length;
    openDialog(`<form method="dialog" data-form="reassign">
      <div class="ek-dialog__head"><h2 class="ek-h2" id="dlg-title">Przenieś ${ids.length} ${ids.length === 1 ? "klienta" : "klientów"}</h2></div>
      <div class="ek-dialog__body">
        <div class="ek-field"><label class="ek-field__label" for="r-to">Nowy opiekun</label><select class="ek-select" id="r-to" name="to">${reps.map((r) => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select></div>
        <ul class="stack stack--sm" style="margin:0;padding-left:20px">
          <li>Przejdzie ${future} ${future === 1 ? "przyszła wizyta" : "przyszłych wizyt"} — wydarzenia przeniosą się do kalendarza nowego opiekuna. Nie liczą się jako przeniesione ani odwołane.</li>
          <li>Przejdzie ${open} ${open === 1 ? "otwarta akcja" : "otwartych akcji"}.</li>
          <li>Odbyte wizyty i notatki zostają przy dotychczasowym autorze.</li></ul></div>
      <div class="ek-dialog__foot"><button class="ek-btn ek-btn--ghost" type="button" data-act="dlg-close">Anuluj</button><button class="ek-btn ek-btn--primary" type="submit">Przenieś klientów</button></div></form>`);
  }

  /* ================= Events ================= */
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    const act = el.dataset.act, id = el.dataset.id;
    const handlers = {
      noop: () => { e.preventDefault(); toast("W produkcji link do zmiany hasła wysyła serwer tożsamości."); },
      "switch-user": () => { S.viewerId = id; S.draft = null; S.demoOpen = false; S.selected.clear(); S.filters.owner = "all"; if (location.hash.includes("login") || !location.hash) go("#/today"); render(); maybePrompt(); },
      logout: () => { e.preventDefault(); S.viewerId = null; closeDialog(); go("#/login"); render(); },
      "demo-toggle": () => { S.demoOpen = !S.demoOpen; render(); },
      theme: () => { const r = document.documentElement; const dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; r.dataset.theme = dark ? "light" : "dark"; },
      reset: () => { const keep = S.viewerId; S = freshState(); S.viewerId = keep; render(); toast("Dane demo przywrócone."); },
      "sim-google-delete": () => {
        const v = S.visits.filter((x) => x.ownerId === S.viewerId && visitState(x) === "planned").sort((a, b) => a.start.localeCompare(b.start))[0];
        if (!v) return toast("Brak zaplanowanych wizyt do usunięcia.");
        v.deletedInGoogle = true; S.demoOpen = false; render(); toast(`Symulacja: wydarzenie „Wizyta: ${customer(v.customerId).name}” usunięto w Google.`); maybePrompt();
      },
      filter: () => { const k = el.dataset.k; S.filters[k] = k === "archived" ? !!el.dataset.v : el.dataset.v; render(); },
      decide: () => decisionDialog(S.visits.find((v) => v.id === id), "google"),
      postpone: () => { S.postponedUntilNav = true; closeDialog(); toast("Przypomnimy przy następnym logowaniu. Baner zostaje na każdej stronie."); },
      "dlg-close": () => closeDialog(),
      "visit-delete": () => decisionDialog(S.visits.find((v) => v.id === id), "app"),
      "not-held": () => { const v = S.visits.find((x) => x.id === id); v.cancelled = true; render(); toast("Oznaczono: wizyta się nie odbyła. Liczy się jako odwołana."); },
      archive: () => archiveDialog(customer(id)),
      restore: () => { customer(id).archived = false; render(); toast("Przywrócono klienta."); },
      copy: () => { try { navigator.clipboard.writeText(el.dataset.v); toast("Skopiowano adres e-mail."); } catch (_) { toast(el.dataset.v); } },
      "action-new": () => actionDialog(id),
      "note-edit": () => noteDialog({ noteId: id }),
      "note-customer": () => noteDialog({ customerId: id }),
      "contact-add": () => { const form = el.closest("form"); bindDraft(form); S.draft[el.dataset.k].push({ value: "", note: "", primary: el.dataset.k === "phones" && !S.draft.phones.length }); render(); },
      "contact-remove": () => { const form = el.closest("form"); bindDraft(form); S.draft[el.dataset.k].splice(Number(el.dataset.i), 1); render(); },
      reassign: () => reassignDialog(),
      "google-connect": () => {
        const u = viewer(); u.google = "linked";
        const pending = S.visits.filter((v) => v.ownerId === u.id && v.unsynced);
        pending.forEach((v) => { v.unsynced = false; });
        render(); toast(pending.length ? `Połączono. Zsynchronizowano ${pending.length} ${pending.length === 1 ? "wizytę" : "wizyty"}.` : "Połączono kalendarz Google.");
      },
      "google-disconnect": () => { viewer().google = "none"; render(); toast("Odłączono kalendarz. Wydarzenia zostały w Google."); },
    };
    if (handlers[act]) handlers[act]();
  });

  document.addEventListener("submit", (e) => {
    const form = e.target;
    const kind = form.dataset.form;
    if (!kind) return;
    e.preventDefault();
    const fd = new FormData(form);
    if (kind === "login") { toast("Demo: wybierz osobę poniżej."); return; }
    if (kind === "customer") return saveCustomer(form);
    if (kind === "visit") return saveVisit(form);
    if (kind === "decision") {
      const v = S.visits.find((x) => x.id === form.dataset.id);
      closeDialog();
      if (fd.get("choice") === "cancel") { v.cancelled = true; v.deletedInGoogle = false; render(); toast("Wizyta odwołana."); }
      else { v.moved = true; v.deletedInGoogle = false; go("#/visits/" + v.id + "/edit"); toast("Wybierz nowy termin."); }
      return;
    }
    if (kind === "archive") {
      const c = customer(form.dataset.id);
      c.archived = true;
      // CUS-9: future visits cancelled without the prompt; open actions cancelled; nothing else changes.
      S.visits.filter((v) => v.customerId === c.id && new Date(v.start) > NOW).forEach((v) => { v.cancelled = true; });
      S.actions.filter((a) => a.customerId === c.id && (a.status === "todo" || a.status === "inprogress")).forEach((a) => { a.status = "cancelled"; a.history.push({ by: S.viewerId, to: "cancelled" }); });
      closeDialog(); render(); toast("Klient zarchiwizowany.");
      return;
    }
    if (kind === "note") {
      const text = String(fd.get("text") || "").trim();
      if (!text) { toast("Notatka jest pusta."); return; }
      const v = S.visits.find((x) => x.id === form.dataset.visit);
      S.notes.push({ id: uid("n"), visitId: v.id, customerId: v.customerId, authorId: S.viewerId, at: NOW.toISOString(), text });
      render(); toast("Dodano notatkę.");
      return;
    }
    if (kind === "note-dlg") {
      const text = String(fd.get("text") || "").trim();
      if (!text) return;
      if (form.dataset.note) S.notes.find((n) => n.id === form.dataset.note).text = text;
      else S.notes.push({ id: uid("n"), visitId: null, customerId: form.dataset.customer, authorId: S.viewerId, at: NOW.toISOString(), text });
      closeDialog(); render(); toast(form.dataset.note ? "Zapisano notatkę." : "Dodano notatkę.");
      return;
    }
    if (kind === "action") {
      const desc = String(fd.get("desc") || "").trim();
      if (!desc) { form.querySelector("#a-desc").setAttribute("aria-invalid", "true"); return; }
      const n = S.notes.find((x) => x.id === form.dataset.note);
      const c = customer(n.customerId);
      // ACT-1: owner = note author; for a manager's action, the customer's owner.
      const ownerId = viewer().role === "manager" ? c.ownerId : n.authorId;
      S.actions.push({ id: uid("a"), noteId: n.id, customerId: c.id, ownerId, authorId: S.viewerId, desc, due: fd.get("due") || null, status: "todo", history: [] });
      closeDialog(); render(); toast("Dodano akcję.");
      return;
    }
    if (kind === "reassign") {
      const to = fd.get("to");
      const ids = [...S.selected];
      ids.forEach((cid) => {
        customer(cid).ownerId = to;
        S.visits.filter((v) => v.customerId === cid && new Date(v.start) > NOW && !v.cancelled).forEach((v) => { v.ownerId = to; });
        S.actions.filter((a) => a.customerId === cid && (a.status === "todo" || a.status === "inprogress")).forEach((a) => { a.ownerId = to; });
      });
      S.selected.clear(); closeDialog(); render(); toast(`Przeniesiono ${ids.length} ${ids.length === 1 ? "klienta" : "klientów"} do: ${userName(to)}.`);
    }
  });

  document.addEventListener("change", (e) => {
    const el = e.target;
    if (el.dataset.actStatus) {
      const a = S.actions.find((x) => x.id === el.dataset.actStatus);
      const to = el.value;
      if (!to) return;
      if (!D.allowedTransitions(a, viewer()).includes(to)) { toast("Ta zmiana statusu jest niedozwolona."); return; } // ACT-2
      a.status = to; a.history.push({ by: S.viewerId, to });
      render(); toast(`Status: ${D.ACTION_STATUS_LABEL[to]}.`);
      return;
    }
    if (el.dataset.select) { el.checked ? S.selected.add(el.dataset.select) : S.selected.delete(el.dataset.select); render(); return; }
    if (el.dataset.filter) { S.filters[el.dataset.filter] = el.value; render(); return; }
    const form = el.closest('form[data-form="customer"]');
    if (form) {
      el.dataset.touched = "1";
      if (el.hasAttribute("data-rerender")) {
        bindDraft(form);
        if (el.dataset.bind === "address.voivodeship") S.draft.address.county = "";
        render();
      } else validateCustomerForm(form, false);
    }
    const vform = el.closest('form[data-form="visit"]');
    if (vform && el.name === "customerId") vform.parentElement.querySelector('[data-slot="event-preview"]').innerHTML = eventPreview(el.value, vform.querySelector("#v-p").value);
  });

  document.addEventListener("input", (e) => {
    if (e.target.dataset.filter === "q") {
      S.filters.q = e.target.value;
      const pos = e.target.selectionStart;
      render();
      const again = document.querySelector('[data-filter="q"]');
      again.focus(); again.setSelectionRange(pos, pos);
      return;
    }
    const form = e.target.closest('form[data-form="customer"]');
    if (form) validateCustomerForm(form, false);
  });
  document.addEventListener("focusout", (e) => {
    const form = e.target.closest && e.target.closest('form[data-form="customer"]');
    if (form && e.target.matches(".ek-input")) { e.target.dataset.touched = "1"; validateCustomerForm(form, false); }
  });

  /* VIS-11: the prompt opens after login; "later" closes it, the banner stays on every page and it
   * opens again at the next login until decided. */
  function maybePrompt() {
    const aw = awaiting();
    if (S.viewerId && aw.length && !S.postponedUntilNav && !dlg.open) decisionDialog(aw[0], "google");
  }

  /* ================= Render ================= */
  const root = document.getElementById("root");
  function render() {
    if (!S.viewerId) { root.innerHTML = screenLogin(); return; }
    const { parts, query } = route();
    const [a, b, c] = parts;
    let html;
    if (a === "customers" && b === "new") html = screenCustomerForm(null);
    else if (a === "customers" && b && c === "edit") html = screenCustomerForm(b);
    else if (a === "customers" && b) html = screenCustomer(b);
    else if (a === "customers") html = screenCustomers();
    else if (a === "visits" && b === "new") html = screenVisitForm(null, query.get("customer"));
    else if (a === "visits" && b && c === "edit") html = screenVisitForm(b);
    else if (a === "visits" && b) html = screenVisit(b);
    else if (a === "visits") html = screenVisits();
    else if (a === "actions") html = screenActions();
    else if (a === "team") html = screenTeam();
    else if (a === "dashboard") html = screenDashboard();
    else if (a === "settings") html = screenSettings();
    else html = screenToday();
    root.innerHTML = html;
    if (!(a === "customers" && (b === "new" || c === "edit"))) S.draft = null;
    else { const f = document.querySelector('form[data-form="customer"]'); if (f) validateCustomerForm(f, false); }
  }

  render();
})();
