import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import type { CustomerRecord } from "../../../src/api/customers";
import {
  CUSTOMERS_URL,
  deferred,
  stubCustomerApi,
  type CustomerReply,
  type RecordedCall,
} from "../../support/customers-http";

// K-07 (EKO-3-01): presentation only. Synthetic values throughout (ADR-0005); the entered phone
// is the criterion's number written without separators, so the K-07 changeset guard has nothing
// to flag, and the server's E.164 answer still differs from what the rep typed.
const CUSTOMER_ID = "3f0c2a4e-8b1d-4c6a-9e2f-5a7b8c9d0e1f";
const CUSTOMER_URL = `${CUSTOMERS_URL}/${CUSTOMER_ID}`;
const NAME = "Gospodarstwo Testowe";
const ENTERED_PHONE = "601234567";
const STORED_PHONE = "+48601234567";
const ENTERED_SECOND_PHONE = "+49 30 1234567";
const STORED_SECOND_PHONE = "+49301234567";
const EMAIL = "farm1@example.invalid";
const NOTE_OWNER = "Właściciel gospodarstwa";
const NOTE_OFFICE = "Biuro";
const NOTE_EMAIL = "Faktury";

const saved: CustomerRecord = {
  id: CUSTOMER_ID,
  name: NAME,
  country: "PL",
  contacts: [
    { kind: "phone", value: STORED_PHONE, note: NOTE_OWNER, primary: true },
    { kind: "phone", value: STORED_SECOND_PHONE, note: NOTE_OFFICE, primary: false },
    { kind: "email", value: EMAIL, note: NOTE_EMAIL, primary: false },
  ],
};

const emptyList: CustomerReply = { status: 200, body: { items: [] } };
const listOfOne: CustomerReply = {
  status: 200,
  body: { items: [{ id: CUSTOMER_ID, name: NAME, country: "PL" }] },
};

interface ContactEntry {
  kind: "phone" | "email";
  value: string;
  note?: string;
}

// The lazy destination's first import is transformed on demand; done here, its cost cannot fall
// inside the first test's one-second wait for the screen and fail it only when the suite is busy.
beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.history.replaceState(null, "", "/klienci");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

async function openCreateForm(user: UserEvent) {
  render(<App />);
  await user.click(await screen.findByRole("link", { name: "Dodaj klienta" }));
  return screen.findByRole("heading", { level: 1, name: "Nowy klient" });
}

function contactGroups() {
  return screen.getAllByRole("group", { name: /^Kontakt \d+$/ });
}

async function addContact(user: UserEvent, entry: ContactEntry) {
  await user.click(screen.getByRole("button", { name: "Dodaj kontakt" }));
  const group = contactGroups().at(-1);
  if (group === undefined) {
    throw new Error("no contact row appeared");
  }
  const scope = within(group);
  await user.selectOptions(scope.getByLabelText("Rodzaj kontaktu"), entry.kind);
  await user.type(scope.getByLabelText("Numer telefonu lub adres e-mail"), entry.value);
  if (entry.note !== undefined) {
    await user.type(scope.getByLabelText("Opis kontaktu"), entry.note);
  }
  return group;
}

function primaryRadio(group: HTMLElement) {
  return within(group).getByRole("radio", { name: "Kontakt główny" });
}

async function fillTheCriterionCustomer(user: UserEvent) {
  await user.type(screen.getByLabelText(/Nazwa klienta/), NAME);
  const first = await addContact(user, { kind: "phone", value: ENTERED_PHONE, note: NOTE_OWNER });
  await addContact(user, { kind: "phone", value: ENTERED_SECOND_PHONE, note: NOTE_OFFICE });
  await addContact(user, { kind: "email", value: EMAIL, note: NOTE_EMAIL });
  await user.click(primaryRadio(first));
}

function posts(calls: readonly RecordedCall[]) {
  return calls.filter((call) => call.method === "POST" && call.url === CUSTOMERS_URL);
}

describe("K-07: in the SPA a rep creates a customer with contacts and sees the server's record", () => {
  it("sends one create with the entered values and then shows the record the server returned", async () => {
    const { calls } = stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: emptyList,
      [`POST ${CUSTOMERS_URL}`]: { status: 201, body: saved },
    });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    const country = screen.getByLabelText(/Kraj/);
    expect(country).toHaveValue("PL");
    expect(country).toHaveDisplayValue("Polska");
    await fillTheCriterionCustomer(user);

    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));

    const heading = await screen.findByRole("heading", { level: 1, name: NAME });
    expect(heading).toBeVisible();
    expect(posts(calls)).toHaveLength(1);
    expect(posts(calls)[0]?.body).toEqual({
      name: NAME,
      country: "PL",
      contacts: [
        { kind: "phone", value: ENTERED_PHONE, note: NOTE_OWNER, primary: true },
        { kind: "phone", value: ENTERED_SECOND_PHONE, note: NOTE_OFFICE, primary: false },
        { kind: "email", value: EMAIL, note: NOTE_EMAIL, primary: false },
      ],
    });
    const contacts = within(screen.getByRole("list", { name: "Kontakty" })).getAllByRole("listitem");
    expect(contacts).toHaveLength(3);
    expect(within(contacts[0] as HTMLElement).getByText(STORED_PHONE)).toBeVisible();
    expect(within(contacts[0] as HTMLElement).getByText(NOTE_OWNER)).toBeVisible();
    expect(within(contacts[0] as HTMLElement).getByText("Kontakt główny")).toBeVisible();
    expect(within(contacts[1] as HTMLElement).getByText(STORED_SECOND_PHONE)).toBeVisible();
    expect(within(contacts[1] as HTMLElement).queryByText("Kontakt główny")).not.toBeInTheDocument();
    expect(within(contacts[2] as HTMLElement).getByText(EMAIL)).toBeVisible();
    expect(screen.getByText("Polska")).toBeVisible();
  });

  it("contrast: the view shows the server's +48 form, not the number the rep typed", async () => {
    stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: emptyList,
      [`POST ${CUSTOMERS_URL}`]: { status: 201, body: saved },
    });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    await fillTheCriterionCustomer(user);
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(screen.getByText(STORED_PHONE)).toBeVisible();
    expect(screen.queryByText(ENTERED_PHONE)).not.toBeInTheDocument();
    expect(screen.queryByText(ENTERED_SECOND_PHONE)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("contrast: a rejection is shown, the entered values stay, and nothing is shown as saved", async () => {
    const { calls } = stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: emptyList,
      [`POST ${CUSTOMERS_URL}`]: {
        status: 422,
        body: {
          detail: [
            {
              type: "value_error",
              loc: ["body", "contacts", 2, "value"],
              msg: "Value error, not an e-mail address",
            },
          ],
        },
      },
    });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    await fillTheCriterionCustomer(user);
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));

    expect(await screen.findByText("Nie zapisano klienta. Popraw zaznaczone pola.")).toBeVisible();
    const emailRow = within(contactGroups()[2] as HTMLElement);
    // Field renders its error inside the label, so the label text continues past the field name.
    const emailValue = emailRow.getByLabelText(/^Numer telefonu lub adres e-mail/);
    expect(emailValue).toHaveValue(EMAIL);
    expect(emailValue).toHaveAccessibleDescription(
      "Podaj poprawny adres e-mail.",
    );
    expect(screen.getByLabelText(/Nazwa klienta/)).toHaveValue(NAME);
    expect(
      within(contactGroups()[0] as HTMLElement).getByLabelText("Numer telefonu lub adres e-mail"),
    ).toHaveValue(ENTERED_PHONE);
    expect(primaryRadio(contactGroups()[0] as HTMLElement)).toBeChecked();
    expect(screen.getByRole("heading", { level: 1, name: "Nowy klient" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: NAME })).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Kontakty" })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/klienci/nowy");
    expect(posts(calls)).toHaveLength(1);
  });

  it("contrast: a refused create is shown as a refusal and keeps the entered values", async () => {
    stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: emptyList,
      [`POST ${CUSTOMERS_URL}`]: { status: 403, body: { detail: "not permitted" } },
    });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    await user.type(screen.getByLabelText(/Nazwa klienta/), NAME);
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));

    expect(await screen.findByText("Twoje konto nie może dodawać klientów.")).toBeVisible();
    expect(screen.getByLabelText(/Nazwa klienta/)).toHaveValue(NAME);
    expect(screen.queryByRole("heading", { level: 1, name: NAME })).not.toBeInTheDocument();
  });

  it("marking a second contact primary clears the first, and the create sends one primary", async () => {
    const { calls } = stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: emptyList,
      [`POST ${CUSTOMERS_URL}`]: { status: 201, body: saved },
    });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    await user.type(screen.getByLabelText(/Nazwa klienta/), NAME);
    const first = await addContact(user, { kind: "phone", value: ENTERED_PHONE });
    const second = await addContact(user, { kind: "email", value: EMAIL });

    await user.click(primaryRadio(first));
    expect(primaryRadio(first)).toBeChecked();
    await user.click(primaryRadio(second));
    expect(primaryRadio(second)).toBeChecked();
    expect(primaryRadio(first)).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
    await screen.findByRole("heading", { level: 1, name: NAME });
    const sent = posts(calls)[0]?.body as { contacts: { primary: boolean }[] };
    expect(sent.contacts.map((contact) => contact.primary)).toEqual([false, true]);
  });

  it("edge: a double click on save sends one create request", async () => {
    const held = deferred<CustomerReply>();
    const { calls } = stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: emptyList,
      [`POST ${CUSTOMERS_URL}`]: () => held.promise,
    });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    await user.type(screen.getByLabelText(/Nazwa klienta/), NAME);

    await user.dblClick(screen.getByRole("button", { name: "Zapisz klienta" }));
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
    held.resolve({ status: 201, body: { ...saved, contacts: [] } });

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)).toHaveLength(1);
  });

  it("edge: markup in a name or a note renders as text", async () => {
    const markupName = "<b>x</b>";
    const markupNote = "<img src=x onerror=alert(1)>";
    stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: emptyList,
      [`POST ${CUSTOMERS_URL}`]: {
        status: 201,
        body: {
          id: CUSTOMER_ID,
          name: markupName,
          country: "PL",
          contacts: [{ kind: "email", value: EMAIL, note: markupNote, primary: false }],
        },
      },
    });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    await user.type(screen.getByLabelText(/Nazwa klienta/), markupName);
    await addContact(user, { kind: "email", value: EMAIL, note: markupNote });
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));

    expect(await screen.findByRole("heading", { level: 1, name: markupName })).toBeVisible();
    expect(screen.getByText(markupNote)).toBeVisible();
    const main = screen.getByRole("main");
    expect(main.querySelector("b")).toBeNull();
    expect(main.querySelector("img")).toBeNull();
  });

  it("edge: markup in a listed name renders as text", async () => {
    stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: {
        status: 200,
        body: { items: [{ id: CUSTOMER_ID, name: "<b>x</b>", country: "PL" }] },
      },
    });
    render(<App />);
    expect(await screen.findByRole("link", { name: "<b>x</b>" })).toBeVisible();
    expect(screen.getByRole("main").querySelector("b")).toBeNull();
  });

  it("edge: the plain list shows a single customer and opens it", async () => {
    const { calls } = stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: listOfOne,
      [`GET ${CUSTOMER_URL}`]: { status: 200, body: saved },
    });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    const list = await screen.findByRole("list", { name: "Lista klientów" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.queryByText("Nie masz jeszcze klientów")).not.toBeInTheDocument();

    await user.click(within(list).getByRole("link", { name: NAME }));

    expect(await screen.findByRole("heading", { level: 1, name: NAME })).toBeVisible();
    expect(screen.getByText(STORED_PHONE)).toBeVisible();
    expect(window.location.pathname).toBe(`/klienci/${CUSTOMER_ID}`);
    expect(calls.map((call) => `${call.method} ${call.url}`)).toContain(`GET ${CUSTOMER_URL}`);
  });

  it("edge: the list shows an empty state when there are no customers", async () => {
    stubCustomerApi({ [`GET ${CUSTOMERS_URL}`]: emptyList });
    render(<App />);
    expect(await screen.findByText("Nie masz jeszcze klientów")).toBeVisible();
    expect(screen.queryByRole("list", { name: "Lista klientów" })).not.toBeInTheDocument();
  });

  it("contrast: a list that fails to load is shown as an error, not as an empty list", async () => {
    stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: { status: 500, body: { detail: "synthetic failure" } },
    });
    render(<App />);
    expect(await screen.findByText("Nie udało się wczytać listy klientów.")).toBeVisible();
    expect(screen.queryByText("Nie masz jeszcze klientów")).not.toBeInTheDocument();
  });

  it("edge: no customer field value appears in the SPA's location (ADR-0005-C13)", async () => {
    stubCustomerApi({
      [`GET ${CUSTOMERS_URL}`]: listOfOne,
      [`POST ${CUSTOMERS_URL}`]: { status: 201, body: saved },
      [`GET ${CUSTOMER_URL}`]: { status: 200, body: saved },
    });
    const values = [NAME, ENTERED_PHONE, STORED_PHONE, ENTERED_SECOND_PHONE, EMAIL, NOTE_OWNER];
    const seen: string[] = [];
    const remember = () => {
      seen.push(window.location.href);
    };
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    remember();
    await fillTheCriterionCustomer(user);
    remember();
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
    await screen.findByRole("heading", { level: 1, name: NAME });
    remember();
    await user.click(screen.getByRole("link", { name: "Wróć do listy klientów" }));
    await user.click(await screen.findByRole("link", { name: NAME }));
    await screen.findByRole("heading", { level: 1, name: NAME });
    remember();

    expect(window.location.pathname).toBe(`/klienci/${CUSTOMER_ID}`);
    for (const href of seen) {
      const decoded = decodeURIComponent(href);
      for (const value of values) {
        expect(decoded).not.toContain(value);
      }
      expect(new URL(href).search).toBe("");
      expect(new URL(href).hash).toBe("");
    }
  });
});

describe("K-07 assumptions: the customer view's other states", () => {
  it("A-03: an id that exists nowhere, or one the rep may not see, is shown as not found", async () => {
    window.history.replaceState(null, "", `/klienci/${CUSTOMER_ID}`);
    stubCustomerApi({ [`GET ${CUSTOMER_URL}`]: { status: 404, body: { detail: "not found" } } });
    render(<App />);
    expect(await screen.findByText("Nie znaleziono klienta.")).toBeVisible();
  });

  it("A-03: a path segment that is not a customer id asks the API nothing", async () => {
    window.history.replaceState(null, "", "/klienci/not-an-id");
    const { calls } = stubCustomerApi({});
    render(<App />);
    expect(await screen.findByText("Nie znaleziono klienta.")).toBeVisible();
    await waitFor(() => {
      expect(calls).toEqual([]);
    });
  });

  it("A-04: an answer of an unexpected shape is an error, never a half-rendered record", async () => {
    window.history.replaceState(null, "", `/klienci/${CUSTOMER_ID}`);
    stubCustomerApi({ [`GET ${CUSTOMER_URL}`]: { status: 200, raw: '{"id":"x","name":5}' } });
    render(<App />);
    expect(await screen.findByText("Nie udało się wczytać klienta.")).toBeVisible();
  });

  it("A-01: an empty name is refused in the form and sends nothing", async () => {
    const { calls } = stubCustomerApi({ [`GET ${CUSTOMERS_URL}`]: emptyList });
    const user = userEvent.setup({ delay: null });
    await openCreateForm(user);
    await user.type(screen.getByLabelText(/Nazwa klienta/), "   ");
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
    expect(screen.getByLabelText(/Nazwa klienta/)).toHaveAccessibleDescription(
      "Podaj nazwę klienta.",
    );
    expect(posts(calls)).toHaveLength(0);
  });
});
