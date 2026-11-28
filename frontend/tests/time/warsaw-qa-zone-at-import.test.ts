import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

// EKO-4-01 QA, K-06 / ADR-0001-C13: the helper's formatters are built when `time/warsaw.ts` is
// first imported. `tests/time/warsaw.test.ts` imports it statically, before its own `beforeAll`
// sets the device zone, so on a machine whose own zone is Europe/Warsaw a formatter built
// without `timeZone` still shows Warsaw there and the C13 half passes vacuously. Here the device
// zone is set first and the module is imported fresh after it, so every formatter is built in
// the device's zone (New York) and only an explicit Europe/Warsaw can give the expected text.
// Synthetic values only (ADR-0005).

const DEVICE_ZONE = "America/New_York";
let previous: string | undefined;
let warsaw: typeof import("../../src/time/warsaw");

beforeAll(async () => {
  previous = process.env["TZ"];
  process.env["TZ"] = DEVICE_ZONE;
  expect(new Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(DEVICE_ZONE);
  vi.resetModules();
  warsaw = await import("../../src/time/warsaw");
});

afterAll(() => {
  if (previous === undefined) {
    delete process.env["TZ"];
  } else {
    process.env["TZ"] = previous;
  }
  vi.resetModules();
});

describe("ADR-0001-C13 with the module built in the device's zone", () => {
  it("contrast: a formatter built now without a zone shows New York's day and hour", () => {
    const deviceDate = new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long", year: "numeric" });
    const deviceTime = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    expect(deviceDate.format(Date.parse("2026-10-24T23:30:00Z"))).toBe("24 października 2026");
    expect(deviceTime.format(Date.parse("2026-10-24T23:30:00Z"))).toBe("19:30");
  });

  it("2026-10-24T23:30:00Z renders as 25 October 2026, 01:30", () => {
    expect(warsaw.formatInstant("2026-10-24T23:30:00Z")).toBe("25 października 2026, 01:30");
    expect(warsaw.formatInstantDate("2026-10-24T23:30:00Z")).toBe("25 października 2026");
    expect(warsaw.formatInstantTime("2026-10-24T23:30:00Z")).toBe("01:30");
  });

  it("2026-03-29T01:00:00Z renders as 29 March 2026, 03:00", () => {
    expect(warsaw.formatInstant("2026-03-29T01:00:00Z")).toBe("29 marca 2026, 03:00");
  });

  it("the Warsaw date of an instant and today are Warsaw's, not New York's", () => {
    expect(warsaw.warsawDateOf("2026-10-24T22:30:00Z")).toBe("2026-10-25");
    expect(warsaw.today(Date.parse("2026-10-24T22:30:00Z"))).toBe("2026-10-25");
    expect(warsaw.nextDays("2026-10-25", 5)).toEqual([
      "2026-10-25",
      "2026-10-26",
      "2026-10-27",
      "2026-10-28",
      "2026-10-29",
    ]);
  });
});
