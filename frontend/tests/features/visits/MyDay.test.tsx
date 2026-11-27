import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import {
  FARM,
  listed,
  ORCHARD,
  periodUrl,
  stubVisitApi,
  visit,
  type ReplySource,
} from "../../support/visits-http";
import { clockAt, inDeviceZone } from "../../support/zone";

// K-06: the My day screen shows Europe/Warsaw days computed by `frontend/src/time/warsaw.ts`
// whatever the device's zone (New York here), the next visit as the server answers its state,
// the day's agenda and a five-day strip with counts. Synthetic values only (ADR-0005).
inDeviceZone();

const MY_DAY = "/moj-dzien";
let assign: MockInstance<(url: string) => void>;

beforeAll(async () => {
  await import("../../../src/features/Wizyty");
});

beforeEach(() => {
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function openMyDay() {
  window.history.replaceState(null, "", MY_DAY);
  render(<App />);
}

function stripDays() {
  const strip = screen.getByRole("group", { name: "Wybierz dzień" });
  return within(strip).getAllByRole("button");
}

function stripNames() {
  return stripDays().map((day) => day.getAttribute("aria-label"));
}

// 2026-10-25 (the 25-hour day), whose 00:30 Warsaw is still 24 October in New York.
const MIDNIGHT_HALF = visit("2026-10-24T22:30:00Z", "2026-10-24T23:30:00Z", "planned", ORCHARD);
const SUNDAY_NOON = visit("2026-10-25T11:00:00Z", "2026-10-25T12:00:00Z", "planned", FARM);
const TUESDAY = visit("2026-10-27T09:00:00Z", "2026-10-27T10:00:00Z", "planned", FARM);

function routes(extra: Record<string, ReplySource> = {}): Record<string, ReplySource> {
  return {
    [`GET ${periodUrl("2026-10-25", "2026-10-29")}`]: listed(MIDNIGHT_HALF, SUNDAY_NOON, TUESDAY),
    [`GET ${periodUrl("2026-10-25", "2026-10-25")}`]: listed(MIDNIGHT_HALF, SUNDAY_NOON),
    ...extra,
  };
}

describe("K-06: the five-day strip holds today and the next four Warsaw dates", () => {
  it("at 2026-10-24T22:30Z (25 Oct, 00:30 Warsaw) shows 25 to 29 October with their counts", async () => {
    clockAt("2026-10-24T22:30:00Z");
    const { calls } = stubVisitApi(routes());
    openMyDay();

    expect(await screen.findByRole("heading", { level: 1, name: "Mój dzień" })).toBeVisible();
    expect(stripNames()).toEqual([
      "niedziela, 25 października 2026",
      "poniedziałek, 26 października 2026",
      "wtorek, 27 października 2026",
      "środa, 28 października 2026",
      "czwartek, 29 października 2026",
    ]);
    const counts = await screen.findAllByText(/^(\d+) wizyt/);
    expect(counts.map((count) => count.textContent)).toEqual([
      "2 wizyty",
      "0 wizyt",
      "1 wizyta",
      "0 wizyt",
      "0 wizyt",
    ]);
    expect(stripDays()[0]).toHaveAttribute("aria-pressed", "true");
    expect(calls.map((call) => call.url)).toEqual(
      expect.arrayContaining([
        periodUrl("2026-10-25", "2026-10-29"),
        periodUrl("2026-10-25", "2026-10-25"),
      ]),
    );
    expect(calls).toHaveLength(2);
  });

  it("contrast: at 2026-10-23T22:30Z (24 Oct, 00:30 Warsaw) shows 24 to 28 October", async () => {
    clockAt("2026-10-23T22:30:00Z");
    stubVisitApi({
      [`GET ${periodUrl("2026-10-24", "2026-10-28")}`]: listed(),
      [`GET ${periodUrl("2026-10-24", "2026-10-24")}`]: listed(),
    });
    openMyDay();

    await screen.findByRole("heading", { level: 1, name: "Mój dzień" });
    expect(stripNames()).toEqual([
      "sobota, 24 października 2026",
      "niedziela, 25 października 2026",
      "poniedziałek, 26 października 2026",
      "wtorek, 27 października 2026",
      "środa, 28 października 2026",
    ]);
  });

  it("at 28 March 23:30 Warsaw keeps 29 March, the 23-hour day", async () => {
    clockAt("2026-03-28T22:30:00Z");
    stubVisitApi({
      [`GET ${periodUrl("2026-03-28", "2026-04-01")}`]: listed(),
      [`GET ${periodUrl("2026-03-28", "2026-03-28")}`]: listed(),
    });
    openMyDay();

    await screen.findByRole("heading", { level: 1, name: "Mój dzień" });
    expect(stripNames()).toEqual([
      "sobota, 28 marca 2026",
      "niedziela, 29 marca 2026",
      "poniedziałek, 30 marca 2026",
      "wtorek, 31 marca 2026",
      "środa, 1 kwietnia 2026",
    ]);
  });

  it("on 29 December runs over the year: 29, 30, 31 December, 1 and 2 January", async () => {
    clockAt("2026-12-29T09:00:00Z");
    stubVisitApi({
      [`GET ${periodUrl("2026-12-29", "2027-01-02")}`]: listed(),
      [`GET ${periodUrl("2026-12-29", "2026-12-29")}`]: listed(),
    });
    openMyDay();

    await screen.findByRole("heading", { level: 1, name: "Mój dzień" });
    expect(stripNames()).toEqual([
      "wtorek, 29 grudnia 2026",
      "środa, 30 grudnia 2026",
      "czwartek, 31 grudnia 2026",
      "piątek, 1 stycznia 2027",
      "sobota, 2 stycznia 2027",
    ]);
  });

  it("selecting a strip day requests and shows that day", async () => {
    clockAt("2026-10-24T22:30:00Z");
    const tuesday = periodUrl("2026-10-27", "2026-10-27");
    const { calls } = stubVisitApi(routes({ [`GET ${tuesday}`]: listed(TUESDAY) }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
    openMyDay();
    await screen.findAllByText("2 wizyty");

    await user.click(screen.getByRole("button", { name: "wtorek, 27 października 2026" }));

    expect(screen.getByRole("button", { name: "wtorek, 27 października 2026" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const agenda = await screen.findByRole("list", { name: "Agenda dnia" });
    expect(within(agenda).getByText(FARM.name)).toBeVisible();
    expect(within(agenda).getByText("10:00 – 11:00")).toBeVisible();
    expect(calls.map((call) => call.url)).toContain(tuesday);
  });
});

describe("K-06: the next visit is the first visit of today the server answers as Planned", () => {
  const heldFirst = visit("2026-10-25T07:00:00Z", "2026-10-25T08:00:00Z", "held", ORCHARD);
  const plannedSecond = visit("2026-10-25T09:00:00Z", "2026-10-25T10:00:00Z", "planned", FARM);
  const plannedThird = visit(
    "2026-10-25T13:00:00Z",
    "2026-10-25T14:00:00Z",
    "planned",
    { ...ORCHARD, id: "6f2a3d4c-5e6f-4a7b-8c9d-0e1f2a3b4c5d", name: "Pasieka Na Wzgórzu" },
  );

  function dayOf(...items: ReturnType<typeof visit>[]) {
    return {
      [`GET ${periodUrl("2026-10-25", "2026-10-29")}`]: listed(...items),
      [`GET ${periodUrl("2026-10-25", "2026-10-25")}`]: listed(...items),
    };
  }

  it("a first visit answered as Held is not the next visit; the second, Planned, one is", async () => {
    clockAt("2026-10-25T08:30:00Z");
    stubVisitApi(dayOf(heldFirst, plannedSecond, plannedThird));
    openMyDay();

    const next = await screen.findByRole("article", { name: "Najbliższa wizyta" });
    expect(within(next).getByRole("heading", { name: FARM.name })).toBeVisible();
    expect(within(next).getByText("10:00 – 11:00")).toBeVisible();
    expect(within(next).getByText("Polna 7, 00-950 Kłodawa")).toBeVisible();

    const agenda = screen.getByRole("list", { name: "Agenda dnia" });
    const rows = within(agenda).getAllByRole("listitem");
    expect(rows.map((row) => within(row).getByRole("heading").textContent)).toEqual([
      ORCHARD.name,
      "Pasieka Na Wzgórzu",
    ]);
    expect(within(rows[0] as HTMLElement).getByText("Odbyta")).toBeVisible();
    expect(within(rows[0] as HTMLElement).getByText("08:00 – 09:00")).toBeVisible();
    expect(within(rows[1] as HTMLElement).getByText("Zaplanowana")).toBeVisible();
  });

  it("contrast: when the first visit is answered as Planned, it is the next visit", async () => {
    clockAt("2026-10-25T06:30:00Z");
    stubVisitApi(dayOf({ ...heldFirst, state: "planned" }, plannedSecond));
    openMyDay();

    const next = await screen.findByRole("article", { name: "Najbliższa wizyta" });
    expect(within(next).getByRole("heading", { name: ORCHARD.name })).toBeVisible();
  });

  it("the agenda is in start order, the next visit is shown once and not again in the list", async () => {
    clockAt("2026-10-25T06:30:00Z");
    stubVisitApi(dayOf(plannedThird, plannedSecond));
    openMyDay();

    const next = await screen.findByRole("article", { name: "Najbliższa wizyta" });
    expect(within(next).getByRole("heading", { name: FARM.name })).toBeVisible();
    const agenda = screen.getByRole("list", { name: "Agenda dnia" });
    expect(within(agenda).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getAllByText(FARM.name)).toHaveLength(1);
  });

  it("a day with no Planned visit shows no next-visit card, only the agenda", async () => {
    clockAt("2026-10-25T20:30:00Z");
    stubVisitApi(dayOf(heldFirst, { ...plannedSecond, state: "held" }));
    openMyDay();

    const agenda = await screen.findByRole("list", { name: "Agenda dnia" });
    expect(within(agenda).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("article", { name: "Najbliższa wizyta" })).not.toBeInTheDocument();
  });

  it("a visit's own address is shown instead of the customer's; markup renders as text", async () => {
    clockAt("2026-10-25T06:30:00Z");
    const marked = visit(
      "2026-10-25T09:00:00Z",
      "2026-10-25T10:00:00Z",
      "planned",
      { ...FARM, name: "<b>Ferma</b> & Syn" },
      "<img src=x onerror=alert(1)> Łąkowa 3",
    );
    stubVisitApi(dayOf(marked));
    openMyDay();

    const next = await screen.findByRole("article", { name: "Najbliższa wizyta" });
    expect(within(next).getByRole("heading", { name: "<b>Ferma</b> & Syn" })).toBeVisible();
    expect(within(next).getByText("<img src=x onerror=alert(1)> Łąkowa 3")).toBeVisible();
    expect(within(next).queryByText(/Polna 7/)).not.toBeInTheDocument();
    expect(document.querySelector("img[src='x']")).toBeNull();
  });
});

describe("K-06: an empty day, a load error and the midnight rollover", () => {
  it("an empty day shows the empty state with the plan button as its next step", async () => {
    clockAt("2026-10-24T22:30:00Z");
    stubVisitApi({
      [`GET ${periodUrl("2026-10-25", "2026-10-29")}`]: listed(),
      [`GET ${periodUrl("2026-10-25", "2026-10-25")}`]: listed(),
    });
    openMyDay();

    expect(await screen.findByRole("heading", { name: "Czas na rozmowę" })).toBeVisible();
    const section = screen.getByRole("region", { name: "Dzisiejsze wizyty" });
    expect(within(section).getByRole("link", { name: "Zaplanuj wizytę" })).toHaveAttribute(
      "href",
      "/wizyty/nowa",
    );
    expect(screen.queryByRole("article", { name: "Najbliższa wizyta" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a load error is shown as an error, not as an empty day", async () => {
    clockAt("2026-10-24T22:30:00Z");
    stubVisitApi({
      [`GET ${periodUrl("2026-10-25", "2026-10-29")}`]: { status: 500, body: { detail: "x" } },
      [`GET ${periodUrl("2026-10-25", "2026-10-25")}`]: { status: 500, body: { detail: "x" } },
    });
    openMyDay();

    expect(await screen.findByText("Nie udało się wczytać wizyt.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Spróbuj ponownie" })).toBeVisible();
    expect(screen.getByText("Nie udało się wczytać liczby wizyt w tych dniach.")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Czas na rozmowę" })).not.toBeInTheDocument();
    expect(screen.queryByText(/^\d+ wizyt/)).not.toBeInTheDocument();
  });

  it("the strip and today roll over at Warsaw midnight without a reload", async () => {
    clockAt("2026-10-24T21:59:00Z");
    const { calls } = stubVisitApi({
      [`GET ${periodUrl("2026-10-24", "2026-10-28")}`]: listed(),
      [`GET ${periodUrl("2026-10-24", "2026-10-24")}`]: listed(),
      ...routes(),
    });
    openMyDay();
    await screen.findAllByText("0 wizyt");
    expect(stripNames()[0]).toBe("sobota, 24 października 2026");

    act(() => {
      vi.advanceTimersByTime(61_000);
    });

    expect(await screen.findByText("2 wizyty")).toBeVisible();
    expect(stripNames()[0]).toBe("niedziela, 25 października 2026");
    expect(stripNames()[4]).toBe("czwartek, 29 października 2026");
    expect(stripDays()[0]).toHaveAttribute("aria-pressed", "true");
    expect(calls.map((call) => call.url)).toContain(periodUrl("2026-10-25", "2026-10-25"));
    expect(assign).not.toHaveBeenCalled();
  });
});
