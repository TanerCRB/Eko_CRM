import { act, render, screen, within } from "@testing-library/react";
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
  type VisitReply,
} from "../../support/visits-http";
import { clockAt, inDeviceZone } from "../../support/zone";

// EKO-4-01 QA, K-06 edges. (1) The plan form has two double-submit guards, an in-flight flag and
// a disabled button; the developer's double-click test passes with either one removed, so each is
// pinned here on its own: two submits in one tick (before React renders the disabled button) are
// stopped only by the flag, and the button a user sees while the create is pending is disabled
// only by the button guard. (2) Markup in a customer name or own address renders as text in an
// agenda row and in the Visits list, not only in the next-visit card. Synthetic values only.
inDeviceZone();

const PLAN = "/wizyty/nowa";
const SAVE = "Zaplanuj wizytę";
const MARKED_NAME = "<b>Ferma</b> & Syn";
const MARKED_ADDRESS = "<img src=x onerror=alert(1)> Łąkowa 3";

const customers: CustomerSummary[] = [
  { id: FARM.id, name: FARM.name, country: "PL", archived: false },
];

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

function creates(calls: readonly RecordedCall[]) {
  return calls.filter((call) => call.method === "POST" && call.url === VISITS_URL);
}

const REFUSED: VisitReply = {
  status: 422,
  body: { detail: [{ type: "value_error", loc: ["body", "end"], msg: "fixed text" }] },
};

async function filledForm() {
  clockAt("2026-10-20T08:00:00Z");
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
  window.history.replaceState(null, "", PLAN);
  render(<App />);
  await screen.findByRole("option", { name: FARM.name });
  await user.selectOptions(screen.getByLabelText(/^Klient/), FARM.name);
  const startDate = screen.getByLabelText(/^Data rozpoczęcia/);
  await user.clear(startDate);
  await user.type(startDate, "2026-10-21");
  await user.type(screen.getByLabelText(/^Godzina rozpoczęcia/), "10:00");
  await user.type(screen.getByLabelText(/^Godzina zakończenia/), "11:00");
  return user;
}

function submitEvent() {
  return new Event("submit", { bubbles: true, cancelable: true });
}

describe("QA K-06: each double-submit guard of the plan form holds on its own", () => {
  it("two submits in one tick, before the disabled button renders, send one create", async () => {
    const held = deferred<VisitReply>();
    const { calls } = stubVisitApi({
      [`GET ${CUSTOMERS_URL}`]: { status: 200, body: { items: customers } },
      [`POST ${VISITS_URL}`]: () => held.promise,
    });
    await filledForm();
    const form = screen.getByRole("form", { name: SAVE });

    act(() => {
      form.dispatchEvent(submitEvent());
      form.dispatchEvent(submitEvent());
    });

    expect(creates(calls)).toHaveLength(1);
    await act(async () => {
      held.resolve(REFUSED);
      await held.promise;
    });
    expect((await screen.findAllByRole("alert")).length).toBeGreaterThan(0);
    // Contrast: once the first create has answered, the next submit does send a create, so the
    // count above could have seen a second one.
    act(() => {
      form.dispatchEvent(submitEvent());
    });
    expect(creates(calls)).toHaveLength(2);
  });

  it("while the create is pending the plan button is disabled, and a click on it sends nothing", async () => {
    const held = deferred<VisitReply>();
    const { calls } = stubVisitApi({
      [`GET ${CUSTOMERS_URL}`]: { status: 200, body: { items: customers } },
      [`POST ${VISITS_URL}`]: () => held.promise,
    });
    const user = await filledForm();
    const button = screen.getByRole("button", { name: SAVE });

    await user.click(button);

    expect(creates(calls)).toHaveLength(1);
    expect(button).toBeDisabled();
    await user.click(button);
    expect(creates(calls)).toHaveLength(1);
    await act(async () => {
      held.resolve(REFUSED);
      await held.promise;
    });
    // Contrast: once the create has answered, the same button is enabled again.
    expect((await screen.findAllByRole("alert")).length).toBeGreaterThan(0);
    expect(button).toBeEnabled();
  });
});

describe("QA K-06: markup renders as text in every place a visit is listed", () => {
  const markedHeld = visit(
    "2026-10-25T09:00:00Z",
    "2026-10-25T10:00:00Z",
    "held",
    { ...FARM, name: MARKED_NAME },
    MARKED_ADDRESS,
  );

  it("an agenda row of My day shows a marked name and own address as text", async () => {
    clockAt("2026-10-25T20:30:00Z");
    stubVisitApi({
      [`GET ${periodUrl("2026-10-25", "2026-10-29")}`]: listed(markedHeld),
      [`GET ${periodUrl("2026-10-25", "2026-10-25")}`]: listed(markedHeld),
    });
    window.history.replaceState(null, "", "/moj-dzien");
    render(<App />);

    const agenda = await screen.findByRole("list", { name: "Agenda dnia" });
    const [row] = within(agenda).getAllByRole("listitem");
    expect(within(row as HTMLElement).getByRole("heading", { name: MARKED_NAME })).toBeVisible();
    expect(within(row as HTMLElement).getByText(MARKED_ADDRESS)).toBeVisible();
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
  });

  it("the Visits week shows a marked name and own address as text", async () => {
    clockAt("2026-10-24T22:30:00Z");
    stubVisitApi({
      [`GET ${periodUrl("2026-10-19", "2026-10-25")}`]: listed(markedHeld),
    });
    window.history.replaceState(null, "", "/wizyty");
    render(<App />);

    expect(await screen.findByText(MARKED_ADDRESS)).toBeVisible();
    expect(screen.getByRole("heading", { name: MARKED_NAME })).toBeVisible();
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
  });
});
