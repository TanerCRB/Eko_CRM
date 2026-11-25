import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import type { ValidationProblem } from "../../../src/api/customers";
import {
  CUSTOMER_URL,
  OTHER_NIP,
  contact,
  contactGroup,
  contactGroups,
  form,
  openCustomer,
  openEditForm,
  register,
  replace,
  requests,
  stored,
  storedWith,
} from "../../support/customers-edit";
import {
  CUSTOMERS_URL,
  VOIVODESHIPS_URL,
  deferred,
  stubCustomerApi,
  type CustomerReply,
} from "../../support/customers-http";

// EKO-3-05 K-07, the edit part: the form is the create form opened on the stored record, and a
// save states the whole customer in one PUT (G-6 A). Presentation and contract only; the rules
// are the server's (K-01, K-03).

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

const puts = (calls: Parameters<typeof requests>[0]) => requests(calls, "PUT", CUSTOMER_URL);

const storedBody = {
  name: stored.name,
  country: "PL",
  street: "Polna 7",
  postal_code: "05-850",
  town: "Ożarów",
  voivodeship: "mazowieckie",
  county: "warszawski zachodni",
  tax_id: stored.tax_id,
  contacts: [
    { kind: "phone", value: "+48601305101", note: "Właściciel", primary: true },
    { kind: "email", value: "zrodlane@example.invalid", note: "Biuro", primary: false },
  ],
};

function rejection(loc: (string | number)[]): CustomerReply {
  const body: ValidationProblem = { detail: [{ type: "value_error", loc, msg: "synthetic" }] };
  return { status: 422, body };
}

describe("K-07 edit: the form opens with the stored values and saves the whole customer", () => {
  it("the edit form opens with every stored value, contact and the primary marker", async () => {
    const user = userEvent.setup({ delay: null });
    await openCustomer(stored);

    await openEditForm(user);

    expect(form.name()).toHaveValue(stored.name);
    expect(form.country()).toHaveValue("PL");
    expect(form.nip()).toHaveValue(stored.tax_id);
    expect(form.street()).toHaveValue("Polna 7");
    expect(form.postalCode()).toHaveValue("05-850");
    expect(form.town()).toHaveValue("Ożarów");
    expect(form.voivodeship()).toHaveValue("mazowieckie");
    expect(form.county()).toHaveValue("warszawski zachodni");
    expect(contactGroups()).toHaveLength(2);
    expect(contact.kind(contactGroup(0))).toHaveValue("phone");
    expect(contact.value(contactGroup(0))).toHaveValue("+48601305101");
    expect(contact.note(contactGroup(0))).toHaveValue("Właściciel");
    expect(contact.primary(contactGroup(0))).toBeChecked();
    expect(contact.kind(contactGroup(1))).toHaveValue("email");
    expect(contact.value(contactGroup(1))).toHaveValue("zrodlane@example.invalid");
    expect(contact.note(contactGroup(1))).toHaveValue("Biuro");
    expect(contact.primary(contactGroup(1))).not.toBeChecked();
  });

  it("an unchanged save sends one PUT carrying the whole customer, country and contacts", async () => {
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, {
      [`PUT ${CUSTOMER_URL}`]: { status: 200, body: stored },
    });
    await openEditForm(user);

    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

    await screen.findByRole("heading", { level: 1, name: stored.name });
    expect(puts(calls)).toHaveLength(1);
    expect(puts(calls)[0]?.body).toEqual(storedBody);
  });

  it("edge: a customer with no contacts and the default country still sends both (M-z2)", async () => {
    const bare = storedWith({
      street: null,
      postal_code: null,
      town: null,
      voivodeship: null,
      county: null,
      tax_id: null,
      contacts: [],
    });
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(bare, {
      [`PUT ${CUSTOMER_URL}`]: { status: 200, body: bare },
    });
    await openEditForm(user);

    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

    await screen.findByRole("heading", { level: 1, name: bare.name });
    expect(puts(calls)[0]?.body).toEqual({ name: bare.name, country: "PL", contacts: [] });
  });

  it("a cleared field is not sent, and the view then shows the server's answer", async () => {
    const answered = storedWith({
      name: "Gospodarstwo Źródlane II",
      street: null,
      tax_id: null,
      contacts: [],
    });
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, {
      [`PUT ${CUSTOMER_URL}`]: { status: 200, body: answered },
    });
    await openEditForm(user);

    await replace(user, form.street(), "");
    await replace(user, form.nip(), "");
    await user.click(within(contactGroup(1)).getByRole("button", { name: "Usuń kontakt" }));
    await user.click(within(contactGroup(0)).getByRole("button", { name: "Usuń kontakt" }));
    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

    expect(await screen.findByRole("heading", { level: 1, name: answered.name })).toBeVisible();
    const body = puts(calls)[0]?.body as Record<string, unknown>;
    expect(body).not.toHaveProperty("street");
    expect(body).not.toHaveProperty("tax_id");
    expect(body["contacts"]).toEqual([]);
    expect(body["country"]).toBe("PL");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText("Nie dodano danych kontaktowych.")).toBeVisible();
    expect(screen.queryByText("Polna 7")).not.toBeInTheDocument();
  });

  it("edge: diacritics and markup entered in the form are sent as typed and shown as text", async () => {
    const markup = "<b>Żółć</b> & <img src=x onerror=alert(1)>";
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, {
      [`PUT ${CUSTOMER_URL}`]: { status: 200, body: storedWith({ name: markup }) },
    });
    await openEditForm(user);

    await replace(user, form.name(), markup);
    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

    expect(await screen.findByRole("heading", { level: 1, name: markup })).toBeVisible();
    expect((puts(calls)[0]?.body as { name: string }).name).toBe(markup);
    const main = screen.getByRole("main");
    expect(main.querySelector("b")).toBeNull();
    expect(main.querySelector("img")).toBeNull();
  });

  it("edge: a double click on save sends one PUT", async () => {
    const held = deferred<CustomerReply>();
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, { [`PUT ${CUSTOMER_URL}`]: () => held.promise });
    await openEditForm(user);

    await user.dblClick(screen.getByRole("button", { name: "Zapisz zmiany" }));
    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));
    held.resolve({ status: 200, body: stored });

    await screen.findByRole("heading", { level: 1, name: stored.name });
    expect(puts(calls)).toHaveLength(1);
  });

  it("edge: no entered or stored value enters the location or browser storage (ADR-0005-C13)", async () => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    const entered = "Gospodarstwo Ukryte";
    const user = userEvent.setup({ delay: null });
    await openCustomer(stored, {
      [`PUT ${CUSTOMER_URL}`]: { status: 200, body: storedWith({ name: entered }) },
    });
    const seen = [window.location.href];
    await openEditForm(user);
    await replace(user, form.name(), entered);
    await replace(user, form.town(), "Zakopane");
    seen.push(window.location.href);
    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));
    await screen.findByRole("heading", { level: 1, name: entered });
    seen.push(window.location.href);

    const values = [entered, "Zakopane", stored.name, stored.town ?? "", stored.tax_id ?? ""];
    for (const href of seen) {
      expect(new URL(href).pathname).toBe(`/klienci/${stored.id}`);
      expect(new URL(href).search).toBe("");
      expect(new URL(href).hash).toBe("");
      for (const value of values) {
        expect(decodeURIComponent(href)).not.toContain(value);
      }
    }
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
  });

  it("A-02: a refused edit (403) says the account cannot change customers and keeps the values", async () => {
    const user = userEvent.setup({ delay: null });
    await openCustomer(stored, {
      [`PUT ${CUSTOMER_URL}`]: { status: 403, body: { detail: "not permitted" } },
    });
    await openEditForm(user);
    await replace(user, form.town(), "Nowe Miasto");

    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

    expect(await screen.findByText("Twoje konto nie może zmieniać danych klientów.")).toBeVisible();
    expect(screen.queryByText("Twoje konto nie może dodawać klientów.")).not.toBeInTheDocument();
    expect(form.town()).toHaveValue("Nowe Miasto");
  });

  it("A-03: a stored contact of a kind the editor cannot show offers no edit form", async () => {
    const unknownKind = storedWith({
      contacts: [{ kind: "fax", value: "+48221305101", note: null, primary: false }],
    });
    await openCustomer(unknownKind);

    expect(screen.queryByRole("button", { name: "Edytuj dane" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archiwizuj klienta" })).toBeVisible();
  });

  it("cancelling the edit sends nothing and shows the stored record again", async () => {
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored);
    await openEditForm(user);

    await replace(user, form.name(), "Inna nazwa");
    await user.click(screen.getByRole("button", { name: "Anuluj" }));

    expect(await screen.findByRole("heading", { level: 1, name: stored.name })).toBeVisible();
    expect(calls.filter((call) => call.method !== "GET")).toEqual([]);
  });
});

// Each rejected `loc` with the field it names and the message create shows for it.
const REJECTIONS: { loc: (string | number)[]; field: () => HTMLElement; message: string }[] = [
  { loc: ["body", "name"], field: form.name, message: "Podaj nazwę klienta, najwyżej 120 znaków." },
  { loc: ["body", "country"], field: form.country, message: "Wybierz kraj z listy." },
  {
    loc: ["body", "postal_code"],
    field: form.postalCode,
    message: "Podaj kod pocztowy w formacie 00-000.",
  },
  { loc: ["body", "town"], field: form.town, message: "Podaj miejscowość, najwyżej 100 znaków." },
  {
    loc: ["body", "tax_id"],
    field: form.nip,
    message:
      "Podaj NIP: 10 cyfr z poprawną sumą kontrolną. Myślniki, spacje i prefiks PL są pomijane.",
  },
  {
    loc: ["body", "contacts", 1, "value"],
    field: () => contact.value(contactGroup(1)),
    message: "Podaj poprawny adres e-mail.",
  },
];

describe("K-07 edit: a 422 marks the field it names with create's message", () => {
  for (const { loc, field, message } of REJECTIONS) {
    it(`a 422 at ${loc.join(".")} marks that field and keeps the entered values`, async () => {
      const user = userEvent.setup({ delay: null });
      await openCustomer(stored, { [`PUT ${CUSTOMER_URL}`]: rejection(loc) });
      await openEditForm(user);
      await replace(user, form.town(), "Nowe Miasto");
      await replace(user, form.nip(), OTHER_NIP);

      await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

      expect(await screen.findByText("Nie zapisano klienta. Popraw zaznaczone pola.")).toBeVisible();
      expect(field()).toHaveAccessibleDescription(message);
      expect(form.town()).toHaveValue("Nowe Miasto");
      expect(form.nip()).toHaveValue(OTHER_NIP);
      expect(contact.value(contactGroup(1))).toHaveValue("zrodlane@example.invalid");
      expect(screen.getByRole("heading", { level: 1, name: "Edytuj klienta" })).toBeVisible();
    });
  }

  it("contrast: the same 422 loc shows the same message on create and on edit (M-z)", async () => {
    for (const { loc, message } of REJECTIONS) {
      const user = userEvent.setup({ delay: null });
      window.history.replaceState(null, "", "/klienci/nowy");
      stubCustomerApi({
        [`POST ${CUSTOMERS_URL}`]: rejection(loc),
        [`GET ${VOIVODESHIPS_URL}`]: { status: 200, body: register },
      });
      const view = render(<App />);
      await screen.findByRole("heading", { level: 1, name: "Nowy klient" });
      await replace(user, form.name(), "Gospodarstwo Porównawcze");
      if (loc[2] === 1) {
        for (let added = 0; added < 2; added += 1) {
          await user.click(screen.getByRole("button", { name: "Dodaj kontakt" }));
        }
        await user.selectOptions(contact.kind(contactGroup(1)), "email");
        await replace(user, contact.value(contactGroup(1)), "zle@");
      }
      await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
      await screen.findByText("Nie zapisano klienta. Popraw zaznaczone pola.");
      const onCreate = screen.getAllByRole("alert").map((alert) => alert.textContent);
      expect(onCreate).toContain(message);
      view.unmount();
      vi.unstubAllGlobals();
    }
  });
});
