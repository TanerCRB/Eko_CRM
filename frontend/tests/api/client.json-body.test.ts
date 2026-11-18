import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../src/api/client";
import { pageNavigation } from "../../src/api/navigation";

// EKO-3-01 (impact map, Frontend): the first request with a body goes through the one client.
const OPERATION = "/api/synthetic/operation";

function answer(status: number, text: string) {
  const response = new Response(text, { status, headers: { "content-type": "application/json" } });
  const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(response));
  vi.stubGlobal("fetch", fetchMock);
  return { response, fetchMock };
}

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("K-07 support: the API client sends a JSON body", () => {
  it("sends the body as JSON, declared as JSON, same-origin, and reads the answer to the end", async () => {
    const { response, fetchMock } = answer(201, '{"created":true}');
    const result = await apiRequest(OPERATION, { method: "POST", body: { name: "Gospodarstwo Testowe" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("same-origin");
    const headers = new Headers(init?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("accept")).toBe("application/json");
    expect(init?.body).toBe('{"name":"Gospodarstwo Testowe"}');
    expect(response.bodyUsed).toBe(true);
    expect(result).toEqual({ kind: "ok", status: 201, body: { created: true } });
  });

  it("contrast: a request without a body declares no content type and sends none", async () => {
    const { fetchMock } = answer(200, "{}");
    await apiRequest(OPERATION);
    const init = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).has("content-type")).toBe(false);
    expect(init?.body).toBeUndefined();
  });

  it("hands a 422 answer's body to the caller, so the form can name the rejected fields", async () => {
    const problem = { detail: [{ type: "value_error", loc: ["body", "name"], msg: "Value error" }] };
    answer(422, JSON.stringify(problem));
    expect(await apiRequest(OPERATION, { method: "POST", body: {} })).toEqual({
      kind: "failed",
      status: 422,
      body: problem,
    });
  });

  it("contrast: any other refusal still carries only its status", async () => {
    answer(403, '{"detail":"not permitted"}');
    expect(await apiRequest(OPERATION, { method: "POST", body: {} })).toStrictEqual({
      kind: "failed",
      status: 403,
    });
  });
});
