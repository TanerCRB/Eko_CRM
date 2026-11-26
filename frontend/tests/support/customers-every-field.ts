import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { expect } from "vitest";
import {
  OTHER_NIP,
  contact,
  contactGroup,
  form,
  replace,
  storedWith,
} from "./customers-edit";

// EKO-3-05 K-07: an edit that changes every field and contact of a stored foreign customer, shared
// by the two 409 cases (restore-first and NIP-taken), which both must keep every entered value.

// A foreign customer, so changing every field includes the country and the region parts.
export const foreign = storedWith({
  name: "Hof Beispiel",
  country: "DE",
  street: "Hauptstraße 1",
  postal_code: "10115",
  town: "Berlin",
  voivodeship: null,
  county: null,
  tax_id: "DE-Steuer 42/7",
  contacts: [
    { kind: "phone", value: "+49301234567", note: "Büro", primary: true },
    { kind: "email", value: "hof@example.invalid", note: "Rechnungen", primary: false },
  ],
  archived: true,
});

export const ENTERED = {
  name: "Gospodarstwo Zażółć",
  street: "Łąkowa 2",
  postalCode: "15-001",
  town: "Białystok",
  voivodeship: "podlaskie",
  county: "bielski",
  firstValue: "zazolc@example.invalid",
  firstNote: "Księgowość",
  secondValue: "601305202",
};

// The body every save of the entered values sends: the cleared note goes as null.
export const enteredBody = {
  name: ENTERED.name,
  country: "PL",
  street: ENTERED.street,
  postal_code: ENTERED.postalCode,
  town: ENTERED.town,
  voivodeship: ENTERED.voivodeship,
  county: ENTERED.county,
  tax_id: OTHER_NIP,
  contacts: [
    { kind: "email", value: ENTERED.firstValue, note: ENTERED.firstNote, primary: false },
    { kind: "phone", value: ENTERED.secondValue, note: null, primary: true },
  ],
};

export async function changeEveryField(user: UserEvent) {
  await replace(user, form.name(), ENTERED.name);
  await user.selectOptions(form.country(), "PL");
  await within(form.voivodeship()).findByRole("option", { name: ENTERED.voivodeship });
  await replace(user, form.nip(), OTHER_NIP);
  await replace(user, form.street(), ENTERED.street);
  await replace(user, form.postalCode(), ENTERED.postalCode);
  await replace(user, form.town(), ENTERED.town);
  await user.selectOptions(form.voivodeship(), ENTERED.voivodeship);
  await user.selectOptions(form.county(), ENTERED.county);
  const first = contactGroup(0);
  await user.selectOptions(contact.kind(first), "email");
  await replace(user, contact.value(first), ENTERED.firstValue);
  await replace(user, contact.note(first), ENTERED.firstNote);
  const second = contactGroup(1);
  await user.selectOptions(contact.kind(second), "phone");
  await replace(user, contact.value(second), ENTERED.secondValue);
  await replace(user, contact.note(second), "");
  await user.click(contact.primary(second));
}

export function expectEnteredValuesKept() {
  expect(screen.getByRole("heading", { level: 1, name: "Edytuj klienta" })).toBeVisible();
  expect(form.name()).toHaveValue(ENTERED.name);
  expect(form.country()).toHaveValue("PL");
  expect(form.nip()).toHaveValue(OTHER_NIP);
  expect(form.street()).toHaveValue(ENTERED.street);
  expect(form.postalCode()).toHaveValue(ENTERED.postalCode);
  expect(form.town()).toHaveValue(ENTERED.town);
  expect(form.voivodeship()).toHaveValue(ENTERED.voivodeship);
  expect(form.county()).toHaveValue(ENTERED.county);
  const first = contactGroup(0);
  expect(contact.kind(first)).toHaveValue("email");
  expect(contact.value(first)).toHaveValue(ENTERED.firstValue);
  expect(contact.note(first)).toHaveValue(ENTERED.firstNote);
  expect(contact.primary(first)).not.toBeChecked();
  const second = contactGroup(1);
  expect(contact.kind(second)).toHaveValue("phone");
  expect(contact.value(second)).toHaveValue(ENTERED.secondValue);
  expect(contact.note(second)).toHaveValue("");
  expect(contact.primary(second)).toBeChecked();
}
