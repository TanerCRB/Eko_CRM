import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import type { CustomerSummary } from "../../../src/api/customers";
import {
  CUSTOMERS_URL,
  deferred,
  FARM,
  listed,
  periodUrl,
  stubVisitApi,
  visit,
  VISITS_URL,
  type RecordedCall,
  type ReplySource,
  type VisitReply,
} from "../../support/visits-http";
import { clockAt, inDeviceZone } from "../../support/zone";

// K-06: the plan form sends the local date and time as typed, with no offset; a 422 naming
// "nonexistent" or "ambiguous" is shown at its field as two distinct Polish messages with the
// typed values kept; a double click sends one create; the picker lists the server's customers.
// Synthetic values only (ADR-0005).
inDeviceZone();

const PLAN = "/wizyty/nowa";
const NONEXISTENT =
  "Tej godziny nie ma tego dnia: zegary przestawia się wtedy o godzinę do przodu. Wybierz inną godzinę.";
const AMBIGUOUS =
  "Ta godzina występuje tego dnia dwa razy: zegary cofa się wtedy o godzinę. Wybierz inną godzinę.";

const customers: CustomerSummary[] = [
  { id: FARM.id, name: FARM.name, country: "PL", archived: false },
  { id: "7b8c9d0e-1f2a-4b3c-8d4e-5f6a7b8c9d0e", name: "<i>Ogrody</i> & Sady", country: "PL", archived: false },
];

beforeAll(async () => {
  await import("../../../src/features/Wizyty");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  clockAt("2026-10-20T08:00:00Z");
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function routes(create: ReplySource, extra: Record<string, ReplySource> = {}) {
  return {
    [`GET ${CUSTOMERS_URL}`]: { status: 200, body: { items: customers } } satisfies VisitReply,
    [`POST ${VISITS_URL}`]: create,
    ...extra,
  };
}

function creates(calls: readonly RecordedCall[]) {
  return calls.filter((call) => call.method === "POST" && call.url === VISITS_URL);
}

async function openForm() {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
  window.history.replaceState(null, "", PLAN);
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: "Zaplanuj wizytę" });
  await screen.findByRole("option", { name: FARM.name });
  return user;
}

async function fill(
  user: ReturnType<typeof userEvent.setup>,
  values: { date: string; start: string; end: string; endDate?: string },
) {
  await user.selectOptions(screen.getByLabelText(/^Klient/), FARM.name);
  const startDate = screen.getByLabelText(/^Data rozpoczęcia/);
  await user.clear(startDate);
  await user.type(startDate, values.date);
  await user.type(screen.getByLabelText(/^Godzina rozpoczęcia/), values.start);
  if (values.endDate !== undefined) {
    const endDate = screen.getByLabelText(/^Data zakończenia/);
    await user.clear(endDate);
    await user.type(endDate, values.endDate);
  }
  await user.type(screen.getByLabelText(/^Godzina zakończenia/), values.end);
}

function reason(type: string, side: "start" | "end"): VisitReply {
  return { status: 422, body: { detail: [{ type, loc: ["body", side], msg: "fixed text" }] } };
}

describe("K-06: the customer picker lists what the server's customer list answers", () => {
  it("offers each customer of GET /api/customers by name, markup as text", async () => {
    const { calls } = stubVisitApi(routes(listed()));
    await openForm();

    const picker = screen.getByLabelText(/^Klient/);
    expect(within(picker).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Wybierz klienta",
      FARM.name,
      "<i>Ogrody</i> & Sady",
    ]);
    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([`GET ${CUSTOMERS_URL}`]);
  });

  it("a failed customer list is an error, not an empty picker", async () => {
    stubVisitApi({ [`GET ${CUSTOMERS_URL}`]: { status: 500, body: { detail: "x" } } });
    window.history.replaceState(null, "", PLAN);
    render(<App />);

    expect(await screen.findByText("Nie udało się wczytać listy klientów.")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Zacznij od klienta" })).not.toBeInTheDocument();
  });

  it("with no customers, says so and links to adding one", async () => {
    stubVisitApi({ [`GET ${CUSTOMERS_URL}`]: { status: 200, body: { items: [] } } });
    window.history.replaceState(null, "", PLAN);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Zacznij od klienta" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Dodaj klienta" })).toHaveAttribute(
      "href",
      "/klienci/nowy",
    );
  });
});

describe("K-06: the form sends the wall time as typed, with no offset", () => {
  it("sends the typed date and HH:MM for start and end, the end date following the start", async () => {
    const planned = visit("2026-10-22T08:00:00Z", "2026-10-22T09:00:00Z", "planned");
    const { calls } = stubVisitApi(
      routes(
        { status: 201, body: planned },
        {
          [`GET ${periodUrl("2026-10-20", "2026-10-24")}`]: listed(planned),
          [`GET ${periodUrl("2026-10-22", "2026-10-22")}`]: listed(planned),
        },
      ),
    );
    const user = await openForm();
    await fill(user, { date: "2026-10-22", start: "10:00", end: "11:00" });

    await user.click(screen.getByRole("button", { name: "Zaplanuj wizytę" }));

    expect(creates(calls).map((call) => call.body)).toStrictEqual([
      {
        customer_id: FARM.id,
        start: { date: "2026-10-22", time: "10:00" },
        end: { date: "2026-10-22", time: "11:00" },
      },
    ]);
    expect(await screen.findByRole("heading", { level: 1, name: "Mój dzień" })).toBeVisible();
    expect(window.location.pathname).toBe("/moj-dzien");
    expect(screen.getByRole("status")).toHaveTextContent(
      `Zaplanowano wizytę: ${FARM.name}, 22 października 2026, 10:00.`,
    );
    expect(
      screen.getByRole("button", { name: "czwartek, 22 października 2026" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("list", { name: "Agenda dnia" })).toHaveTextContent(FARM.name);
  });

  it("sends a typed end date and a given own address; a blank address is not sent", async () => {
    const planned = visit("2026-11-30T22:00:00Z", "2026-12-01T00:00:00Z", "planned");
    const { calls } = stubVisitApi(routes({ status: 201, body: planned }, {
      [`GET ${periodUrl("2026-10-20", "2026-10-24")}`]: listed(),
      [`GET ${periodUrl("2026-10-20", "2026-10-20")}`]: listed(),
    }));
    const user = await openForm();
    await fill(user, { date: "2026-11-30", start: "23:00", end: "01:00", endDate: "2026-12-01" });
    await user.type(screen.getByLabelText(/^Adres spotkania/), "Łąkowa 3");

    await user.click(screen.getByRole("button", { name: "Zaplanuj wizytę" }));

    expect(creates(calls).map((call) => call.body)).toStrictEqual([
      {
        customer_id: FARM.id,
        start: { date: "2026-11-30", time: "23:00" },
        end: { date: "2026-12-01", time: "01:00" },
        own_address: "Łąkowa 3",
      },
    ]);
  });
});

describe("K-06: the two DST reasons are shown at their field as distinct messages", () => {
  it("nonexistent at the start shows its message at the start time, values kept", async () => {
    stubVisitApi(routes(reason("nonexistent_local_time", "start")));
    const user = await openForm();
    await fill(user, { date: "2026-03-29", start: "02:30", end: "04:00" });

    await user.click(screen.getByRole("button", { name: "Zaplanuj wizytę" }));

    const startTime = screen.getByLabelText(/^Godzina rozpoczęcia/);
    expect(await screen.findByText(NONEXISTENT)).toBeVisible();
    expect(startTime).toHaveAccessibleDescription(NONEXISTENT);
    expect(startTime).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/^Godzina zakończenia/)).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText(AMBIGUOUS)).not.toBeInTheDocument();
    expect(startTime).toHaveValue("02:30");
    expect(screen.getByLabelText(/^Data rozpoczęcia/)).toHaveValue("2026-03-29");
    expect(screen.getByLabelText(/^Godzina zakończenia/)).toHaveValue("04:00");
    expect(screen.getByLabelText(/^Klient/)).toHaveValue(FARM.id);
    expect(window.location.pathname).toBe(PLAN);
  });

  it("ambiguous at the end shows the other message at the end time, values kept", async () => {
    stubVisitApi(routes(reason("ambiguous_local_time", "end")));
    const user = await openForm();
    await fill(user, { date: "2026-10-25", start: "01:30", end: "02:30" });

    await user.click(screen.getByRole("button", { name: "Zaplanuj wizytę" }));

    const endTime = screen.getByLabelText(/^Godzina zakończenia/);
    expect(await screen.findByText(AMBIGUOUS)).toBeVisible();
    expect(endTime).toHaveAccessibleDescription(AMBIGUOUS);
    expect(screen.getByLabelText(/^Godzina rozpoczęcia/)).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText(NONEXISTENT)).not.toBeInTheDocument();
    expect(endTime).toHaveValue("02:30");
    expect(screen.getByLabelText(/^Godzina rozpoczęcia/)).toHaveValue("01:30");
  });

  it("an end not after the start is named at the end, apart from the DST reasons", async () => {
    stubVisitApi(routes({
      status: 422,
      body: { detail: [{ type: "value_error", loc: ["body", "end"], msg: "fixed text" }] },
    }));
    const user = await openForm();
    await fill(user, { date: "2026-10-20", start: "10:00", end: "10:00" });

    await user.click(screen.getByRole("button", { name: "Zaplanuj wizytę" }));

    const message = "Koniec wizyty musi być później niż jej początek.";
    expect(await screen.findByText(message)).toBeVisible();
    expect(screen.getByLabelText(/^Godzina zakończenia/)).toHaveAccessibleDescription(message);
  });
});

describe("K-06: other answers and the double click", () => {
  it("a double click on the plan button sends one create", async () => {
    const held = deferred<VisitReply>();
    const { calls } = stubVisitApi(routes(() => held.promise, {
      [`GET ${periodUrl("2026-10-20", "2026-10-24")}`]: listed(),
      [`GET ${periodUrl("2026-10-21", "2026-10-21")}`]: listed(),
    }));
    const user = await openForm();
    await fill(user, { date: "2026-10-21", start: "10:00", end: "11:00" });

    await user.dblClick(screen.getByRole("button", { name: "Zaplanuj wizytę" }));

    expect(creates(calls)).toHaveLength(1);
    held.resolve({
      status: 201,
      body: visit("2026-10-21T08:00:00Z", "2026-10-21T09:00:00Z", "planned"),
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Mój dzień" })).toBeVisible();
    expect(creates(calls)).toHaveLength(1);
  });

  it.each([
    [{ status: 409, body: { detail: "restore it first" } }, "Ten klient jest zarchiwizowany. Przywróć go, aby zaplanować wizytę."],
    [{ status: 404, body: { detail: "not found" } }, "Nie znaleziono tego klienta wśród Twoich klientów."],
    [{ status: 403, body: { detail: "not permitted" } }, "Twoje konto nie może planować wizyt."],
    [{ status: 500, body: { detail: "x" } }, "Nie udało się zaplanować wizyty. Spróbuj ponownie."],
  ] as const)("%j is said as %s, the form kept", async (reply, message) => {
    stubVisitApi(routes(reply));
    const user = await openForm();
    await fill(user, { date: "2026-10-21", start: "10:00", end: "11:00" });

    await user.click(screen.getByRole("button", { name: "Zaplanuj wizytę" }));

    expect(await screen.findByText(message)).toBeVisible();
    expect(screen.getByLabelText(/^Godzina rozpoczęcia/)).toHaveValue("10:00");
  });
});
