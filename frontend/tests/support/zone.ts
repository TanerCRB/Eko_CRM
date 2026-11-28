import { afterAll, beforeAll, expect, vi } from "vitest";

// K-06 / ADR-0001-C13, C14: the device sits in a zone other than Europe/Warsaw, so a date read
// in the device's zone shows a different day or hour than Warsaw at the instants the tests use.
export const DEVICE_ZONE = "America/New_York";

export function inDeviceZone(): void {
  let previous: string | undefined;
  beforeAll(() => {
    previous = process.env["TZ"];
    process.env["TZ"] = DEVICE_ZONE;
    // Without this the suite would pass vacuously on a machine whose own zone is Warsaw.
    expect(new Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(DEVICE_ZONE);
  });
  afterAll(() => {
    if (previous === undefined) {
      delete process.env["TZ"];
    } else {
      process.env["TZ"] = previous;
    }
  });
}

// Fake time that still moves with real time, so Testing Library's polling keeps working; a test
// moves it past a boundary with `vi.advanceTimersByTime`.
export function clockAt(instant: string): void {
  vi.useFakeTimers({ now: new Date(instant), shouldAdvanceTime: true });
}
