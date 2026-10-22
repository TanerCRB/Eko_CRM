/*
 * Eko_CRM domain rules — prototype P1 (plain JS, no build step).
 * Mirrors ../handoff/domain.ts, which is the version meant for frontend/src.
 * Rules are cited by requirement identifier from docs/product/project-brief.md.
 * The server stays the authority (CUS-3, ACT-2): these functions are for instant form feedback.
 */
(function (global) {
  "use strict";

  const VOIVODESHIPS = [
    "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "łódzkie", "małopolskie",
    "mazowieckie", "opolskie", "podkarpackie", "podlaskie", "pomorskie", "śląskie",
    "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie",
  ];

  // Partial county list for the prototype; production needs the full TERYT register (380 entries).
  const COUNTIES = {
    "wielkopolskie": ["gnieźnieński", "kaliski", "kościański", "leszczyński", "poznański", "wrzesiński"],
    "kujawsko-pomorskie": ["bydgoski", "inowrocławski", "toruński", "włocławski"],
    "lubelskie": ["bialski", "chełmski", "lubelski", "zamojski"],
    "mazowieckie": ["ciechanowski", "płocki", "radomski", "siedlecki"],
    "podlaskie": ["białostocki", "łomżyński", "suwalski"],
  };

  /* ---- NIP (CUS-5) ---- */
  const NIP_WEIGHTS = [6, 5, 7, 2, 3, 4, 5, 6, 7];

  function normalizeNip(raw) {
    return String(raw || "").replace(/^\s*PL/i, "").replace(/[\s-]/g, "");
  }

  /** @returns {{ok: true, value: string} | {ok: false, error: string}} */
  function validateNip(raw, country) {
    if (!raw || !String(raw).trim()) return { ok: true, value: "" };
    if (country && country !== "Polska") return { ok: true, value: String(raw).trim() }; // foreign tax ID: free text
    const v = normalizeNip(raw);
    if (!/^\d{10}$/.test(v)) return { ok: false, error: "NIP ma 10 cyfr. Myślniki, spacje i prefiks PL są pomijane." };
    const sum = NIP_WEIGHTS.reduce((s, w, i) => s + w * Number(v[i]), 0) % 11;
    if (sum === 10 || sum !== Number(v[9])) return { ok: false, error: "Ten NIP ma błędną cyfrę kontrolną. Sprawdź, czy nie ma literówki." };
    return { ok: true, value: v };
  }

  /** Builds a valid NIP from 9 digits (seed helper). Returns null when no check digit exists. */
  function makeNip(nine) {
    const sum = NIP_WEIGHTS.reduce((s, w, i) => s + w * Number(nine[i]), 0) % 11;
    return sum === 10 ? null : nine + sum;
  }

  function formatNip(v) {
    return v && v.length === 10 ? `${v.slice(0, 3)}-${v.slice(3, 6)}-${v.slice(6, 8)}-${v.slice(8)}` : v;
  }

  /* ---- Address (CUS-3, CUS-4) ---- */
  function validateAddress(a) {
    const errors = {};
    if (a.country === "Polska") {
      if (a.postalCode && !/^\d{2}-\d{3}$/.test(a.postalCode)) errors.postalCode = "Kod pocztowy w formacie 00-000.";
      if (a.voivodeship && !VOIVODESHIPS.includes(a.voivodeship)) errors.voivodeship = "Wybierz jedno z 16 województw.";
      if (a.county) {
        if (!a.voivodeship) errors.county = "Najpierw wybierz województwo.";
        else if (COUNTIES[a.voivodeship] && !COUNTIES[a.voivodeship].includes(a.county)) errors.county = "Ten powiat nie leży w wybranym województwie.";
      }
    }
    return errors;
  }

  /* ---- Contacts (CUS-8) ---- */
  function normalizePhone(raw) {
    let v = String(raw || "").replace(/[\s()-]/g, "");
    if (!v) return "";
    if (v.startsWith("00")) v = "+" + v.slice(2);
    if (!v.startsWith("+")) v = "+48" + v;
    return v;
  }
  function validatePhone(raw) {
    const v = normalizePhone(raw);
    return /^\+\d{8,15}$/.test(v) ? { ok: true, value: v } : { ok: false, error: "Numer w formacie międzynarodowym, np. +48 600 100 200." };
  }
  function formatPhone(v) {
    const m = /^\+48(\d{3})(\d{3})(\d{3})$/.exec(v || "");
    return m ? `+48 ${m[1]} ${m[2]} ${m[3]}` : v;
  }
  function validateEmail(raw) {
    const v = String(raw || "").trim();
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) ? { ok: true, value: v.toLowerCase() } : { ok: false, error: "Adres e-mail wygląda na niepełny." };
  }

  /* ---- Customer validation (CUS-2, CUS-6, CUS-7) ---- */
  /**
   * @param draft customer draft
   * @param all every customer the server knows (to simulate uniqueness)
   * @param viewer {id, role}
   * @returns {{errors: object, warnings: string[], conflict: null | {customerId, message}}}
   */
  function checkCustomer(draft, all, viewer) {
    const errors = {};
    const warnings = [];
    let conflict = null;
    if (!draft.name || !draft.name.trim()) errors.name = "Podaj nazwę klienta.";
    if (!draft.address.country) errors.country = "Podaj kraj.";
    Object.assign(errors, validateAddress(draft.address));
    const nip = validateNip(draft.nip, draft.address.country);
    if (!nip.ok) errors.nip = nip.error;
    draft.phones.forEach((p, i) => { if (p.value && !validatePhone(p.value).ok) errors["phone" + i] = validatePhone(p.value).error; });
    draft.emails.forEach((e, i) => { if (e.value && !validateEmail(e.value).ok) errors["email" + i] = validateEmail(e.value).error; });

    const others = all.filter((c) => c.id !== draft.id);
    if (nip.ok && nip.value) {
      const hit = others.find((c) => c.nip === nip.value);
      if (hit) {
        // ACC-8: the rep learns nothing about the other customer or its owner.
        conflict = viewer.role === "manager"
          ? { customerId: hit.id, message: "Klient z tym NIP już istnieje." }
          : { customerId: null, message: "Klient z tym NIP już istnieje — skontaktuj się z kierownikiem." };
      }
    }
    // CUS-7: a rep is warned only within their own customers.
    const scope = viewer.role === "manager" ? others : others.filter((c) => c.ownerId === viewer.id);
    const key = (s) => String(s || "").trim().toLowerCase();
    const phones = draft.phones.map((p) => normalizePhone(p.value)).filter(Boolean);
    const emails = draft.emails.map((e) => key(e.value)).filter(Boolean);
    scope.forEach((c) => {
      if (c.phones.some((p) => phones.includes(p.value))) warnings.push(`Ten sam numer telefonu ma klient „${c.name}”.`);
      if (c.emails.some((e) => emails.includes(e.value))) warnings.push(`Ten sam e-mail ma klient „${c.name}”.`);
      if (key(c.name) === key(draft.name) && key(c.address.town) && key(c.address.town) === key(draft.address.town)) warnings.push(`Klient „${c.name}” w miejscowości ${c.address.town} już istnieje.`);
    });
    return { errors, warnings, conflict };
  }

  /* ---- Visit state (glossary, VIS-*) ---- */
  /** @returns {"planned"|"held"|"cancelled"|"awaiting"} derived, never stored except cancelled/awaiting */
  function visitState(v, now) {
    if (v.cancelled) return "cancelled";
    if (v.deletedInGoogle) return "awaiting";
    return new Date(v.end) <= now ? "held" : "planned";
  }
  const VISIT_STATE_LABEL = { planned: "Zaplanowana", held: "Odbyta", cancelled: "Odwołana", awaiting: "Czeka na decyzję" };

  /* ---- Action status (ACT-2, ACT-3) ---- */
  const ACTION_STATUS_LABEL = { todo: "Do zrobienia", inprogress: "W toku", done: "Zrobione", cancelled: "Anulowane" };
  const TRANSITIONS = {
    todo: ["inprogress", "done", "cancelled"],
    inprogress: ["done", "cancelled", "todo"],
    done: ["todo"],
    cancelled: ["todo"],
  };
  /** ACC-5: the manager may only close (done/cancelled) someone else's action. */
  function allowedTransitions(action, viewer) {
    const next = TRANSITIONS[action.status] || [];
    if (viewer.role === "manager" && action.ownerId !== viewer.id) return next.filter((s) => s === "done" || s === "cancelled");
    if (viewer.role !== "manager" && action.ownerId !== viewer.id) return [];
    return next;
  }
  function isOverdue(action, now) {
    if (!action.due || action.status === "done" || action.status === "cancelled") return false;
    return endOfDay(action.due) < now;
  }
  /** ACT-4: due today or earlier, not closed, has a due date. */
  function isReminder(action, now) {
    if (!action.due || action.status === "done" || action.status === "cancelled") return false;
    return startOfDay(action.due) <= now;
  }

  /* ---- Dashboard (DSH-2, DSH-3) ---- */
  function dashboardCounts(visits, from, to, now) {
    const inRange = visits.filter((v) => {
      const t = new Date(v.start);
      return t >= from && t <= to;
    });
    const c = { planned: 0, held: 0, moved: 0, cancelled: 0, awaiting: 0 };
    inRange.forEach((v) => {
      const s = visitState(v, now);
      if (s === "cancelled") c.cancelled++;
      else if (s === "awaiting") c.awaiting++;
      else { c.planned++; if (s === "held") c.held++; }
      if (v.moved) c.moved++;
    });
    return c;
  }

  /* ---- Dates (Europe/Warsaw; the prototype uses the browser zone) ---- */
  function startOfDay(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
  function endOfDay(d) { const x = new Date(d); x.setHours(23, 59, 59, 999); return x; }
  const fmtTime = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit" });
  const fmtDay = new Intl.DateTimeFormat("pl-PL", { weekday: "long", day: "numeric", month: "long" });
  const fmtDate = new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "short" });
  const fmtDateLong = new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long", year: "numeric" });

  global.EkoDomain = {
    VOIVODESHIPS, COUNTIES, VISIT_STATE_LABEL, ACTION_STATUS_LABEL, TRANSITIONS,
    normalizeNip, validateNip, makeNip, formatNip, validateAddress,
    normalizePhone, validatePhone, formatPhone, validateEmail, checkCustomer,
    visitState, allowedTransitions, isOverdue, isReminder, dashboardCounts,
    startOfDay, endOfDay, fmtTime, fmtDay, fmtDate, fmtDateLong,
  };
})(window);
