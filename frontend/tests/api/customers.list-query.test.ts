// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { type CustomerListQuery, listCustomers } from "../../src/api/customers";
import { CUSTOMERS_URL } from "../support/customers-http";

// EKO-3-04 Q-6 (QA): the backend's contract check pairs the declared `CustomerListQuery` with the
// OpenAPI operation's query parameters; it never reads the request the SPA builds. This file is
// the other half of that chain: the names in the list request's query string are exactly the
// declared type's keys, so a name typed into the request alone cannot drift past both checks.

// Every key of the type, each with a value; an excess or missing key fails type-checking.
const everyKey: { [K in keyof Required<CustomerListQuery>]: string } = {
  q: "kowal",
  owner: "synthetic-subject-0002",
};

function recordLists() {
  const sent: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const url = new URL(href, "http://spa.test");
      if (url.pathname !== CUSTOMERS_URL) {
        throw new Error(`Unexpected request ${href}`);
      }
      sent.push(url);
      return Promise.resolve(
        new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
  return sent;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EKO-3-04 Q-6: the list request's query names are the declared query type's keys", () => {
  it("a query with every declared key sends exactly those names, with their values", async () => {
    const sent = recordLists();

    await expect(listCustomers(everyKey)).resolves.toEqual({ kind: "listed", customers: [] });

    expect(sent).toHaveLength(1);
    const params = sent[0]?.searchParams;
    expect([...(params?.keys() ?? [])].sort()).toEqual(Object.keys(everyKey).sort());
    for (const [key, value] of Object.entries(everyKey)) {
      expect(params?.getAll(key)).toEqual([value]);
    }
  });

  it("contrast: the same call with no query sends no query names at all", async () => {
    const sent = recordLists();

    await listCustomers({});

    expect(sent).toHaveLength(1);
    expect(sent[0]?.search).toBe("");
  });
});

describe("EKO-3-08 K-07: the owner parameter is the chosen subject, exactly", () => {
  it("a subject holding URL-special characters arrives byte-equal in `owner`", async () => {
    const subject = "rep+1&x=y%20#z ąż";
    const sent = recordLists();

    await listCustomers({ owner: subject });

    expect(sent).toHaveLength(1);
    expect(sent[0]?.searchParams.getAll("owner")).toEqual([subject]);
    expect([...(sent[0]?.searchParams.keys() ?? [])]).toEqual(["owner"]);
  });

  it("a term and an owner are both sent", async () => {
    const sent = recordLists();

    await listCustomers({ q: " kowal ", owner: "synthetic-subject-0002" });

    expect(sent[0]?.searchParams.getAll("q")).toEqual(["kowal"]);
    expect(sent[0]?.searchParams.getAll("owner")).toEqual(["synthetic-subject-0002"]);
  });
});
