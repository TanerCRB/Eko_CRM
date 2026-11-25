import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionInfo } from "../../../src/api/auth";
import type { NipTakenProblem } from "../../../src/api/customers";
import { pageNavigation } from "../../../src/api/navigation";
import { mount } from "../../../src/mount";
import {
  CUSTOMER_URL,
  form,
  openCustomer,
  openEditForm,
  requests,
  storedWith,
} from "../../support/customers-edit";
import {
  ENTERED,
  changeEveryField,
  enteredBody,
  expectEnteredValuesKept,
  foreign,
} from "../../support/customers-every-field";
import {
  CUSTOMERS_URL,
  VOIVODESHIPS_URL,
  deferred,
  inOrder,
  stubCustomerApi,
  type CustomerReply,
  type RecordedCall,
  type ReplySource,
} from "../../support/customers-http";
import { SESSION_URL } from "../../support/http";

// EKO-3-05 K-07, D-5 / D-6 X-4 A: an edit answered 409 NIP-taken is shown at the tax-ID field with
// create's messages and link, keeps every entered value, and is told apart from restore-first and
// any other 409 by the exact `detail` alone. The refusal itself is the server's (K-03).

const NIP_DETAIL = "a customer with this NIP already exists - contact your manager";
const NIP_TAKEN = "Klient z tym numerem NIP już istnieje — skontaktuj się z kierownikiem.";
const NIP_TAKEN_WITH_REFERENCE = "Klient z tym numerem NIP już istnieje.";
const OPEN_EXISTING = "Otwórz istniejącego klienta";
const SAVE_FAILED = "Nie udało się zapisać klienta. Spróbuj ponownie.";
const RESTORE_FIRST =
  "Ten klient jest zarchiwizowany. Przywróć go, aby zmienić jego dane. Wprowadzone zmiany pozostały w formularzu.";
const EXISTING_ID = "9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a";

// The edited customer is active here: the NIP check is reached only on an active row (K-03).
const edited = { ...foreign, archived: false };
const repBody: NipTakenProblem = { detail: NIP_DETAIL };
const managerBody: NipTakenProblem = { detail: NIP_DETAIL, existing_customer_id: EXISTING_ID };
const nipTaken: CustomerReply = { status: 409, body: repBody };
const nipTakenWithReference: CustomerReply = { status: 409, body: managerBody };
const existingArchived = storedWith({
  id: EXISTING_ID,
  name: "Gospodarstwo Wcześniejsze",
  archived: true,
});

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

let unmount: (() => void) | undefined;

afterEach(() => {
  act(() => unmount?.());
  unmount = undefined;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

const puts = (calls: readonly RecordedCall[]) => requests(calls, "PUT", CUSTOMER_URL);

function taxIdField() {
  return form.nip();
}

function openExistingLink() {
  return screen.queryByRole("link", { name: OPEN_EXISTING });
}

function restoreButton() {
  return screen.queryByRole("button", { name: "Przywróć klienta" });
}

function formAlerts() {
  return document.querySelectorAll(".form-alert");
}

function invalidFields() {
  return Array.from(document.querySelectorAll('[aria-invalid="true"]'));
}

async function refusedEdit(put: ReplySource, routes: Record<string, ReplySource> = {}) {
  const user = userEvent.setup({ delay: null });
  const { calls } = await openCustomer(edited, { [`PUT ${CUSTOMER_URL}`]: put, ...routes });
  await openEditForm(user);
  await changeEveryField(user);
  await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));
  return { calls, user };
}

function expectOnlyTheTaxIdMarked(message: string) {
  expect(taxIdField()).toHaveAccessibleDescription(message);
  expect(invalidFields()).toEqual([taxIdField()]);
  expect(formAlerts()).toHaveLength(0);
  expect(screen.queryByText(SAVE_FAILED)).not.toBeInTheDocument();
  expect(restoreButton()).toBeNull();
}

function expectGenericFailure() {
  expect(screen.getByText(SAVE_FAILED)).toBeVisible();
  expect(invalidFields()).toEqual([]);
  expect(screen.queryByText(NIP_TAKEN)).not.toBeInTheDocument();
  expect(screen.queryByText(NIP_TAKEN_WITH_REFERENCE)).not.toBeInTheDocument();
  expect(openExistingLink()).toBeNull();
  expect(restoreButton()).toBeNull();
}

describe("K-07 D-6 X-4 A: an edit refused for a taken NIP is shown at the tax-ID field", () => {
  it("marks only the tax-ID field with nipTaken, offers no link or restore, and keeps every value", async () => {
    const { calls } = await refusedEdit(nipTaken);

    expect(await screen.findByText(NIP_TAKEN)).toBeVisible();
    expectOnlyTheTaxIdMarked(NIP_TAKEN);
    expect(openExistingLink()).toBeNull();
    expectEnteredValuesKept();
    expect(puts(calls)).toHaveLength(1);
    expect(puts(calls)[0]?.body).toEqual(enteredBody);
    expect(requests(calls, "GET", CUSTOMER_URL)).toHaveLength(1);
  });

  it("with a reference shows nipTakenWithReference and a link to that customer", async () => {
    await refusedEdit(nipTakenWithReference);

    expect(await screen.findByText(NIP_TAKEN_WITH_REFERENCE)).toBeVisible();
    expectOnlyTheTaxIdMarked(NIP_TAKEN_WITH_REFERENCE);
    expect(openExistingLink()).toHaveAttribute("href", `/klienci/${EXISTING_ID}`);
    expectEnteredValuesKept();
  });

  it("following the link opens the existing customer, also when it is archived, and offers restore", async () => {
    const { user } = await refusedEdit(nipTakenWithReference, {
      [`GET ${CUSTOMERS_URL}/${EXISTING_ID}`]: { status: 200, body: existingArchived },
    });
    const link = await screen.findByRole("link", { name: OPEN_EXISTING });

    await user.click(link);

    expect(
      await screen.findByRole("heading", { level: 1, name: existingArchived.name }),
    ).toBeVisible();
    expect(screen.getByText("Klient zarchiwizowany")).toBeVisible();
    expect(restoreButton()).toBeVisible();
    const location = new URL(window.location.href);
    expect(location.pathname).toBe(`/klienci/${EXISTING_ID}`);
    expect(location.search).toBe("");
    expect(location.hash).toBe("");
    for (const value of [ENTERED.name, ENTERED.street, ENTERED.town, ENTERED.firstValue]) {
      expect(decodeURIComponent(window.location.href)).not.toContain(value);
    }
  });

  it("a further save sends exactly one PUT whose body equals the refused one", async () => {
    const { calls, user } = await refusedEdit(
      inOrder(nipTaken, { status: 200, body: storedWith({ name: ENTERED.name }) }),
    );
    await screen.findByText(NIP_TAKEN);

    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));

    await screen.findByRole("heading", { level: 1, name: ENTERED.name });
    expect(puts(calls)).toHaveLength(2);
    expect(puts(calls)[1]?.body).toEqual(puts(calls)[0]?.body);
  });

  it("edge: a double click on save answered NIP-taken sends one PUT", async () => {
    const held = deferred<CustomerReply>();
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(edited, { [`PUT ${CUSTOMER_URL}`]: () => held.promise });
    await openEditForm(user);
    await changeEveryField(user);

    await user.dblClick(screen.getByRole("button", { name: "Zapisz zmiany" }));
    held.resolve(nipTaken);

    await screen.findByText(NIP_TAKEN);
    expect(puts(calls)).toHaveLength(1);
  });

  it("contrast: the same edit answered restore-first marks no field and offers restore", async () => {
    await refusedEdit({ status: 409, body: { detail: "restore it first" } });

    expect(await screen.findByText(RESTORE_FIRST)).toBeVisible();
    expect(invalidFields()).toEqual([]);
    expect(screen.queryByText(NIP_TAKEN)).not.toBeInTheDocument();
    expect(restoreButton()).toBeVisible();
  });

  const notNipTaken: [string, CustomerReply][] = [
    ["conflict", { status: 409, body: { detail: "conflict" } }],
    ["upper case", { status: 409, body: { detail: NIP_DETAIL.replace("a customer", "A customer") } }],
    ["trailing space", { status: 409, body: { detail: `${NIP_DETAIL} ` } }],
    ["missing", { status: 409, raw: "{}" }],
  ];
  for (const [label, reply] of notNipTaken) {
    it(`edge: a 409 whose detail is ${label} is the generic failure and keeps every value`, async () => {
      await refusedEdit(reply);

      await screen.findByText(SAVE_FAILED);
      expectGenericFailure();
      expectEnteredValuesKept();
    });
  }

  const badReferences: [string, string][] = [
    ["null", "null"],
    ["a number", "7"],
    ["not a UUID", '"not-a-customer"'],
    ["a UUID followed by a path", `"${EXISTING_ID}/archive"`],
  ];
  for (const [label, reference] of badReferences) {
    it(`edge: a reference that is ${label} gives nipTaken and no link`, async () => {
      await refusedEdit({
        status: 409,
        raw: `{"detail":${JSON.stringify(NIP_DETAIL)},"existing_customer_id":${reference}}`,
      });

      expect(await screen.findByText(NIP_TAKEN)).toBeVisible();
      expect(openExistingLink()).toBeNull();
      expectEnteredValuesKept();
    });
  }

  const otherFailures: [string, CustomerReply, string][] = [
    ["404", { status: 404, body: { detail: "not found" } }, "Nie znaleziono klienta."],
    ["503", { status: 503, body: { detail: "temporarily unavailable" } }, SAVE_FAILED],
  ];
  for (const [label, reply, shown] of otherFailures) {
    it(`edge: a ${label} on the edit PUT never shows the NIP-taken message`, async () => {
      await refusedEdit(reply);

      expect(await screen.findByText(shown)).toBeVisible();
      expect(screen.queryByText(NIP_TAKEN)).not.toBeInTheDocument();
      expect(screen.queryByText(NIP_TAKEN_WITH_REFERENCE)).not.toBeInTheDocument();
      expect(openExistingLink()).toBeNull();
      expect(taxIdField()).not.toHaveAttribute("aria-invalid");
    });
  }
});

describe("K-07 M-z8: the link comes from the answer, never from the session's roles", () => {
  function session(roles: SessionInfo["roles"]): CustomerReply {
    const info: SessionInfo = { subject: "synthetic-staff-0305", name: "Ewa Testowa", roles };
    return { status: 200, raw: JSON.stringify(info) };
  }

  async function mountedRefusal(roles: SessionInfo["roles"], put: CustomerReply) {
    window.history.replaceState(null, "", `/klienci/${edited.id}`);
    stubCustomerApi({
      [`GET ${SESSION_URL}`]: session(roles),
      [`GET ${CUSTOMER_URL}`]: { status: 200, body: edited },
      [`GET ${VOIVODESHIPS_URL}`]: { status: 200, body: { as_of: "2026-01-01", voivodeships: [] } },
      [`PUT ${CUSTOMER_URL}`]: put,
    });
    document.body.innerHTML = '<div id="root"></div>';
    act(() => {
      unmount = mount(document);
    });
    const user = userEvent.setup({ delay: null });
    await screen.findByRole("heading", { level: 1, name: edited.name });
    await user.click(screen.getByRole("button", { name: "Edytuj dane" }));
    await screen.findByRole("heading", { level: 1, name: "Edytuj klienta" });
    await user.click(screen.getByRole("button", { name: "Zapisz zmiany" }));
  }

  it("a manager's session with an answer carrying no reference shows no link", async () => {
    await mountedRefusal(["rep", "manager"], nipTaken);

    expect(await screen.findByText(NIP_TAKEN)).toBeVisible();
    expect(openExistingLink()).toBeNull();
  });

  it("contrast: a rep's session with an answer carrying a reference shows the link", async () => {
    await mountedRefusal(["rep"], nipTakenWithReference);

    expect(await screen.findByText(NIP_TAKEN_WITH_REFERENCE)).toBeVisible();
    expect(
      within(screen.getByRole("form", { name: "Edytuj klienta" })).getByRole("link", {
        name: OPEN_EXISTING,
      }),
    ).toHaveAttribute("href", `/klienci/${EXISTING_ID}`);
  });
});
