import { render, screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { createElement } from "react";
import { App } from "../../src/App";
import type { CustomerRecord } from "../../src/api/customers";
import type { VoivodeshipList } from "../../src/api/reference";
import {
  CUSTOMERS_URL,
  stubCustomerApi,
  VOIVODESHIPS_URL,
  type RecordedCall,
  type ReplySource,
} from "./customers-http";

// EKO-3-05 K-07: one stored customer and the screen helpers its edit, archive and restore tests
// share. Synthetic values only (ADR-0005); the NIPs are assembled at run time, so no NIP-shaped
// literal sits in the source, and phone numbers carry no separators.
export const CUSTOMER_ID = "4e5f6a7b-8c9d-4e0f-a1b2-c3d4e5f6a7b8";
export const CUSTOMER_URL = `${CUSTOMERS_URL}/${CUSTOMER_ID}`;
export const ARCHIVE_URL = `${CUSTOMER_URL}/archive`;
export const RESTORE_URL = `${CUSTOMER_URL}/restore`;
export const STORED_NIP = "0".repeat(3) + "5550101";
export const OTHER_NIP = "0".repeat(3) + "5550202";

export const register: VoivodeshipList = {
  as_of: "2026-01-01",
  voivodeships: [
    { name: "mazowieckie", counties: ["warszawski zachodni", "Warszawa"] },
    { name: "podlaskie", counties: ["bielski", "hajnowski"] },
  ],
};

export const stored: CustomerRecord = {
  id: CUSTOMER_ID,
  name: "Gospodarstwo Źródlane",
  country: "PL",
  street: "Polna 7",
  postal_code: "05-850",
  town: "Ożarów",
  voivodeship: "mazowieckie",
  county: "warszawski zachodni",
  tax_id: STORED_NIP,
  contacts: [
    { kind: "phone", value: "+48601305101", note: "Właściciel", primary: true },
    { kind: "email", value: "zrodlane@example.invalid", note: "Biuro", primary: false },
  ],
  archived: false,
};

export function storedWith(overrides: Partial<CustomerRecord>): CustomerRecord {
  return { ...stored, ...overrides };
}

// The customer's own screen, read by id, with the register the edit form loads.
export async function openCustomer(
  record: CustomerRecord,
  routes: Record<string, ReplySource> = {},
) {
  window.history.replaceState(null, "", `/klienci/${record.id}`);
  const stub = stubCustomerApi({
    [`GET ${CUSTOMERS_URL}/${record.id}`]: { status: 200, body: record },
    [`GET ${VOIVODESHIPS_URL}`]: { status: 200, body: register },
    ...routes,
  });
  render(createElement(App));
  await screen.findByRole("heading", { level: 1, name: record.name });
  return stub;
}

export async function openEditForm(user: UserEvent) {
  await user.click(screen.getByRole("button", { name: "Edytuj dane" }));
  await screen.findByRole("heading", { level: 1, name: "Edytuj klienta" });
  // The region selects hold the stored values only once their options are there.
  if (screen.queryByLabelText(/^Województwo/) !== null) {
    await within(screen.getByLabelText(/^Województwo/)).findByRole("option", {
      name: "mazowieckie",
    });
  }
}

// Each field by its label; a field showing an error continues its label with the message.
export const form = {
  name: () => screen.getByLabelText(/^Nazwa klienta/),
  country: () => screen.getByLabelText(/^Kraj/),
  nip: () => screen.getByLabelText(/^NIP/),
  foreignTaxId: () => screen.getByLabelText(/^Numer podatkowy/),
  street: () => screen.getByLabelText(/^Ulica i numer/),
  postalCode: () => screen.getByLabelText(/^Kod pocztowy/),
  town: () => screen.getByLabelText(/^Miejscowość/),
  voivodeship: () => screen.getByLabelText(/^Województwo/),
  county: () => screen.getByLabelText(/^Powiat/),
};

export function contactGroups() {
  return screen.queryAllByRole("group", { name: /^Kontakt \d+$/ });
}

export function contactGroup(position: number): HTMLElement {
  const group = contactGroups()[position];
  if (group === undefined) {
    throw new Error(`no contact row ${String(position + 1)}`);
  }
  return group;
}

export const contact = {
  kind: (group: HTMLElement) => within(group).getByLabelText(/^Rodzaj kontaktu/),
  value: (group: HTMLElement) => within(group).getByLabelText(/^Numer telefonu lub adres e-mail/),
  note: (group: HTMLElement) => within(group).getByLabelText(/^Opis kontaktu/),
  primary: (group: HTMLElement) => within(group).getByRole("radio", { name: "Kontakt główny" }),
};

// Replaces a field's whole value the way a user does: select it all, then type over it.
export async function replace(user: UserEvent, field: HTMLElement, value: string) {
  await user.clear(field);
  if (value !== "") {
    await user.click(field);
    await user.paste(value);
  }
}

export function requests(calls: readonly RecordedCall[], method: string, url: string) {
  return calls.filter((call) => call.method === method && call.url === url);
}

// Every request other than the screen's reads: the customer by id and the register.
export function writes(calls: readonly RecordedCall[]) {
  return calls.filter((call) => call.method !== "GET");
}
