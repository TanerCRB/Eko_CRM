import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { apiRequest } from "../../src/api/client";
import { pageNavigation } from "../../src/api/navigation";
import { signedIn, stubFetch, unauthenticated, unavailable } from "../support/http";

const OPERATION = "/api/synthetic/operation";

let assign: MockInstance<(url: string) => void>;

beforeEach(() => {
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("K-03: any API 401 during use sends the user to login (central client)", () => {
  it("redirects to login with the current path and query on 401", async () => {
    window.history.replaceState(null, "", "/klienci?strona=2&sort=nazwa");
    stubFetch({ [OPERATION]: [unauthenticated] });

    const result = await apiRequest(OPERATION);

    expect(result).toEqual({ kind: "unauthenticated" });
    expect(assign).toHaveBeenCalledExactlyOnceWith(
      "/api/auth/login?return_to=%2Fklienci%3Fstrona%3D2%26sort%3Dnazwa",
    );
  });

  it("leaves navigation to the caller on 401 when asked to report it", async () => {
    stubFetch({ [OPERATION]: [unauthenticated] });

    const result = await apiRequest(OPERATION, { method: "POST", onUnauthenticated: "report" });

    expect(result).toEqual({ kind: "unauthenticated" });
    expect(assign).not.toHaveBeenCalled();
  });

  it("contrast: 200 returns the body and does not navigate", async () => {
    stubFetch({ [OPERATION]: [signedIn("Anna Testowa")] });

    const result = await apiRequest(OPERATION);

    expect(result).toEqual({
      kind: "ok",
      status: 200,
      body: { subject: "synthetic-subject-0001", name: "Anna Testowa" },
    });
    expect(assign).not.toHaveBeenCalled();
  });

  it("contrast: 503 and a network failure are 'unavailable', never a redirect", async () => {
    stubFetch({ [OPERATION]: [unavailable] });
    expect(await apiRequest(OPERATION)).toEqual({ kind: "unavailable" });

    stubFetch({ [OPERATION]: ["network-error"] });
    expect(await apiRequest(OPERATION)).toEqual({ kind: "unavailable" });

    expect(assign).not.toHaveBeenCalled();
  });

  it("reports any other status as failed with that status", async () => {
    stubFetch({ [OPERATION]: [{ status: 403, body: { detail: "origin refused" } }] });

    expect(await apiRequest(OPERATION, { method: "POST" })).toEqual({ kind: "failed", status: 403 });
    expect(assign).not.toHaveBeenCalled();
  });

  it("sends every request same-origin, asking for JSON, with no Authorization header", async () => {
    const { calls } = stubFetch({ [OPERATION]: [signedIn(null)] });

    await apiRequest(OPERATION, { method: "POST" });

    expect(calls).toHaveLength(1);
    const init = calls[0]?.init;
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("same-origin");
    const headers = new Headers(init?.headers);
    expect(headers.get("accept")).toBe("application/json");
    expect(headers.has("authorization")).toBe(false);
  });
});
