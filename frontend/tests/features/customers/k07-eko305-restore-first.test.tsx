import { screen, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { pageNavigation } from "../../../src/api/navigation";
import {
  CUSTOMER_URL,
  OTHER_NIP,
  RESTORE_URL,
  contact,
  contactGroup,
  form,
  openCustomer,
  openEditForm,
  replace,
  requests,
  storedWith,
} from "../../support/customers-edit";
import {
  deferred,
  inOrder,
  type CustomerReply,
  type RecordedCall,
  type ReplySource,
} from "../../support/customers-http";

// EKO-3-05 K-07, D-3 F-1 A: an edit answered 409 {"detail":"restore it first"} keeps the form and
// every entered value, says the customer must be restored first and offers restore; a later save
// resends the same body. The refusal itself is the server's (K-04); only its display is here.

const RESTORE_FIRST =
  "Ten klient jest zarchiwizowany. Przywróć go, aby zmienić jego dane. Wprowadzone zmiany pozostały w formularzu.";
const SAVE_FAILED = "Nie udało się zapisać klienta. Spróbuj ponownie.";
const RESTORED = "Klient przywrócony. Zapisz zmiany ponownie, aby je zachować.";
const RESTORE_FAILED = "Nie udało się przywrócić klienta. Spróbuj ponownie.";

// A foreign customer, so changing every field includes the country and the region parts.
const foreign = storedWith({
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

const ENTERED = {
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
const enteredBody = {
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

const restoreFirst: CustomerReply = { status: 409, body: { detail: "restore it first" } };
const restoredAnswer: CustomerReply = { status: 200, body: { ...foreign, archived: false } };
const savedAnswer = storedWith({
  name: "Gospodarstwo Zażółć",
  tax_id: OTHER_NIP,
  archived: false,
});

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

async function changeEveryField(user: UserEvent) {
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

function expectEnteredValuesKept() {
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

function formAlert() {
  return within(screen.getByRole("form", { name: "Edytuj klienta" }))
    .getAllByRole("alert")
    .find((element) => element.classList.contains("form-alert"));
}

function restoreButton() {
  return screen.queryByRole("button", { name: "Przywróć klienta" });
}

async function refusedEdit(put: ReplySource, routes: Record<string, ReplySource> = {}) {
  const user = userEvent.setup({ delay: null });
  const { calls } = await openCustomer(foreign, { [`PUT ${CUSTOMER_URL}`]: put, ...routes });
  await openEditForm(user);
  await changeEveryField(user);
  await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));
  return { calls, user };
}

const puts = (calls: readonly RecordedCall[]) => requests(calls, "PUT", CUSTOMER_URL);
const restores = (calls: readonly RecordedCall[]) => requests(calls, "POST", RESTORE_URL);

describe("K-07 D-3 F-1 A: an edit refused with restore-it-first keeps the form and offers restore", () => {
  it("shows the dedicated restore-first message, marks no field, and keeps every value", async () => {
    const { calls } = await refusedEdit(restoreFirst);

    expect(await screen.findByText(RESTORE_FIRST)).toBeVisible();
    expect(formAlert()).toHaveTextContent(RESTORE_FIRST);
    expect(screen.queryByText(SAVE_FAILED)).not.toBeInTheDocument();
    expect(document.querySelectorAll('[aria-invalid="true"]')).toHaveLength(0);
    expectEnteredValuesKept();
    expect(puts(calls)).toHaveLength(1);
    expect(puts(calls)[0]?.body).toEqual(enteredBody);
    // Nothing is re-read: the one read by id is the screen's own, before the edit.
    expect(requests(calls, "GET", CUSTOMER_URL)).toHaveLength(1);
    expect(window.location.pathname).toBe(`/klienci/${foreign.id}`);
  });

  it("the offered restore sends exactly one POST …/restore with no body, and nothing else", async () => {
    const { calls, user } = await refusedEdit(restoreFirst, {
      [`POST ${RESTORE_URL}`]: restoredAnswer,
    });
    await screen.findByText(RESTORE_FIRST);
    const before = calls.length;

    const restore = restoreButton();
    expect(restore).not.toBeNull();
    await user.click(restore as HTMLElement);

    expect(await screen.findByText(RESTORED)).toBeVisible();
    const sent = calls.slice(before);
    expect(sent).toEqual([{ method: "POST", url: RESTORE_URL, body: undefined }]);
    expectEnteredValuesKept();
  });

  it("restore then resave: one further save sends one PUT whose body equals the refused one", async () => {
    const { calls, user } = await refusedEdit(
      inOrder(restoreFirst, { status: 200, body: savedAnswer }),
      { [`POST ${RESTORE_URL}`]: restoredAnswer },
    );
    await screen.findByText(RESTORE_FIRST);
    await user.click(restoreButton() as HTMLElement);
    await screen.findByText(RESTORED);
    expect(puts(calls)).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

    expect(await screen.findByRole("heading", { level: 1, name: savedAnswer.name })).toBeVisible();
    expect(puts(calls)).toHaveLength(2);
    expect(puts(calls)[1]?.body).toEqual(puts(calls)[0]?.body);
    expect(puts(calls)[1]?.body).toEqual(enteredBody);
    expect(restores(calls)).toHaveLength(1);
    // The view shows the server's answer, not the entered values.
    expect(screen.getByText("Polna 7")).toBeVisible();
    expect(screen.queryByText(ENTERED.street)).not.toBeInTheDocument();
  });

  it("edge: a double click on the offered restore sends one POST …/restore", async () => {
    const held = deferred<CustomerReply>();
    const { calls, user } = await refusedEdit(restoreFirst, {
      [`POST ${RESTORE_URL}`]: () => held.promise,
    });
    await screen.findByText(RESTORE_FIRST);

    await user.dblClick(restoreButton() as HTMLElement);
    held.resolve(restoredAnswer);

    await screen.findByText(RESTORED);
    expect(restores(calls)).toHaveLength(1);
    expect(puts(calls)).toHaveLength(1);
  });

  it("contrast: 409 {\"detail\":\"conflict\"} shows the generic failure, offers no restore, keeps values", async () => {
    await refusedEdit({ status: 409, body: { detail: "conflict" } });

    expect(await screen.findByText(SAVE_FAILED)).toBeVisible();
    expect(screen.queryByText(RESTORE_FIRST)).not.toBeInTheDocument();
    expect(restoreButton()).toBeNull();
    expectEnteredValuesKept();
  });

  const notRestoreFirst: [string, CustomerReply][] = [
    ['"Restore it first"', { status: 409, body: { detail: "Restore it first" } }],
    ['" restore it first"', { status: 409, body: { detail: " restore it first" } }],
    ['""', { status: 409, body: { detail: "" } }],
    ["missing", { status: 409, raw: "{}" }],
    ["not JSON", { status: 409, raw: "restore it first" }],
  ];
  for (const [label, reply] of notRestoreFirst) {
    it(`edge: a 409 whose detail is ${label} is not restore-first`, async () => {
      await refusedEdit(reply);

      expect(await screen.findByText(SAVE_FAILED)).toBeVisible();
      expect(screen.queryByText(RESTORE_FIRST)).not.toBeInTheDocument();
      expect(restoreButton()).toBeNull();
      expectEnteredValuesKept();
    });
  }

  it("edge: a 404 on the edit PUT never shows the restore-first message", async () => {
    await refusedEdit({ status: 404, body: { detail: "not found" } });

    expect(await screen.findByText("Nie znaleziono klienta.")).toBeVisible();
    expect(screen.queryByText(RESTORE_FIRST)).not.toBeInTheDocument();
    expect(restoreButton()).toBeNull();
    expectEnteredValuesKept();
  });

  it("edge: a 503 on the edit PUT never shows the restore-first message", async () => {
    await refusedEdit({ status: 503, body: { detail: "temporarily unavailable" } });

    expect(await screen.findByText(SAVE_FAILED)).toBeVisible();
    expect(screen.queryByText(RESTORE_FIRST)).not.toBeInTheDocument();
    expect(restoreButton()).toBeNull();
    expectEnteredValuesKept();
  });

  const failedRestores: [string, CustomerReply][] = [
    ["404", { status: 404, body: { detail: "not found" } }],
    ["503", { status: 503, body: { detail: "temporarily unavailable" } }],
  ];
  for (const [label, reply] of failedRestores) {
    it(`edge: a restore answered ${label} keeps every value, sends no PUT and shows the failure`, async () => {
      const { calls, user } = await refusedEdit(restoreFirst, { [`POST ${RESTORE_URL}`]: reply });
      await screen.findByText(RESTORE_FIRST);
      const before = calls.length;

      await user.click(restoreButton() as HTMLElement);

      expect(await screen.findByText(RESTORE_FAILED)).toBeVisible();
      expect(screen.queryByText(RESTORED)).not.toBeInTheDocument();
      expect(calls.slice(before)).toEqual([{ method: "POST", url: RESTORE_URL, body: undefined }]);
      expectEnteredValuesKept();
    });
  }

  it("edge: a restore answered 200 that still says archived is not shown as success", async () => {
    const { user } = await refusedEdit(restoreFirst, {
      [`POST ${RESTORE_URL}`]: { status: 200, body: foreign },
    });
    await screen.findByText(RESTORE_FIRST);

    await user.click(restoreButton() as HTMLElement);

    expect(await screen.findByText(RESTORE_FAILED)).toBeVisible();
    expect(screen.queryByText(RESTORED)).not.toBeInTheDocument();
    expectEnteredValuesKept();
  });

  it("floor (G-1 A): the restore-first and restore texts name no visits and no actions", async () => {
    const { user } = await refusedEdit(restoreFirst, { [`POST ${RESTORE_URL}`]: restoredAnswer });
    const shown: string[] = [];
    shown.push((await screen.findByText(RESTORE_FIRST)).textContent);
    await user.click(restoreButton() as HTMLElement);
    shown.push((await screen.findByText(RESTORED)).textContent);

    for (const text of shown) {
      expect(text.toLowerCase()).not.toMatch(/wizyt|zada/);
    }
  });
});
