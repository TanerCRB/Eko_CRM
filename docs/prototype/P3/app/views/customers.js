/* Customers: list, detail, form. */
import { t, fmtTime } from "../i18n.js";
import { icon } from "../icons.js";
import * as R from "../rules.js";
import { S, me, isManager, visibleCustomers, customer, canSeeCustomer, customerVisits, customerNotes, openTasksOf, reps, userName, stateOf, checkDraft, emptyDraft } from "../store.js";
import { shell } from "./shell.js";
import { esc, person, initials, stateChip, flags, noteBlock, visitRow, section, empty, mapsUrl, relDay, notice } from "../ui.js";

export function notFound(active) {
  return shell(active, empty(t("customers.notFoundTitle"), t("customers.notFoundBody"), `<a class="btn" href="#/${active}">${t("customers.backToList")}</a>`));
}

export function customersView() {
  const q = S.ui.q.trim().toLowerCase();
  const list = visibleCustomers()
    .filter((c) => c.archived === S.ui.archived)
    .filter((c) => !isManager() || S.ui.owner === "all" || c.ownerId === S.ui.owner)
    .filter((c) => !q || [c.name, c.address.town, c.nip, ...c.phones.map((p) => p.value)].join(" ").toLowerCase().includes(q))
    .sort((a, b) => a.name.localeCompare(b.name, "pl"));
  const rows = list.map((c) => {
    const next = S.visits.filter((v) => v.customerId === c.id && stateOf(v) === "planned").sort((a, b) => a.start.localeCompare(b.start))[0];
    const open = openTasksOf(c.id).length;
    return `<li><a class="row" data-link href="#/klienci/${c.id}"><span class="person">${initials(c.name)}</span>
      <span class="row__main"><span class="row__title">${esc(c.name)}</span><span class="t-meta">${esc(c.address.town || "")}${isManager() ? ` · ${esc(userName(c.ownerId))}` : ""}</span></span>
      <span class="row__aside">${next ? `<span class="t-meta">${relDay(next.start)} ${fmtTime(next.start)}</span>` : ""}${open ? `<span class="count" data-tone="quiet">${open}</span>` : ""}</span></a></li>`;
  }).join("");
  const emptyText = S.ui.q ? t("customers.noMatch", { q: esc(S.ui.q) }) : S.ui.archived ? t("customers.noArchived") : t("customers.none");
  return shell("klienci", `
    <div class="page__head"><div class="page__titles"><h1 class="page__title">${t("customers.title")}</h1><p class="page__sub">${isManager() ? t("customers.subAll") : t("customers.subMine")}</p></div>
      <a class="btn" data-kind="primary" href="#/klienci/nowy">${icon("plus")}${t("customers.add")}</a></div>
    <div class="toolbar">
      <label class="search"><span class="visually-hidden">${t("customers.search")}</span>${icon("search")}<input class="input" data-filter="q" value="${esc(S.ui.q)}" placeholder="${t("customers.search")}"></label>
      ${isManager() ? `<select class="select" data-filter="owner" style="width:auto" aria-label="${t("team.colOwner")}"><option value="all">${t("customers.allReps")}</option>${reps().map((r) => `<option value="${r.id}" ${S.ui.owner === r.id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select>` : ""}
      <div class="tabs" role="group"><button class="tabs__tab" data-do="tab" data-key="archived" data-value="" aria-pressed="${!S.ui.archived}">${t("customers.active")}</button><button class="tabs__tab" data-do="tab" data-key="archived" data-value="1" aria-pressed="${S.ui.archived}">${t("customers.archived")}</button></div>
    </div>
    ${list.length ? `<ul class="rows">${rows}</ul>` : empty(emptyText, "", `<a class="btn" href="#/klienci/nowy">${icon("plus")}${t("customers.add")}</a>`)}`);
}

export function customerView(id) {
  const c = customer(id);
  if (!canSeeCustomer(c)) return notFound("klienci");
  const own = c.ownerId === S.meId;
  const visits = customerVisits(c.id).sort((a, b) => b.start.localeCompare(a.start));
  const notes = customerNotes(c.id).sort((a, b) => b.at.localeCompare(a.at));
  const a = c.address;
  const line = R.addressLine(a);
  return shell("klienci", `
    <a class="crumb" href="#/klienci">${icon("back", "small")}${t("customers.title")}</a>
    <div class="page__head"><div class="page__titles"><h1 class="page__title">${esc(c.name)}</h1>
      <p class="page__sub">${c.archived ? `${t("customer.archivedTag")} · ` : ""}${t("customer.owner", { name: esc(userName(c.ownerId)) })}</p></div>
      <div class="btn-row">
        ${own && !c.archived ? `<a class="btn" data-kind="primary" href="#/wizyty/nowa?klient=${c.id}">${icon("plus")}${t("customer.plan")}</a>` : ""}
        ${!c.archived ? `<a class="btn" href="#/klienci/${c.id}/edycja">${icon("edit")}${t("action.edit")}</a>` : ""}
        ${c.archived ? `<button class="btn" data-do="restore" data-id="${c.id}">${icon("restore")}${t("customer.restore")}</button>` : `<button class="btn" data-kind="quiet" data-do="archive" data-id="${c.id}">${icon("archive")}${t("customer.archive")}</button>`}
      </div></div>
    <div class="two-col">
      <div class="stack">
        ${section(t("customer.notesTitle"), notes.length ? notes.map(noteBlock).join("") : `<p class="t-muted">${t("customer.noNotes")}</p>`,
          isManager() && !own ? `<button class="btn" data-size="small" data-do="note-manager" data-id="${c.id}">${icon("note", "small")}${t("customer.managerNote")}</button>` : "")}
        ${section(t("customer.visitsTitle"), visits.length ? `<ul class="rows">${visits.map(visitRow).join("")}</ul>` : `<p class="t-muted">${t("customer.noVisits")}</p>`)}
      </div>
      <div class="stack">
        ${section(t("customer.contactTitle"), `
          ${c.phones.map((p) => `<div class="contact">${icon("phone")}<div><a class="contact__value" href="tel:${p.value}">${R.formatPhone(p.value)}</a>${p.who ? `<div class="contact__who">${esc(p.who)}</div>` : ""}</div>${p.primary ? `<span class="contact__primary">${t("customer.primary")}</span>` : "<span></span>"}</div>`).join("")}
          ${c.emails.map((e) => `<div class="contact">${icon("mail")}<div><span class="contact__value">${esc(e.value)}</span>${e.who ? `<div class="contact__who">${esc(e.who)}</div>` : ""}</div><button class="btn" data-kind="quiet" data-size="icon" data-do="copy" data-arg="${esc(e.value)}" aria-label="${t("customer.copy")}">${icon("copy", "small")}</button></div>`).join("")}
          ${!c.phones.length && !c.emails.length ? `<p class="t-muted">${t("customer.noContact")}</p>` : ""}`)}
        ${section(t("customer.dataTitle"), `<dl class="kv">
          <dt>${t("customer.address")}</dt><dd>${esc(line) || "–"}${line ? `<br><a class="t-meta" href="${mapsUrl(line)}" target="_blank" rel="noopener">${t("customer.openMaps")}</a>` : ""}</dd>
          <dt>${t("customer.voivodeship")}</dt><dd>${esc(a.voivodeship) || "–"}</dd>
          <dt>${t("customer.county")}</dt><dd>${esc(a.county) || "–"}</dd>
          <dt>${t("customer.nip")}</dt><dd>${c.nip ? R.formatNip(c.nip) : "–"}</dd></dl>`)}
      </div>
    </div>`);
}

/* ---------- Form (CUS-1 … CUS-8) ---------- */
const COUNTRIES = ["Polska", "Niemcy", "Litwa", "Czechy", "Słowacja", "Ukraina", "Inny"];

export function customerFormView(id) {
  if (id && !canSeeCustomer(customer(id))) return notFound("klienci");
  if (!S.ui.draft || S.ui.draft.id !== (id ?? null)) S.ui.draft = id ? JSON.parse(JSON.stringify(customer(id))) : emptyDraft();
  const d = S.ui.draft;
  const a = d.address;
  const pl = a.country === R.POLAND;
  const counties = R.COUNTIES[a.voivodeship];
  const back = id ? `#/klienci/${id}` : "#/klienci";
  return shell("klienci", `
    <a class="crumb" href="${back}">${icon("back", "small")}${id ? t("form.backToCustomer") : t("customers.title")}</a>
    <div class="page__head"><h1 class="page__title">${id ? t("form.editTitle") : t("form.newTitle")}</h1></div>
    <form class="stack" data-form="customer" novalidate style="max-width:860px">
      <div data-slot="conflict"></div>
      <div class="form-section" style="border-top:0;padding-top:0"><h2 class="form-section__title">${t("form.sectionCustomer")}</h2>
        <div class="form-grid">
          <div class="field" data-span="full"><label class="field__label" for="f-name">${t("form.name")}</label><input class="input" id="f-name" data-bind="name" value="${esc(d.name)}" autocomplete="off"><div data-err="name"></div></div>
          <div class="field"><label class="field__label" for="f-nip">${t("form.nip")} <small>(${t("form.optional")})</small></label><input class="input" id="f-nip" data-bind="nip" value="${esc(d.nip)}" inputmode="numeric" placeholder="${t("form.nipPlaceholder")}"><span class="field__hint">${pl ? t("form.nipHintPl") : t("form.nipHintForeign")}</span><div data-err="nip"></div></div>
          ${isManager() ? `<div class="field"><label class="field__label" for="f-owner">${t("form.owner")}</label><select class="select" id="f-owner" data-bind="ownerId">${reps().map((r) => `<option value="${r.id}" ${d.ownerId === r.id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select></div>` : ""}
        </div></div>
      <div class="form-section"><h2 class="form-section__title">${t("form.sectionAddress")}</h2>
        <div class="form-grid">
          <div class="field"><label class="field__label" for="f-country">${t("form.country")}</label><select class="select" id="f-country" data-bind="address.country" data-rerender>${COUNTRIES.map((x) => `<option ${a.country === x ? "selected" : ""}>${x}</option>`).join("")}</select><div data-err="country"></div></div>
          <div class="field" data-span="full"><label class="field__label" for="f-street">${t("form.street")}</label><input class="input" id="f-street" data-bind="address.street" value="${esc(a.street)}"></div>
          <div class="field"><label class="field__label" for="f-postal">${t("form.postal")}</label><input class="input" id="f-postal" data-bind="address.postalCode" value="${esc(a.postalCode)}" ${pl ? 'inputmode="numeric" placeholder="00-000"' : ""}><div data-err="postalCode"></div></div>
          <div class="field"><label class="field__label" for="f-town">${t("form.town")}</label><input class="input" id="f-town" data-bind="address.town" value="${esc(a.town)}"></div>
          ${pl ? `
          <div class="field"><label class="field__label" for="f-voi">${t("form.voivodeship")}</label><select class="select" id="f-voi" data-bind="address.voivodeship" data-rerender><option value="">–</option>${R.VOIVODESHIPS.map((x) => `<option ${a.voivodeship === x ? "selected" : ""}>${x}</option>`).join("")}</select><div data-err="voivodeship"></div></div>
          <div class="field"><label class="field__label" for="f-county">${t("form.county")}</label>${counties
            ? `<select class="select" id="f-county" data-bind="address.county"><option value="">–</option>${counties.map((x) => `<option ${a.county === x ? "selected" : ""}>${x}</option>`).join("")}</select>`
            : `<input class="input" id="f-county" data-bind="address.county" value="${esc(a.county)}" ${a.voivodeship ? "" : "disabled"} placeholder="${a.voivodeship ? "" : t("form.countyFirst")}">`}<span class="field__hint">${t("form.countyPartial")}</span><div data-err="county"></div></div>` : ""}
        </div></div>
      <div class="form-section"><h2 class="form-section__title">${t("form.sectionPhones")}</h2>
        ${d.phones.map((p, i) => contactFields("phone", p, i)).join("")}
        <div><button class="btn" data-size="small" type="button" data-do="contact-add" data-kind-list="phones">${icon("plus", "small")}${t("form.addPhone")}</button></div></div>
      <div class="form-section"><h2 class="form-section__title">${t("form.sectionEmails")}</h2>
        ${d.emails.map((e, i) => contactFields("email", e, i)).join("") || `<p class="t-meta">${t("form.noEmails")}</p>`}
        <div><button class="btn" data-size="small" type="button" data-do="contact-add" data-kind-list="emails">${icon("plus", "small")}${t("form.addEmail")}</button></div></div>
      <div data-slot="warnings"></div>
      <div class="btn-row"><button class="btn" data-kind="primary" type="submit">${id ? t("form.submitEdit") : t("form.submitNew")}</button><a class="btn" data-kind="quiet" href="${back}">${t("action.cancel")}</a></div>
    </form>`);
}

function contactFields(kind, item, i) {
  const list = kind === "phone" ? "phones" : "emails";
  return `<div class="form-grid" style="align-items:end">
    <div class="field"><label class="field__label" for="f-${kind}${i}">${kind === "phone" ? t("form.phone") : t("form.email")}</label><input class="input" id="f-${kind}${i}" data-bind="${list}.${i}.value" value="${esc(item.value)}" ${kind === "phone" ? 'inputmode="tel" placeholder="+48 600 100 200"' : 'inputmode="email"'}><div data-err="${kind}${i}"></div></div>
    <div class="field"><label class="field__label" for="f-${kind}who${i}">${t("form.who")} <small>(${t("form.optional")})</small></label><input class="input" id="f-${kind}who${i}" data-bind="${list}.${i}.who" value="${esc(item.who)}" placeholder="${t("form.whoPlaceholder")}"></div>
    <div class="btn-row">${kind === "phone" ? `<label class="check"><input type="radio" name="primary" data-primary="${i}" ${item.primary ? "checked" : ""}>${t("form.primary")}</label>` : ""}
      <button class="btn" data-kind="quiet" data-size="small" type="button" data-do="contact-remove" data-kind-list="${list}" data-index="${i}">${t("action.remove")}</button></div></div>`;
}

/* Read the inputs into the draft. */
export function bindDraft(form) {
  const d = S.ui.draft;
  form.querySelectorAll("[data-bind]").forEach((el) => {
    const path = el.dataset.bind.split(".");
    let o = d;
    for (let i = 0; i < path.length - 1; i++) o = o[path[i]];
    o[path[path.length - 1]] = el.value;
  });
  form.querySelectorAll("[data-primary]").forEach((el) => { d.phones[Number(el.dataset.primary)].primary = el.checked; });
}

/* Show codes as words; only touched fields show errors until submit. */
export function validateForm(form, showAll) {
  bindDraft(form);
  const res = checkDraft(S.ui.draft);
  form.querySelectorAll("[data-err]").forEach((slot) => {
    const k = slot.dataset.err;
    const input = slot.parentElement.querySelector(".input, .select");
    const show = showAll || (input && input.dataset.touched);
    const code = show ? res.codes[k] : null;
    slot.innerHTML = code ? `<span class="field__error">${t("err." + code)}</span>` : "";
    if (input) input.setAttribute("aria-invalid", code ? "true" : "false");
  });
  form.querySelector('[data-slot="conflict"]').innerHTML = res.conflict
    ? notice("blocked", "alert", t("conflict." + res.conflict.code), res.conflict.customerId ? `<a href="#/klienci/${res.conflict.customerId}">${t("form.conflictOpen")}</a>` : t("form.conflictBlocked")) : "";
  form.querySelector('[data-slot="warnings"]').innerHTML = res.warnings.length
    ? notice("warning", "alert", t("form.dupTitle"), res.warnings.map((w) => t("warn." + w.code, { name: esc(w.name), town: esc(w.town) })).join("<br>") + `<br><span class="t-meta">${t("form.dupHint")}</span>`) : "";
  return res;
}
