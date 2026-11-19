import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import type { CustomerRecord } from "../../../src/api/customers";
import {
  CUSTOMERS_URL,
  stubCustomerApi,
  VOIVODESHIPS_URL,
  type CustomerReply,
} from "../../support/customers-http";

// K-07 (EKO-3-02): the customer view shows the stored address and tax ID. Synthetic values only
// (ADR-0005); the NIP is assembled at run time, so no NIP-shaped literal sits here (G-7 A).
const CUSTOMER_ID = "8c1d2e3f-4a5b-4c6d-9e7f-0a1b2c3d4e5f";
const CUSTOMER_URL = `${CUSTOMERS_URL}/${CUSTOMER_ID}`;
const NAME = "Gospodarstwo Widoczne";
const STORED_NIP = "0".repeat(3) + "7654321";
const ENTERED_NIP = `PL ${STORED_NIP.slice(0, 3)} ${STORED_NIP.slice(3, 6)} ${STORED_NIP.slice(6)}`;

const polish: CustomerRecord = {
  id: CUSTOMER_ID,
  name: NAME,
  country: "PL",
  street: "Zażółcona 3/5",
  postal_code: "90-001",
  town: "Łódź",
  voivodeship: "łódzkie",
  county: "Łódź",
  tax_id: STORED_NIP,
  contacts: [],
};

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

function openView(reply: CustomerReply) {
  window.history.replaceState(null, "", `/klienci/${CUSTOMER_ID}`);
  stubCustomerApi({ [`GET ${CUSTOMER_URL}`]: reply });
  render(<App />);
  return screen.findByRole("heading", { level: 1, name: NAME });
}

// The value a description list gives for a term, as the rep reads it beside its label.
function detail(term: string): string | null {
  const terms = screen.queryAllByRole("term").filter((element) => element.textContent === term);
  if (terms.length === 0) {
    return null;
  }
  expect(terms).toHaveLength(1);
  const definition = terms[0]?.nextElementSibling;
  expect(definition).not.toBeNull();
  return definition?.textContent ?? null;
}

describe("K-07 (EKO-3-02): the customer view shows the stored address and tax ID", () => {
  it("shows each stored address part and the NIP beside its own label", async () => {
    await openView({ status: 200, body: polish });

    expect(detail("Ulica i numer")).toBe("Zażółcona 3/5");
    expect(detail("Kod pocztowy")).toBe("90-001");
    expect(detail("Miejscowość")).toBe("Łódź");
    expect(detail("Województwo")).toBe("łódzkie");
    expect(detail("Powiat")).toBe("Łódź");
    expect(detail("NIP")).toBe(STORED_NIP);
    expect(detail("Kraj")).toBe("Polska");
  });

  it("contrast: after a create the view shows the server's ten digits, not the NIP as typed", async () => {
    window.history.replaceState(null, "", "/klienci/nowy");
    const register: CustomerReply = {
      status: 200,
      body: { as_of: "2026-01-01", voivodeships: [{ name: "łódzkie", counties: ["Łódź"] }] },
    };
    stubCustomerApi({
      [`GET ${VOIVODESHIPS_URL}`]: register,
      [`POST ${CUSTOMERS_URL}`]: { status: 201, body: polish },
    });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "Nowy klient" });
    await user.click(screen.getByLabelText(/^Nazwa klienta/));
    await user.paste(NAME);
    await user.click(screen.getByLabelText(/^NIP/));
    await user.paste(ENTERED_NIP);

    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(detail("NIP")).toBe(STORED_NIP);
    expect(screen.queryByText(ENTERED_NIP)).not.toBeInTheDocument();
    expect(detail("Ulica i numer")).toBe("Zażółcona 3/5");
  });

  it("a foreign customer's tax ID is shown as its tax number, with no voivodeship or county", async () => {
    await openView({
      status: 200,
      body: {
        ...polish,
        country: "DE",
        postal_code: "10115",
        town: "Berlin",
        voivodeship: null,
        county: null,
        tax_id: "DE-Steuer 42/7",
      },
    });

    expect(detail("Numer podatkowy")).toBe("DE-Steuer 42/7");
    expect(detail("NIP")).toBeNull();
    expect(detail("Województwo")).toBeNull();
    expect(detail("Powiat")).toBeNull();
    expect(detail("Kod pocztowy")).toBe("10115");
    expect(detail("Kraj")).toBe("Niemcy");
  });

  it("edge: markup in the street renders as text", async () => {
    const markup = "<img src=x onerror=alert(1)> 7";
    await openView({ status: 200, body: { ...polish, street: markup } });

    expect(detail("Ulica i numer")).toBe(markup);
    const main = screen.getByRole("main");
    expect(main.querySelector("img")).toBeNull();
  });

  it("edge: diacritics show as stored", async () => {
    await openView({ status: 200, body: { ...polish, street: "Źródlana 1", town: "Żółkiewka" } });

    expect(within(screen.getByRole("main")).getByText("Źródlana 1")).toBeVisible();
    expect(detail("Miejscowość")).toBe("Żółkiewka");
  });
});

describe("K-07 assumptions (EKO-3-02): the customer view's address states", () => {
  it("A-07: a part that was not given is shown as not given", async () => {
    await openView({
      status: 200,
      body: { ...polish, street: null, voivodeship: null, county: null, tax_id: null },
    });

    expect(detail("Ulica i numer")).toBe("Nie podano");
    expect(detail("Województwo")).toBe("Nie podano");
    expect(detail("Powiat")).toBe("Nie podano");
    expect(detail("NIP")).toBe("Nie podano");
    expect(detail("Miejscowość")).toBe("Łódź");
  });

  it("A-08: an answer from a backend without the new fields still shows the customer, as not given", async () => {
    await openView({
      status: 200,
      raw: JSON.stringify({ id: CUSTOMER_ID, name: NAME, country: "PL", contacts: [] }),
    });

    expect(detail("Ulica i numer")).toBe("Nie podano");
    expect(detail("NIP")).toBe("Nie podano");
  });

  it("A-08: an address part of an unexpected type is an error, never a half-rendered record", async () => {
    window.history.replaceState(null, "", `/klienci/${CUSTOMER_ID}`);
    stubCustomerApi({
      [`GET ${CUSTOMER_URL}`]: {
        status: 200,
        raw: JSON.stringify({ ...polish, postal_code: 90001 }),
      },
    });
    render(<App />);

    expect(await screen.findByText("Nie udało się wczytać klienta.")).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: NAME })).not.toBeInTheDocument();
  });
});
