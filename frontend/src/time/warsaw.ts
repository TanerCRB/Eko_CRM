// The frontend's one source of "now", "today" and Europe/Warsaw dates and wall times (ADR-0001
// Constraint 3, C13, C14). Every instant is read and shown in Europe/Warsaw, named explicitly, so
// a device in another zone shows the same days and hours. Days are counted on the calendar, never
// by adding 24 hours to an instant: Warsaw has 23- and 25-hour days. Imports no frontend layer.

export const WARSAW_ZONE = "Europe/Warsaw";

// A Europe/Warsaw calendar date written `YYYY-MM-DD`.
export type CalendarDate = string;

export interface DateRange {
  first: CalendarDate;
  last: CalendarDate;
}

const CALENDAR_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
// RFC 3339 with an explicit offset, as the API answers an instant (ADR-0001 Constraint 3).
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/i;
// Display copy is Polish (the SPA's one locale); the parts read for data use a fixed locale with
// Latin digits, so no result depends on the browser's locale.
const DISPLAY_LOCALE = "pl-PL";

const wallClockParts = new Intl.DateTimeFormat("en-US", {
  timeZone: WARSAW_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
  numberingSystem: "latn",
});
const longDate = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: WARSAW_ZONE,
  day: "numeric",
  month: "long",
  year: "numeric",
});
const dayAndMonth = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: WARSAW_ZONE,
  day: "numeric",
  month: "long",
});
const wallTime = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: WARSAW_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const weekdayLong = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: WARSAW_ZONE,
  weekday: "long",
});
const weekdayShort = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: WARSAW_ZONE,
  weekday: "short",
});

// The one read of the browser's clock (ADR-0001 addendum 2026-10-29).
export function nowInstant(): number {
  return Date.now();
}

export function isCalendarDate(value: string): boolean {
  const parts = CALENDAR_DATE.exec(value);
  if (parts === null) {
    return false;
  }
  const [year, month, day] = [Number(parts[1]), Number(parts[2]), Number(parts[3])];
  const noon = new Date(Date.UTC(year, month - 1, day, 12));
  return (
    noon.getUTCFullYear() === year && noon.getUTCMonth() === month - 1 && noon.getUTCDate() === day
  );
}

export function isInstant(value: string): boolean {
  return INSTANT.test(value) && Number.isFinite(Date.parse(value));
}

function epochOf(instant: number | string): number {
  return typeof instant === "number" ? instant : Date.parse(instant);
}

function calendarParts(date: CalendarDate): [number, number, number] {
  const parts = CALENDAR_DATE.exec(date);
  if (parts === null || !isCalendarDate(date)) {
    throw new RangeError("not a calendar date (YYYY-MM-DD)");
  }
  return [Number(parts[1]), Number(parts[2]), Number(parts[3])];
}

function calendarDateOfUtcDay(epoch: number): CalendarDate {
  const day = new Date(epoch);
  const month = String(day.getUTCMonth() + 1).padStart(2, "0");
  const date = String(day.getUTCDate()).padStart(2, "0");
  return `${String(day.getUTCFullYear()).padStart(4, "0")}-${month}-${date}`;
}

const WALL_PARTS = ["year", "month", "day", "hour", "minute", "second"] as const;
type WallPart = (typeof WALL_PARTS)[number];

function isWallPart(type: string): type is WallPart {
  return WALL_PARTS.some((part) => part === type);
}

function wallClock(epoch: number): Record<WallPart, number> {
  const found: Record<WallPart, number> = { year: 0, month: 0, day: 0, hour: 0, minute: 0, second: 0 };
  for (const part of wallClockParts.formatToParts(epoch)) {
    if (isWallPart(part.type)) {
      found[part.type] = Number(part.value);
    }
  }
  return found;
}

// Warsaw's offset from UTC at an instant on a whole second, in milliseconds.
function offsetAt(epoch: number): number {
  const wall = wallClock(epoch);
  return Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute, wall.second) - epoch;
}

export function warsawDateOf(instant: number | string): CalendarDate {
  const wall = wallClock(epochOf(instant));
  return calendarDateOfUtcDay(Date.UTC(wall.year, wall.month - 1, wall.day));
}

export function today(at: number = nowInstant()): CalendarDate {
  return warsawDateOf(at);
}

export function addDays(date: CalendarDate, days: number): CalendarDate {
  const [year, month, day] = calendarParts(date);
  return calendarDateOfUtcDay(Date.UTC(year, month - 1, day + days));
}

export function nextDays(first: CalendarDate, count: number): CalendarDate[] {
  return Array.from({ length: count }, (_, index) => addDays(first, index));
}

// Monday to Sunday of the week holding `date` (ADR-0001-C14).
export function weekOf(date: CalendarDate): DateRange {
  const [year, month, day] = calendarParts(date);
  const sinceMonday = (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7;
  const first = addDays(date, -sinceMonday);
  return { first, last: addDays(first, 6) };
}

export function thisWeek(at: number = nowInstant()): DateRange {
  return weekOf(today(at));
}

// The instant Warsaw's `date` begins. Warsaw never changes its offset near midnight, so the
// offset read at UTC midnight of the same date is the one in force.
function startOfDay(date: CalendarDate): number {
  const [year, month, day] = calendarParts(date);
  const utcMidnight = Date.UTC(year, month - 1, day);
  return utcMidnight - offsetAt(utcMidnight);
}

export function msUntilNextDay(at: number = nowInstant()): number {
  return startOfDay(addDays(today(at), 1)) - at;
}

// Ascending by instant; equal instants keep their order under a stable sort.
export function compareInstants(a: string, b: string): number {
  return epochOf(a) - epochOf(b);
}

function noonOf(date: CalendarDate): number {
  const [year, month, day] = calendarParts(date);
  return Date.UTC(year, month - 1, day, 12);
}

// A calendar date as "25 października 2026"; its noon is the same date in Warsaw.
export function formatDate(date: CalendarDate): string {
  return longDate.format(noonOf(date));
}

// "25 października", for a date whose year is shown elsewhere.
export function formatDayMonth(date: CalendarDate): string {
  return dayAndMonth.format(noonOf(date));
}

export function formatWeekday(date: CalendarDate): string {
  return weekdayLong.format(noonOf(date));
}

export function formatShortWeekday(date: CalendarDate): string {
  return weekdayShort.format(noonOf(date));
}

export function dayOfMonth(date: CalendarDate): string {
  return String(calendarParts(date)[2]);
}

export function formatInstantDate(instant: string): string {
  return longDate.format(epochOf(instant));
}

export function formatInstantTime(instant: string): string {
  return wallTime.format(epochOf(instant));
}

export function formatInstant(instant: string): string {
  return `${formatInstantDate(instant)}, ${formatInstantTime(instant)}`;
}
