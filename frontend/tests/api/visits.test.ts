import { afterEach, describe, expect, it, vi } from "vitest";
import { listVisitPeriod, listVisits, planVisit, type VisitInput } from "../../src/api/visits";
import {
  FARM,
  listed,
  periodUrl,
  stubVisitApi,
  visit,
  VISITS_URL,
  type VisitReply,
} from "../support/visits-http";
import { inDeviceZone } from "../support/zone";

// K-06, the typed client: the wall time crosses as typed, periods as Warsaw dates in the query,
// and the two 422 reasons stay apart. Synthetic values only (ADR-0005).
inDeviceZone();

afterEach(() => {
  vi.unstubAllGlobals();
});

const input: VisitInput = {
  customer_id: FARM.id,
  start: { date: "2026-10-25", time: "02:30" },
  end: { date: "2026-10-25", time: "03:30" },
};

function rejection(type: string, loc: (string | number)[]): VisitReply {
  return { status: 422, body: { detail: [{ type, loc, msg: "fixed text" }] } };
}

describe("K-06: the plan request sends the local date and time as typed, with no offset", () => {
  it("posts exactly the typed date and HH:MM strings and no own address when none is given", async () => {
    const planned = visit("2026-10-25T00:30:00Z", "2026-10-25T02:30:00Z", "planned");
    const { calls } = stubVisitApi({ [`POST ${VISITS_URL}`]: { status: 201, body: planned } });

    const result = await planVisit(input);

    expect(result).toEqual({ kind: "planned", visit: planned });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body).toStrictEqual({
      customer_id: FARM.id,
      start: { date: "2026-10-25", time: "02:30" },
      end: { date: "2026-10-25", time: "03:30" },
    });
  });

  it("sends a given own address in the body, not in the URL", async () => {
    const planned = visit("2026-10-25T08:00:00Z", "2026-10-25T09:00:00Z", "planned");
    const { calls } = stubVisitApi({ [`POST ${VISITS_URL}`]: { status: 201, body: planned } });

    await planVisit({ ...input, own_address: "Łąkowa 3" });

    expect(calls[0]?.url).toBe(VISITS_URL);
    expect(calls[0]?.body).toMatchObject({ own_address: "Łąkowa 3" });
  });
});

describe("K-06: a 422 names its reason at its field", () => {
  it("nonexistent_local_time at the start is the nonexistent reason at the start", async () => {
    stubVisitApi({
      [`POST ${VISITS_URL}`]: rejection("nonexistent_local_time", ["body", "start"]),
    });
    expect(await planVisit(input)).toEqual({
      kind: "rejected",
      fields: [{ field: "start", reason: "nonexistent" }],
    });
  });

  it("ambiguous_local_time at the end is the ambiguous reason at the end", async () => {
    stubVisitApi({ [`POST ${VISITS_URL}`]: rejection("ambiguous_local_time", ["body", "end"]) });
    expect(await planVisit(input)).toEqual({
      kind: "rejected",
      fields: [{ field: "end", reason: "ambiguous" }],
    });
  });

  it("an end not after the start, and form errors of each part, name their fields", async () => {
    stubVisitApi({
      [`POST ${VISITS_URL}`]: {
        status: 422,
        body: {
          detail: [
            { type: "value_error", loc: ["body", "end"], msg: "x" },
            { type: "string_pattern_mismatch", loc: ["body", "start", "time"], msg: "x" },
            { type: "value_error", loc: ["body", "start", "date"], msg: "x" },
            { type: "uuid_parsing", loc: ["body", "customer_id"], msg: "x" },
            { type: "string_too_long", loc: ["body", "own_address"], msg: "x" },
            { type: "extra_forbidden", loc: ["body", "owner"], msg: "x" },
          ],
        },
      },
    });
    expect(await planVisit(input)).toEqual({
      kind: "rejected",
      fields: [
        { field: "end", reason: "notAfterStart" },
        { field: "start", part: "time" },
        { field: "start", part: "date" },
        { field: "customer" },
        { field: "ownAddress" },
        { field: "request" },
      ],
    });
  });

  it("a 422 with no readable detail rejects the request as a whole", async () => {
    stubVisitApi({ [`POST ${VISITS_URL}`]: { status: 422, body: {} } });
    expect(await planVisit(input)).toEqual({ kind: "rejected", fields: [{ field: "request" }] });
  });
});

describe("K-06: the other answers to a plan", () => {
  it.each([
    [404, { detail: "not found" }, { kind: "notFound" }],
    [409, { detail: "restore it first" }, { kind: "restoreFirst" }],
    [409, { detail: "something else" }, { kind: "failed" }],
    [403, { detail: "not permitted" }, { kind: "refused" }],
    [500, { detail: "x" }, { kind: "failed" }],
  ] as const)("%i %j is %j", async (status, body, expected) => {
    stubVisitApi({ [`POST ${VISITS_URL}`]: { status, body } });
    expect(await planVisit(input)).toEqual(expected);
  });

  it("a 201 whose body is outside the contract is a failure, not a visit", async () => {
    stubVisitApi({ [`POST ${VISITS_URL}`]: { status: 201, raw: '{"id":"x"}' } });
    expect(await planVisit(input)).toEqual({ kind: "failed" });
  });
});

describe("K-06: periods are Warsaw dates in the query; lists are read through the contract", () => {
  it("a period requests its first and last date and answers the visits", async () => {
    const first = visit("2026-10-24T22:30:00Z", "2026-10-24T23:30:00Z", "planned");
    const { calls } = stubVisitApi({
      [`GET ${periodUrl("2026-10-25", "2026-10-29")}`]: listed(first),
    });

    const result = await listVisitPeriod({ first: "2026-10-25", last: "2026-10-29" });

    expect(calls.map((call) => call.url)).toEqual([periodUrl("2026-10-25", "2026-10-29")]);
    expect(result).toEqual({ kind: "listed", visits: [first] });
  });

  it("a date that is not YYYY-MM-DD sends nothing", async () => {
    const { calls } = stubVisitApi({});
    expect(await listVisitPeriod({ first: "2026-02-30", last: "2026-03-01" })).toEqual({
      kind: "failed",
    });
    expect(calls).toEqual([]);
  });

  it("the all-visits list requests /api/visits", async () => {
    const held = visit("2026-03-29T01:00:00Z", "2026-03-29T02:00:00Z", "held");
    const { calls } = stubVisitApi({ [`GET ${VISITS_URL}`]: listed(held) });
    expect(await listVisits()).toEqual({ kind: "listed", visits: [held] });
    expect(calls.map((call) => call.url)).toEqual([VISITS_URL]);
  });

  it.each([
    ["a state the contract does not name", { state: "cancelled" }],
    ["an instant without an offset", { starts_at: "2026-10-25T01:30:00" }],
    ["a missing customer", { customer: null }],
    ["an identifier that is not a UUID", { id: "../customers" }],
  ])("an item with %s makes the list a failure", async (_, change) => {
    const item = { ...visit("2026-10-24T22:30:00Z", "2026-10-24T23:30:00Z", "planned"), ...change };
    stubVisitApi({ [`GET ${VISITS_URL}`]: { status: 200, raw: JSON.stringify({ items: [item] }) } });
    expect(await listVisits()).toEqual({ kind: "failed" });
  });
});
