// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { createCustomer, type CustomerInput } from "../../src/api/customers";
import { CUSTOMERS_URL, stubCustomerApi } from "../support/customers-http";

const input: CustomerInput = { name: "Gospodarstwo Testowe", country: "PL", contacts: [] };

afterEach(() => {
  vi.unstubAllGlobals();
});

// EKO-1-35: the OpenAPI document does not require `detail` in a 422 answer, so the stub types
// allow its absence, and such an answer still names the request as rejected rather than failing.
describe("EKO-1-35 K-05 Domain: a 422 answer without detail", () => {
  it("is a rejection of the request as a whole", async () => {
    stubCustomerApi({ [`POST ${CUSTOMERS_URL}`]: { status: 422, body: {} } });

    await expect(createCustomer(input)).resolves.toEqual({
      kind: "rejected",
      fields: [{ field: "request" }],
    });
  });

  it("contrast: a 422 answer naming a field rejects that field", async () => {
    stubCustomerApi({
      [`POST ${CUSTOMERS_URL}`]: {
        status: 422,
        body: { detail: [{ type: "missing", loc: ["body", "name"], msg: "Field required" }] },
      },
    });

    await expect(createCustomer(input)).resolves.toEqual({
      kind: "rejected",
      fields: [{ field: "name" }],
    });
  });
});
