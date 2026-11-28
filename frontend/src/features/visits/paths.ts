// Fixed SPA locations of the visit screens; no visit value or date ever goes into one
// (ADR-0005-C13).
export const MY_DAY_PATH = "/moj-dzien";
export const VISITS_PATH = "/wizyty";
export const PLAN_VISIT_PATH = "/wizyty/nowa";

export function isVisitsPath(path: string): boolean {
  return path === MY_DAY_PATH || path === VISITS_PATH || path.startsWith(`${VISITS_PATH}/`);
}
