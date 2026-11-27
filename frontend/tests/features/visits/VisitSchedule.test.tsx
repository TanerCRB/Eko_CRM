import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import {
  FARM,
  listed,
  ORCHARD,
  periodUrl,
  stubVisitApi,
  visit,
  VISITS_URL,
} from "../../support/visits-http";
import { clockAt, inDeviceZone } from "../../support/zone";

// K-06: the Visits list's week is Monday to Sunday of the Warsaw week holding today, and the
// all-visits view groups what the server answers by Warsaw day, whatever the device's zone (New
// York here). Synthetic values only (ADR-0005).
inDeviceZone();

beforeAll(async () => {
  await import("../../../src/features/Wizyty");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function openVisits() {
  window.history.replaceState(null, "", "/wizyty");
  render(<App />);
}

const WEEK = periodUrl("2026-10-19", "2026-10-25");
// Sunday 25 October, 23:30 Warsaw (CET), which is 18:30 the same day in New York.
const SUNDAY_LATE = visit("2026-10-25T22:30:00Z", "2026-10-25T23:00:00Z", "planned", FARM);
// Monday 19 October, 00:30 Warsaw (CEST), which is still Sunday 18 October in New York.
const MONDAY_EARLY = visit("2026-10-18T22:30:00Z", "2026-10-18T23:30:00Z", "held", ORCHARD);

describe("K-06: the week is Monday 19 to Sunday 25 October at 2026-10-24T22:30Z", () => {
  it("requests that week and shows its seven Warsaw days, each visit on its start's day", async () => {
    clockAt("2026-10-24T22:30:00Z");
    const { calls } = stubVisitApi({ [`GET ${WEEK}`]: listed(MONDAY_EARLY, SUNDAY_LATE) });
    openVisits();

    expect(await screen.findByRole("heading", { level: 1, name: "Wizyty" })).toBeVisible();
    expect(screen.getByText("19 października 2026 – 25 października 2026")).toBeVisible();
    const board = screen.getByRole("region", { name: "Wizyty w tygodniu" });
    await within(board).findByText(FARM.name);
    const columns = within(board).getAllByRole("region");
    expect(columns.map((column) => within(column).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "poniedziałek, 19 października",
      "wtorek, 20 października",
      "środa, 21 października",
      "czwartek, 22 października",
      "piątek, 23 października",
      "sobota, 24 października",
      "niedziela, 25 października",
    ]);
    const monday = columns[0] as HTMLElement;
    const sunday = columns[6] as HTMLElement;
    expect(within(monday).getByText(ORCHARD.name)).toBeVisible();
    expect(within(monday).getByText("00:30 – 01:30")).toBeVisible();
    expect(within(monday).getByText("Odbyta")).toBeVisible();
    expect(within(sunday).getByText(FARM.name)).toBeVisible();
    expect(within(sunday).getByText("23:30 – 00:00")).toBeVisible();
    expect(within(sunday).getByText(/Dzisiaj/)).toBeVisible();
    expect(within(columns[3] as HTMLElement).getByText("Brak wizyt")).toBeVisible();
    expect(calls.map((call) => call.url)).toEqual([WEEK]);
  });

  it("contrast: one day later, Monday 26 October in Warsaw, the week is 26 October to 1 November", async () => {
    clockAt("2026-10-25T23:30:00Z");
    const { calls } = stubVisitApi({ [`GET ${periodUrl("2026-10-26", "2026-11-01")}`]: listed() });
    openVisits();

    expect(await screen.findByText("26 października 2026 – 1 listopada 2026")).toBeVisible();
    expect(calls.map((call) => call.url)).toEqual([periodUrl("2026-10-26", "2026-11-01")]);
  });

  it("a load error of the week is an error, not an empty week", async () => {
    clockAt("2026-10-24T22:30:00Z");
    stubVisitApi({ [`GET ${WEEK}`]: { status: 503, body: { detail: "temporarily unavailable" } } });
    openVisits();

    expect(await screen.findByText("Nie udało się wczytać wizyt.")).toBeVisible();
    expect(screen.queryByText("Brak wizyt")).not.toBeInTheDocument();
  });
});

describe("K-06: the all-visits view shows every visit the server answers, grouped by Warsaw day", () => {
  it("groups by the Warsaw date of each start and shows Warsaw times (C13)", async () => {
    clockAt("2026-10-24T22:30:00Z");
    const lateSaturday = visit("2026-10-24T21:30:00Z", "2026-10-24T21:45:00Z", "held", ORCHARD);
    const earlySunday = visit("2026-10-24T23:30:00Z", "2026-10-25T00:30:00Z", "planned", FARM);
    const springForward = visit("2026-03-29T01:00:00Z", "2026-03-29T02:00:00Z", "held", FARM);
    const { calls } = stubVisitApi({
      [`GET ${WEEK}`]: listed(),
      [`GET ${VISITS_URL}`]: listed(springForward, lateSaturday, earlySunday),
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
    openVisits();
    await screen.findByRole("region", { name: "Wizyty w tygodniu" });

    await user.click(screen.getByRole("button", { name: "Wszystkie wizyty" }));

    const all = await screen.findByRole("region", { name: "Wszystkie wizyty" });
    await within(all).findAllByText(FARM.name);
    const groups = within(all).getAllByRole("region");
    expect(groups.map((group) => within(group).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "niedziela, 29 marca 2026",
      "sobota, 24 października 2026",
      "niedziela, 25 października 2026",
    ]);
    expect(within(groups[0] as HTMLElement).getByText("03:00 – 04:00")).toBeVisible();
    expect(within(groups[1] as HTMLElement).getByText("23:30 – 23:45")).toBeVisible();
    expect(within(groups[2] as HTMLElement).getByText("01:30 – 02:30")).toBeVisible();
    expect(screen.getByRole("button", { name: "Wszystkie wizyty" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(calls.map((call) => call.url)).toEqual([WEEK, VISITS_URL]);
  });

  it("with no visits at all shows the empty state with the plan button", async () => {
    clockAt("2026-10-24T22:30:00Z");
    stubVisitApi({ [`GET ${WEEK}`]: listed(), [`GET ${VISITS_URL}`]: listed() });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
    openVisits();
    await screen.findByRole("region", { name: "Wizyty w tygodniu" });

    await user.click(screen.getByRole("button", { name: "Wszystkie wizyty" }));

    expect(await screen.findByRole("heading", { name: "Nie masz jeszcze wizyt" })).toBeVisible();
    const all = screen.getByRole("region", { name: "Wszystkie wizyty" });
    expect(within(all).getByRole("link", { name: "Zaplanuj wizytę" })).toHaveAttribute(
      "href",
      "/wizyty/nowa",
    );
  });
});
