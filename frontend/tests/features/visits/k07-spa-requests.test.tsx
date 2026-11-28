import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import {
  CUSTOMERS_URL,
  FARM,
  listed,
  periodUrl,
  stubVisitApi,
  visit,
  VISITS_URL,
} from "../../support/visits-http";
import { clockAt, inDeviceZone } from "../../support/zone";

// K-07, the SPA line: walking My day, the week, all visits and a plan makes no request outside
// `/api/`; K-06 edge: no visit value enters the location, the history or browser storage.
// Synthetic values only (ADR-0005).
inDeviceZone();

const MARKER = "Znacznik-Adresu-4f1c";
const FIXED_PATHS = ["/", "/moj-dzien", "/wizyty", "/wizyty/nowa"];

beforeAll(async () => {
  await import("../../../src/features/Wizyty");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

const planned = visit("2026-10-21T08:00:00Z", "2026-10-21T09:00:00Z", "planned", FARM, MARKER);
const seen: string[] = [];

function recordLocation() {
  const { pathname, search, hash, href } = window.location;
  seen.push(href);
  expect(FIXED_PATHS).toContain(pathname);
  expect(search).toBe("");
  expect(hash).toBe("");
  expect(window.history.state).toBeNull();
}

describe("K-07 / K-06: the visit screens talk only to /api/ and keep visit values out of the location", () => {
  it("walks every visit screen and a plan with only /api/ requests and no visit value stored", async () => {
    clockAt("2026-10-20T08:00:00Z");
    const { calls } = stubVisitApi({
      [`GET ${periodUrl("2026-10-20", "2026-10-24")}`]: listed(planned),
      [`GET ${periodUrl("2026-10-20", "2026-10-20")}`]: listed(),
      [`GET ${periodUrl("2026-10-21", "2026-10-21")}`]: listed(planned),
      [`GET ${periodUrl("2026-10-19", "2026-10-25")}`]: listed(planned),
      [`GET ${VISITS_URL}`]: listed(planned),
      [`GET ${CUSTOMERS_URL}`]: {
        status: 200,
        body: { items: [{ id: FARM.id, name: FARM.name, country: "PL", archived: false }] },
      },
      [`POST ${VISITS_URL}`]: { status: 201, body: planned },
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
    render(<App />);

    await user.click(screen.getByRole("link", { name: "Mój dzień" }));
    await screen.findByText("1 wizyta");
    recordLocation();
    await user.click(screen.getByRole("button", { name: "środa, 21 października 2026" }));
    await screen.findByText(MARKER);
    recordLocation();
    await user.click(screen.getByRole("link", { name: "Pokaż tydzień" }));
    await screen.findByText(MARKER);
    recordLocation();
    await user.click(screen.getByRole("button", { name: "Wszystkie wizyty" }));
    await screen.findByRole("region", { name: "Wszystkie wizyty" });
    recordLocation();
    await user.click(screen.getAllByRole("link", { name: "Zaplanuj wizytę" })[0] as HTMLElement);
    await screen.findByRole("option", { name: FARM.name });
    recordLocation();
    await user.selectOptions(screen.getByLabelText(/^Klient/), FARM.name);
    const startDate = screen.getByLabelText(/^Data rozpoczęcia/);
    await user.clear(startDate);
    await user.type(startDate, "2026-10-21");
    await user.type(screen.getByLabelText(/^Godzina rozpoczęcia/), "10:00");
    await user.type(screen.getByLabelText(/^Godzina zakończenia/), "11:00");
    await user.type(screen.getByLabelText(/^Adres spotkania/), MARKER);
    await user.click(screen.getByRole("button", { name: "Zaplanuj wizytę" }));
    await screen.findByRole("heading", { level: 1, name: "Mój dzień" });
    recordLocation();

    // Contrast: the recorder does see requests, the create among them.
    expect(calls.some((call) => call.method === "POST" && call.url === VISITS_URL)).toBe(true);
    expect(calls.length).toBeGreaterThan(6);
    expect(calls.filter((call) => !call.url.startsWith("/api/"))).toEqual([]);
    for (const href of seen) {
      expect(href).not.toContain(MARKER);
      expect(href).not.toContain(FARM.id);
      expect(href).not.toContain(planned.id);
      expect(href).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    }
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
