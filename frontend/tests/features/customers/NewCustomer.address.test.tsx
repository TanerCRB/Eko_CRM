import { render, screen, waitFor } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import type { CustomerRecord } from "../../../src/api/customers";
import type { VoivodeshipList } from "../../../src/api/reference";
import {
  CUSTOMERS_URL,
  deferred,
  stubCustomerApi,
  VOIVODESHIPS_URL,
  type CustomerReply,
  type RecordedCall,
  type ReplySource,
} from "../../support/customers-http";

// K-07 (EKO-3-02): the create form's address and tax-ID fields. Presentation only; the rules are
// the server's (K-01..K-05). Synthetic values throughout (ADR-0005); the NIP is assembled at run
// time from a `000` prefix, so no NIP-shaped literal sits in the source (G-7 A).
const CUSTOMER_ID = "5d2e8f1a-3b4c-4d5e-8f6a-7b8c9d0e1f2a";
const NAME = "Gospodarstwo Adresowe";
const STREET = "Testowa 12";
const POSTAL_CODE = "00-950";
const TOWN = "Łódź";
const STORED_NIP = "0".repeat(3) + "1234567";
const ENTERED_NIP = `PL ${STORED_NIP.slice(0, 3)}-${STORED_NIP.slice(3, 6)}-${STORED_NIP.slice(6, 8)}-${STORED_NIP.slice(8)}`;
const FOREIGN_TAX_ID = "DE-Steuer 42/7";

// A synthetic slice of the register: the real answer has 16 voivodeships and 380 counties.
const register: VoivodeshipList = {
  as_of: "2026-01-01",
  voivodeships: [
    { name: "mazowieckie", counties: ["warszawski zachodni", "Warszawa"] },
    { name: "podlaskie", counties: ["bielski", "hajnowski"] },
    { name: "śląskie", counties: ["bielski", "cieszyński"] },
  ],
};
const registerReply: CustomerReply = { status: 200, body: register };
const emptyList: CustomerReply = { status: 200, body: { items: [] } };

function savedCustomer(overrides: Partial<CustomerRecord> = {}): CustomerRecord {
  return {
    id: CUSTOMER_ID,
    name: NAME,
    country: "PL",
    street: null,
    postal_code: null,
    town: null,
    voivodeship: null,
    county: null,
    tax_id: null,
    contacts: [],
    archived: false,
    ...overrides,
  };
}

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.history.replaceState(null, "", "/klienci/nowy");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function stub(post: ReplySource, voivodeships: ReplySource = registerReply) {
  return stubCustomerApi({
    [`GET ${CUSTOMERS_URL}`]: emptyList,
    [`GET ${VOIVODESHIPS_URL}`]: voivodeships,
    [`POST ${CUSTOMERS_URL}`]: post,
  });
}

async function openForm() {
  const user = userEvent.setup({ delay: null });
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: "Nowy klient" });
  return user;
}

async function enter(user: UserEvent, field: HTMLElement, value: string) {
  await user.click(field);
  await user.paste(value);
}

// Field and SelectField render an error inside the label, so the name continues past the label.
const label = {
  name: /^Nazwa klienta/,
  country: /^Kraj/,
  street: /^Ulica i numer/,
  postalCode: /^Kod pocztowy/,
  town: /^Miejscowość/,
  voivodeship: /^Województwo/,
  county: /^Powiat/,
  nip: /^NIP/,
  foreignTaxId: /^Numer podatkowy/,
};

async function voivodeshipSelect() {
  const select = screen.getByLabelText(label.voivodeship);
  await waitFor(() => {
    expect(select).toBeEnabled();
  });
  return select;
}

async function fillPolishAddress(user: UserEvent) {
  await enter(user, screen.getByLabelText(label.name), NAME);
  await enter(user, screen.getByLabelText(label.street), STREET);
  await enter(user, screen.getByLabelText(label.postalCode), POSTAL_CODE);
  await enter(user, screen.getByLabelText(label.town), TOWN);
  await user.selectOptions(await voivodeshipSelect(), "mazowieckie");
  await user.selectOptions(screen.getByLabelText(label.county), "warszawski zachodni");
  await enter(user, screen.getByLabelText(label.nip), ENTERED_NIP);
}

function posts(calls: readonly RecordedCall[]) {
  return calls.filter((call) => call.method === "POST" && call.url === CUSTOMERS_URL);
}

async function save(user: UserEvent) {
  await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
}

describe("K-07 (EKO-3-02): the create form carries the address and tax ID, per country", () => {
  it("for Poland shows street, postal code, town, voivodeship, county and NIP", async () => {
    stub({ status: 201, body: savedCustomer() });
    await openForm();

    expect(screen.getByLabelText(label.country)).toHaveValue("PL");
    for (const field of [label.street, label.postalCode, label.town, label.nip]) {
      expect(screen.getByLabelText(field)).toBeVisible();
    }
    const voivodeship = await voivodeshipSelect();
    expect(voivodeship).toBeVisible();
    expect(screen.getByLabelText(label.county)).toBeVisible();
    expect(screen.getByRole("option", { name: "mazowieckie" })).toBeInTheDocument();
  });

  it("contrast: switching to Germany hides voivodeship and county, switching back shows them", async () => {
    stub({ status: 201, body: savedCustomer() });
    const user = await openForm();
    await voivodeshipSelect();

    await user.selectOptions(screen.getByLabelText(label.country), "DE");

    expect(screen.queryByLabelText(label.voivodeship)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(label.county)).not.toBeInTheDocument();
    for (const field of [label.street, label.postalCode, label.town, label.foreignTaxId]) {
      expect(screen.getByLabelText(field)).toBeVisible();
    }
    expect(screen.queryByLabelText(label.nip)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(label.country), "PL");

    expect(screen.getByLabelText(label.voivodeship)).toBeVisible();
    expect(screen.getByLabelText(label.county)).toBeVisible();
    expect(screen.getByLabelText(label.nip)).toBeVisible();
  });

  it("sends every entered address part and the tax ID as entered for Poland", async () => {
    const { calls } = stub({
      status: 201,
      body: savedCustomer({
        street: STREET,
        postal_code: POSTAL_CODE,
        town: TOWN,
        voivodeship: "mazowieckie",
        county: "warszawski zachodni",
        tax_id: STORED_NIP,
      }),
    });
    const user = await openForm();
    await fillPolishAddress(user);

    await save(user);

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)).toHaveLength(1);
    expect(posts(calls)[0]?.body).toEqual({
      name: NAME,
      country: "PL",
      street: STREET,
      postal_code: POSTAL_CODE,
      town: TOWN,
      voivodeship: "mazowieckie",
      county: "warszawski zachodni",
      tax_id: ENTERED_NIP,
      contacts: [],
    });
  });

  it("contrast: after picking mazowieckie and switching to Germany, the create sends neither voivodeship nor county", async () => {
    const { calls } = stub({
      status: 201,
      body: savedCustomer({ country: "DE", street: STREET, postal_code: POSTAL_CODE, town: TOWN }),
    });
    const user = await openForm();
    await fillPolishAddress(user);

    await user.selectOptions(screen.getByLabelText(label.country), "DE");
    await save(user);

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)).toHaveLength(1);
    const sent = posts(calls)[0]?.body as Record<string, unknown>;
    expect(sent).not.toHaveProperty("voivodeship");
    expect(sent).not.toHaveProperty("county");
    expect(sent).toMatchObject({
      country: "DE",
      street: STREET,
      postal_code: POSTAL_CODE,
      town: TOWN,
      tax_id: ENTERED_NIP,
    });
  });
});

describe("K-07 (EKO-3-02): a server field error marks its own field and keeps every value", () => {
  const cases = [
    {
      loc: "postal_code",
      field: label.postalCode,
      message: "Podaj kod pocztowy w formacie 00-000.",
    },
    {
      loc: "voivodeship",
      field: label.voivodeship,
      message: "Wybierz jedno z 16 województw.",
    },
    {
      loc: "county",
      field: label.county,
      message: "Ten powiat nie leży w wybranym województwie.",
    },
    {
      loc: "tax_id",
      field: label.nip,
      message: "Podaj NIP: 10 cyfr z poprawną sumą kontrolną. Myślniki, spacje i prefiks PL są pomijane.",
    },
    {
      loc: "street",
      field: label.street,
      message: "Podaj ulicę i numer, najwyżej 150 znaków.",
    },
    {
      loc: "town",
      field: label.town,
      message: "Podaj miejscowość, najwyżej 100 znaków.",
    },
  ] as const;

  it.each(cases)("a 422 at $loc marks exactly that field", async ({ loc, field, message }) => {
    const { calls } = stub({
      status: 422,
      body: { detail: [{ type: "value_error", loc: ["body", loc], msg: "Value error, synthetic" }] },
    });
    const user = await openForm();
    await fillPolishAddress(user);

    await save(user);

    expect(await screen.findByText("Nie zapisano klienta. Popraw zaznaczone pola.")).toBeVisible();
    const marked = screen.getByLabelText(field);
    expect(marked).toHaveAttribute("aria-invalid", "true");
    expect(marked).toHaveAccessibleDescription(message);
    const others = Object.values(label).filter(
      (other) => other !== field && other !== label.foreignTaxId,
    );
    for (const other of others) {
      expect(screen.getByLabelText(other)).not.toHaveAttribute("aria-invalid");
    }
    expect(screen.getByLabelText(label.name)).toHaveValue(NAME);
    expect(screen.getByLabelText(label.street)).toHaveValue(STREET);
    expect(screen.getByLabelText(label.postalCode)).toHaveValue(POSTAL_CODE);
    expect(screen.getByLabelText(label.town)).toHaveValue(TOWN);
    expect(screen.getByLabelText(label.voivodeship)).toHaveValue("mazowieckie");
    expect(screen.getByLabelText(label.county)).toHaveValue("warszawski zachodni");
    expect(screen.getByLabelText(label.nip)).toHaveValue(ENTERED_NIP);
    expect(screen.getByRole("heading", { level: 1, name: "Nowy klient" })).toBeVisible();
    expect(posts(calls)).toHaveLength(1);
  });

  it("a foreign postal code or tax ID error says the foreign bound, not the Polish rule", async () => {
    stub({
      status: 422,
      body: {
        detail: [
          { type: "string_too_long", loc: ["body", "postal_code"], msg: "synthetic" },
          { type: "string_too_long", loc: ["body", "tax_id"], msg: "synthetic" },
        ],
      },
    });
    const user = await openForm();
    await enter(user, screen.getByLabelText(label.name), NAME);
    await user.selectOptions(screen.getByLabelText(label.country), "DE");
    await enter(user, screen.getByLabelText(label.postalCode), POSTAL_CODE);
    await enter(user, screen.getByLabelText(label.foreignTaxId), FOREIGN_TAX_ID);

    await save(user);

    expect(await screen.findByText("Nie zapisano klienta. Popraw zaznaczone pola.")).toBeVisible();
    expect(screen.getByLabelText(label.postalCode)).toHaveAccessibleDescription(
      "Kod pocztowy może mieć najwyżej 20 znaków.",
    );
    expect(screen.getByLabelText(label.foreignTaxId)).toHaveAccessibleDescription(
      "Numer podatkowy może mieć najwyżej 32 znaki.",
    );
    expect(screen.getByLabelText(label.foreignTaxId)).toHaveValue(FOREIGN_TAX_ID);
  });

  it("edge: an error on a field that is hidden falls back to the form-level alert", async () => {
    stub({
      status: 422,
      body: { detail: [{ type: "value_error", loc: ["body", "county"], msg: "synthetic" }] },
    });
    const user = await openForm();
    await fillPolishAddress(user);
    await save(user);
    await screen.findByText("Nie zapisano klienta. Popraw zaznaczone pola.");

    await user.selectOptions(screen.getByLabelText(label.country), "DE");

    expect(screen.queryByLabelText(label.county)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Województwo lub powiat wymaga poprawy. Te pola dotyczą tylko klientów z Polski.",
      ),
    ).toBeVisible();
  });

  it("edge: a double submit with an address still sends one create request", async () => {
    const held = deferred<CustomerReply>();
    const { calls } = stub(() => held.promise);
    const user = await openForm();
    await fillPolishAddress(user);

    await user.dblClick(screen.getByRole("button", { name: "Zapisz klienta" }));
    await save(user);
    held.resolve({ status: 201, body: savedCustomer({ street: STREET }) });

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)).toHaveLength(1);
  });
});

describe("K-07 assumptions (EKO-3-02): the address part of the form", () => {
  it("A-01: a field left empty is not sent at all", async () => {
    const { calls } = stub({ status: 201, body: savedCustomer() });
    const user = await openForm();
    await voivodeshipSelect();
    await enter(user, screen.getByLabelText(label.name), NAME);

    await save(user);

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)[0]?.body).toEqual({ name: NAME, country: "PL", contacts: [] });
  });

  it("A-02: the county list is the chosen voivodeship's, and another voivodeship clears the county", async () => {
    stub({ status: 201, body: savedCustomer() });
    const user = await openForm();
    const voivodeship = await voivodeshipSelect();
    const county = screen.getByLabelText(label.county);
    expect(county).toBeDisabled();
    expect(county).toHaveDisplayValue("Najpierw wybierz województwo");

    await user.selectOptions(voivodeship, "podlaskie");
    expect(county).toBeEnabled();
    expect(screen.getByRole("option", { name: "hajnowski" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "cieszyński" })).not.toBeInTheDocument();
    await user.selectOptions(county, "bielski");

    await user.selectOptions(voivodeship, "śląskie");

    expect(county).toHaveValue("");
    expect(screen.getByRole("option", { name: "cieszyński" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "hajnowski" })).not.toBeInTheDocument();
  });

  it("A-03: a voivodeship picked before switching away is picked again on switching back", async () => {
    const { calls } = stub({ status: 201, body: savedCustomer() });
    const user = await openForm();
    await fillPolishAddress(user);

    await user.selectOptions(screen.getByLabelText(label.country), "DE");
    await user.selectOptions(screen.getByLabelText(label.country), "PL");

    expect(screen.getByLabelText(label.voivodeship)).toHaveValue("mazowieckie");
    expect(screen.getByLabelText(label.county)).toHaveValue("warszawski zachodni");
    await save(user);
    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)[0]?.body).toMatchObject({
      voivodeship: "mazowieckie",
      county: "warszawski zachodni",
    });
  });

  it("A-04: the tax-ID field keeps its value when the country changes, under the label of the country", async () => {
    stub({ status: 201, body: savedCustomer() });
    const user = await openForm();
    await enter(user, screen.getByLabelText(label.nip), FOREIGN_TAX_ID);

    await user.selectOptions(screen.getByLabelText(label.country), "DE");

    expect(screen.getByLabelText(label.foreignTaxId)).toHaveValue(FOREIGN_TAX_ID);
  });

  it("A-05: while the list loads the voivodeship cannot be picked yet", async () => {
    const held = deferred<CustomerReply>();
    stub({ status: 201, body: savedCustomer() }, () => held.promise);
    await openForm();

    expect(screen.getByLabelText(label.voivodeship)).toBeDisabled();
    expect(screen.getByText("Ładowanie listy województw…")).toBeVisible();

    held.resolve(registerReply);
    expect(await voivodeshipSelect()).toBeEnabled();
    expect(screen.queryByText("Ładowanie listy województw…")).not.toBeInTheDocument();
  });

  it("A-06: a list that fails to load is shown as an error and the customer still saves without it", async () => {
    const { calls } = stub(
      { status: 201, body: savedCustomer() },
      { status: 500, body: { detail: "synthetic failure" } },
    );
    const user = await openForm();

    expect(
      await screen.findByText(
        "Nie udało się wczytać listy województw i powiatów. Klienta można zapisać bez nich.",
      ),
    ).toBeVisible();
    expect(screen.getByLabelText(label.voivodeship)).toBeDisabled();
    expect(screen.getByLabelText(label.county)).toBeDisabled();
    await enter(user, screen.getByLabelText(label.name), NAME);
    await enter(user, screen.getByLabelText(label.street), STREET);
    await save(user);

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)[0]?.body).toEqual({
      name: NAME,
      country: "PL",
      street: STREET,
      contacts: [],
    });
  });

  it("A-06: a list of an unexpected shape is the same error, never an empty select", async () => {
    stub({ status: 201, body: savedCustomer() }, { status: 200, raw: '{"voivodeships":[{"name":5}]}' });
    await openForm();

    expect(
      await screen.findByText(
        "Nie udało się wczytać listy województw i powiatów. Klienta można zapisać bez nich.",
      ),
    ).toBeVisible();
  });
});

describe("K-07 invariants (EKO-3-02): the impact map's frontend rules on the new fields", () => {
  it("no address or tax-ID value reaches the location or browser storage (ADR-0005-C12, C13)", async () => {
    const { calls } = stub({
      status: 201,
      body: savedCustomer({ street: STREET, postal_code: POSTAL_CODE, town: TOWN, tax_id: STORED_NIP }),
    });
    window.localStorage.clear();
    window.sessionStorage.clear();
    const user = await openForm();
    await fillPolishAddress(user);
    const before = window.location.href;
    await save(user);
    await screen.findByRole("heading", { level: 1, name: NAME });

    expect(posts(calls)).toHaveLength(1);
    for (const href of [before, window.location.href]) {
      const decoded = decodeURIComponent(href);
      for (const value of [STREET, POSTAL_CODE, TOWN, "mazowieckie", ENTERED_NIP, STORED_NIP]) {
        expect(decoded).not.toContain(value);
      }
    }
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
  });
});
