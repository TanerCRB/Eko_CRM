// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Problem } from "../../src/api/auth";
import { readReps, REPS_PATH, type RepList } from "../../src/api/reps";

// EKO-3-08 K-07: the manager's reps list as the SPA reads it (K-02's answer). An answer that is
// not the declared shape is a failure, never a selector with holes. Synthetic values (ADR-0005).

type RepsReply =
  | { status: 200; body: RepList }
  | { status: 403 | 500 | 503; body: Problem }
  | { status: 200; raw: string }
  | "network-error";

function answer(reply: RepsReply) {
  const sent: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      sent.push(href);
      if (reply === "network-error") {
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      const text = "raw" in reply ? reply.raw : JSON.stringify(reply.body);
      return Promise.resolve(
        new Response(text, { status: reply.status, headers: { "content-type": "application/json" } }),
      );
    }),
  );
  return sent;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EKO-3-08 K-07: reading the reps list", () => {
  it("lists every entry the server answered, subject and name, in its order", async () => {
    const sent = answer({
      status: 200,
      body: {
        items: [
          { subject: "synthetic-rep-0002", name: "Zenon Przykładowy" },
          { subject: "synthetic-rep-0001", name: null },
        ],
      },
    });

    await expect(readReps()).resolves.toEqual({
      kind: "listed",
      reps: [
        { subject: "synthetic-rep-0002", name: "Zenon Przykładowy" },
        { subject: "synthetic-rep-0001", name: null },
      ],
    });
    expect(sent).toEqual([REPS_PATH]);
    expect(REPS_PATH).toBe("/api/reps");
  });

  it("an empty list is listed, not failed", async () => {
    answer({ status: 200, body: { items: [] } });

    await expect(readReps()).resolves.toEqual({ kind: "listed", reps: [] });
  });

  it("a field the SPA does not read is left out of the entry", async () => {
    answer({
      status: 200,
      raw: JSON.stringify({ items: [{ subject: "synthetic-rep-0001", name: "Ala", extra: 1 }] }),
    });

    await expect(readReps()).resolves.toEqual({
      kind: "listed",
      reps: [{ subject: "synthetic-rep-0001", name: "Ala" }],
    });
  });

  it("G-8 A: a refusal, a server failure or no network is a failed read", async () => {
    for (const reply of [
      { status: 403, body: { detail: "not permitted" } },
      { status: 500, body: { detail: "synthetic failure" } },
      { status: 503, body: { detail: "temporarily unavailable" } },
      "network-error",
    ] as const) {
      answer(reply);

      await expect(readReps()).resolves.toEqual({ kind: "failed" });
    }
  });

  it("A-15: an answer not of the declared shape, or naming one subject twice, is a failed read", async () => {
    for (const raw of [
      "not json",
      JSON.stringify([{ subject: "synthetic-rep-0001", name: null }]),
      JSON.stringify({ items: "synthetic-rep-0001" }),
      JSON.stringify({ items: [{ name: "Ala" }] }),
      JSON.stringify({ items: [{ subject: "", name: "Ala" }] }),
      JSON.stringify({ items: [{ subject: "synthetic-rep-0001", name: 7 }] }),
      JSON.stringify({ items: [{ subject: "synthetic-rep-0001" }] }),
      JSON.stringify({
        items: [
          { subject: "synthetic-rep-0001", name: "Ala" },
          { subject: "synthetic-rep-0001", name: "Ola" },
        ],
      }),
    ]) {
      answer({ status: 200, raw });

      await expect(readReps(), raw).resolves.toEqual({ kind: "failed" });
    }
  });
});
