/*
 * Eko_CRM prototype P3 — translation helper.
 * t(key, vars) reads the active catalogue; a value that is an array of three forms is picked by
 * the Polish plural rule from vars.n. Formatters use Intl with the "pl-PL" locale, so a second
 * language changes the locale tag and the catalogue, nothing else.
 */
import pl from "../i18n/pl.js";

let dict = pl;
let locale = "pl-PL";

/** Polish plural categories: 0 = one, 1 = few (2–4 except 12–14), 2 = many. */
export function pluralIndex(n) {
  const abs = Math.abs(n);
  if (abs === 1) return 0;
  const m10 = abs % 10, m100 = abs % 100;
  if (m10 >= 2 && m10 <= 4 && !(m100 >= 12 && m100 <= 14)) return 1;
  return 2;
}

export function t(key, vars = {}) {
  let s = dict[key];
  if (s === undefined) return key; // a missing key shows itself, so it gets noticed in review
  if (Array.isArray(s)) s = s[pluralIndex(Number(vars.n) || 0)];
  return s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] === undefined ? "" : String(vars[k])));
}

export function setCatalogue(nextDict, nextLocale) { dict = nextDict; locale = nextLocale; }
export const getLocale = () => locale;

const fmt = (opts) => new Intl.DateTimeFormat(locale, opts);
export const fmtTime = (d) => fmt({ hour: "2-digit", minute: "2-digit" }).format(new Date(d));
export const fmtDayLong = (d) => fmt({ weekday: "long", day: "numeric", month: "long" }).format(new Date(d));
export const fmtDayShort = (d) => fmt({ day: "numeric", month: "short" }).format(new Date(d));
export const fmtDateFull = (d) => fmt({ day: "numeric", month: "long", year: "numeric" }).format(new Date(d));
export const fmtDow = (d) => fmt({ weekday: "short" }).format(new Date(d));
export const fmtDowLong = (d) => fmt({ weekday: "long" }).format(new Date(d));
export const fmtMonthYear = (d) => fmt({ month: "long", year: "numeric" }).format(new Date(d));
