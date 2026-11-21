import { render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import { CUSTOMERS_URL, stubCustomerApi } from "../../support/customers-http";

// QA (EKO-3-02, fix round 2): since the answer type no longer models an answer without the
// address parts, `parseCustomer` alone reads a missing part as not given (A-08). The A-08 test in
// CustomerDetail.address.test.tsx looks at two of the six parts; this one looks at each part on
// its own, and its contrast differs from it in one thing only: the part is present in the answer.
// Synthetic values only (ADR-0005); the NIP is assembled at run time (G-7 A).
const CUSTOMER_ID = "5e6f7a8b-9c0d-4e1f-8a2b-3c4d5e6f7a8b";
const NAME = "Gospodarstwo Bez Adresu";
const STORED_NIP = "0".repeat(3) + "7654321";

const answer: Record<string, unknown> = {
  id: CUSTOMER_ID,
  name: NAME,
  country: "PL",
  contacts: [],
  street: "Zażółcona 3/5",
  postal_code: "90-001",
  town: "Łódź",
  voivodeship: "łódzkie",
  county: "zgierski",
  tax_id: STORED_NIP,
};

const PARTS = [
  ["street", "Ulica i numer"],
  ["postal_code", "Kod pocztowy"],
  ["town", "Miejscowość"],
  ["voivodeship", "Województwo"],
  ["county", "Powiat"],
  ["tax_id", "NIP"],
] as const;

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

async function openView(body: Record<string, unknown>) {
  window.history.replaceState(null, "", `/klienci/${CUSTOMER_ID}`);
  stubCustomerApi({
    [`GET ${CUSTOMERS_URL}/${CUSTOMER_ID}`]: { status: 200, raw: JSON.stringify(body) },
  });
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: NAME }, { timeout: 3000 });
}

function detail(term: string): string | null {
  const terms = screen.queryAllByRole("term").filter((element) => element.textContent === term);
  expect(terms).toHaveLength(1);
  return terms[0]?.nextElementSibling?.textContent ?? null;
}

describe("QA A-08 (EKO-3-02): each address part missing from an older answer reads as not given", () => {
  it.each(PARTS)("A-08: %s left out of the answer is shown as not given", async (part, label) => {
    const older = Object.fromEntries(Object.entries(answer).filter(([key]) => key !== part));

    await openView(older);

    expect(detail(label)).toBe("Nie podano");
  });

  it.each(PARTS)("contrast: %s present in the answer is shown as stored", async (part, label) => {
    await openView(answer);

    expect(detail(label)).toBe(answer[part]);
  });
});
