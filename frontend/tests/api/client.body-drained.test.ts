import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../src/api/client";
import { pageNavigation } from "../../src/api/navigation";

// EKO-2-02 K-08 browser leg: Chromium does not finish a fetch whose body is never read, so an
// unread 403 on the session read kept the no-role page from ever reaching network idle.

const OPERATION = "/api/synthetic/operation";

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("K-08: the client reads every answer's body to the end, whatever the status", () => {
  it.each([401, 403, 500, 503] as const)(
    "drains the body of a %i answer while still reporting it by status alone",
    async (status) => {
      const response = new Response('{"detail":"synthetic"}', { status });
      vi.stubGlobal(
        "fetch",
        vi.fn(() => Promise.resolve(response)),
      );

      const result = await apiRequest(OPERATION, { onUnauthenticated: "report" });

      expect(response.bodyUsed).toBe(true);
      expect(result.kind).not.toBe("ok");
    },
  );

  it("contrast: a 200 answer's body is read as before", async () => {
    const response = new Response('{"status":"logged_out"}', { status: 200 });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(response)),
    );

    const result = await apiRequest(OPERATION);

    expect(response.bodyUsed).toBe(true);
    expect(result).toEqual({ kind: "ok", status: 200, body: { status: "logged_out" } });
  });

  it("an answer whose body fails to read is still reported by its status", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.error(new TypeError("connection reset"));
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(body, { status: 403 }))),
    );

    expect(await apiRequest(OPERATION)).toEqual({ kind: "failed", status: 403 });
  });
});
