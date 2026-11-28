import { afterEach, describe, expect, it, vi } from "vitest";
import {
  addDays,
  formatInstant,
  formatInstantTime,
  msUntilNextDay,
  nextDays,
  thisWeek,
  today,
  warsawDateOf,
} from "../../src/time/warsaw";
import { clockAt, inDeviceZone } from "../support/zone";

// K-06 / ADR-0001-C13 and C14, the Vitest halves: every Warsaw date and wall time the SPA shows
// comes from this helper, whatever the device's zone.
inDeviceZone();

afterEach(() => {
  vi.useRealTimers();
});

describe("ADR-0001-C14: today and this week are Europe/Warsaw dates of the browser's clock", () => {
  it("today is 2026-10-23 at 2026-10-22T22:30:00Z (00:30 in Warsaw, 18:30 in New York)", () => {
    clockAt("2026-10-22T22:30:00Z");
    expect(today()).toBe("2026-10-23");
  });

  it("today is 2027-01-01 at 2026-12-31T23:30:00Z", () => {
    clockAt("2026-12-31T23:30:00Z");
    expect(today()).toBe("2027-01-01");
  });

  it("this week is 2026-10-26 to 2026-11-01 at 2026-10-25T23:30:00Z", () => {
    clockAt("2026-10-25T23:30:00Z");
    expect(thisWeek()).toEqual({ first: "2026-10-26", last: "2026-11-01" });
  });

  it("the week holding Sunday 2026-10-25 runs Monday 19 to Sunday 25 October", () => {
    clockAt("2026-10-24T22:30:00Z");
    expect(thisWeek()).toEqual({ first: "2026-10-19", last: "2026-10-25" });
  });

  it("contrast: one hour earlier, still 24 October in Warsaw, the day is 2026-10-24", () => {
    clockAt("2026-10-23T22:30:00Z");
    expect(today()).toBe("2026-10-24");
  });
});

describe("K-06: days are counted on the calendar, never by adding 24 hours to an instant", () => {
  it("the five days from 25 October (a 25-hour day) are 25 to 29 October", () => {
    expect(nextDays("2026-10-25", 5)).toEqual([
      "2026-10-25",
      "2026-10-26",
      "2026-10-27",
      "2026-10-28",
      "2026-10-29",
    ]);
  });

  it("the five days from 28 March keep 29 March (a 23-hour day)", () => {
    expect(nextDays("2026-03-28", 5)).toEqual([
      "2026-03-28",
      "2026-03-29",
      "2026-03-30",
      "2026-03-31",
      "2026-04-01",
    ]);
  });

  it("days cross the year: 29 December gives 29, 30, 31 December and 1, 2 January", () => {
    expect(nextDays("2026-12-29", 5)).toEqual([
      "2026-12-29",
      "2026-12-30",
      "2026-12-31",
      "2027-01-01",
      "2027-01-02",
    ]);
  });

  it("adds and subtracts days across a month and a leap day", () => {
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDays("2028-03-01", -1)).toBe("2028-02-29");
    expect(addDays("2026-11-01", -7)).toBe("2026-10-25");
  });
});

describe("ADR-0001-C13: instants render in Europe/Warsaw, never in the device's zone", () => {
  it("2026-10-24T23:30:00Z renders as 25 October 2026, 01:30", () => {
    expect(formatInstant("2026-10-24T23:30:00Z")).toBe("25 października 2026, 01:30");
  });

  it("2026-03-29T01:00:00Z renders as 29 March 2026, 03:00", () => {
    expect(formatInstant("2026-03-29T01:00:00Z")).toBe("29 marca 2026, 03:00");
  });

  it("the Warsaw date of an instant is the Warsaw calendar date, on both sides of midnight", () => {
    expect(warsawDateOf("2026-10-24T21:59:00Z")).toBe("2026-10-24");
    expect(warsawDateOf("2026-10-24T22:00:00Z")).toBe("2026-10-25");
    expect(formatInstantTime("2026-10-25T22:30:00Z")).toBe("23:30");
  });
});

describe("K-06: the time left to Warsaw's next midnight", () => {
  it("is one minute at 23:59 in Warsaw on 24 October (CEST)", () => {
    clockAt("2026-10-24T21:59:00Z");
    expect(msUntilNextDay()).toBe(60_000);
  });

  it("is one minute at 23:59 in Warsaw on 25 October, the 25-hour day (CET by then)", () => {
    clockAt("2026-10-25T22:59:00Z");
    expect(msUntilNextDay()).toBe(60_000);
  });
});
