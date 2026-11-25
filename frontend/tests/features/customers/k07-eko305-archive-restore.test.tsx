import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import {
  ARCHIVE_URL,
  CUSTOMER_ID,
  RESTORE_URL,
  openCustomer,
  requests,
  stored,
  storedWith,
  writes,
} from "../../support/customers-edit";
import {
  CUSTOMERS_URL,
  deferred,
  stubCustomerApi,
  type CustomerReply,
  type OlderCustomerRecord,
} from "../../support/customers-http";

// EKO-3-05 K-07, archive and restore: archiving asks first and sends nothing until confirmed;
// what the screen shows as archived comes from each answer's `archived`, never from the request.

const ARCHIVE_TITLE = "Zarchiwizować tego klienta?";
const ARCHIVE_CONSEQUENCE =
  "Klient zniknie z listy aktywnych klientów. Jego dane pozostaną zapisane i możesz go później przywrócić.";
const ARCHIVED_NOTICE = "Klient zarchiwizowany. Możesz go przywrócić.";
const RESTORED_NOTICE = "Klient przywrócony. Jest znowu na liście aktywnych klientów.";
const ACTIVE_STATE = "Klient aktywny";
const ARCHIVED_STATE = "Klient zarchiwizowany";

const archived = storedWith({ archived: true });

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

function archiveAction() {
  return screen.queryByRole("button", { name: "Archiwizuj klienta" });
}

function restoreAction() {
  return screen.queryByRole("button", { name: "Przywróć klienta" });
}

describe("K-07 archive: nothing is sent until the user confirms", () => {
  it("opening the confirmation sends nothing; confirming sends exactly one POST …/archive", async () => {
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, {
      [`POST ${ARCHIVE_URL}`]: { status: 200, body: archived },
    });
    expect(screen.getByText(ACTIVE_STATE)).toBeVisible();

    await user.click(archiveAction() as HTMLElement);

    const dialog = await screen.findByRole("dialog", { name: ARCHIVE_TITLE });
    expect(writes(calls)).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Archiwizuj klienta" }));

    expect(await screen.findByText(ARCHIVED_NOTICE)).toBeVisible();
    expect(writes(calls)).toEqual([{ method: "POST", url: ARCHIVE_URL, body: undefined }]);
    expect(screen.getByText(ARCHIVED_STATE)).toBeVisible();
    expect(restoreAction()).toBeVisible();
    expect(archiveAction()).toBeNull();
  });

  it("contrast: cancelling the same confirmation sends nothing and the customer stays active", async () => {
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, {
      [`POST ${ARCHIVE_URL}`]: { status: 200, body: archived },
    });

    await user.click(archiveAction() as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: ARCHIVE_TITLE });
    await user.click(within(dialog).getByRole("button", { name: "Wróć" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(writes(calls)).toEqual([]);
    expect(screen.getByText(ACTIVE_STATE)).toBeVisible();
    expect(archiveAction()).toBeVisible();
  });

  it("the confirmation says the customer leaves the active list and can be restored", async () => {
    const user = userEvent.setup({ delay: null });
    await openCustomer(stored);

    await user.click(archiveAction() as HTMLElement);

    const dialog = await screen.findByRole("dialog", { name: ARCHIVE_TITLE });
    expect(dialog).toHaveAccessibleDescription(ARCHIVE_CONSEQUENCE);
  });

  it("edge: a double click on confirm sends one POST …/archive", async () => {
    const held = deferred<CustomerReply>();
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, { [`POST ${ARCHIVE_URL}`]: () => held.promise });

    await user.click(archiveAction() as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: ARCHIVE_TITLE });
    await user.dblClick(within(dialog).getByRole("button", { name: "Archiwizuj klienta" }));
    const again = archiveAction();
    if (again !== null && !(again as HTMLButtonElement).disabled) {
      await user.click(again);
    }
    held.resolve({ status: 200, body: archived });

    await screen.findByText(ARCHIVED_NOTICE);
    expect(requests(calls, "POST", ARCHIVE_URL)).toHaveLength(1);
  });

  it("edge: a failed archive is shown as a failure and the customer stays active", async () => {
    const user = userEvent.setup({ delay: null });
    await openCustomer(stored, {
      [`POST ${ARCHIVE_URL}`]: { status: 503, body: { detail: "temporarily unavailable" } },
    });

    await user.click(archiveAction() as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: ARCHIVE_TITLE });
    await user.click(within(dialog).getByRole("button", { name: "Archiwizuj klienta" }));

    expect(
      await screen.findByText("Nie udało się zarchiwizować klienta. Spróbuj ponownie."),
    ).toBeVisible();
    expect(screen.queryByText(ARCHIVED_NOTICE)).not.toBeInTheDocument();
    expect(screen.getByText(ACTIVE_STATE)).toBeVisible();
  });
});

describe("K-07 restore: an answer with archived: true offers restore", () => {
  it("an archived customer offers restore, which sends one POST …/restore with no body", async () => {
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(archived, {
      [`POST ${RESTORE_URL}`]: { status: 200, body: stored },
    });
    expect(screen.getByText(ARCHIVED_STATE)).toBeVisible();
    expect(archiveAction()).toBeNull();

    await user.click(restoreAction() as HTMLElement);

    expect(await screen.findByText(RESTORED_NOTICE)).toBeVisible();
    expect(writes(calls)).toEqual([{ method: "POST", url: RESTORE_URL, body: undefined }]);
    expect(screen.getByText(ACTIVE_STATE)).toBeVisible();
    expect(archiveAction()).toBeVisible();
    expect(restoreAction()).toBeNull();
  });

  it("contrast: the same customer with archived: false offers no restore", async () => {
    await openCustomer(stored);

    expect(restoreAction()).toBeNull();
    expect(screen.queryByText(ARCHIVED_STATE)).not.toBeInTheDocument();
    expect(archiveAction()).toBeVisible();
  });

  it("edge: an answer without archived, from an older backend, is not shown as archived", async () => {
    const olderRecord: OlderCustomerRecord = {
      id: stored.id,
      name: stored.name,
      country: stored.country,
      street: stored.street,
      postal_code: stored.postal_code,
      town: stored.town,
      voivodeship: stored.voivodeship,
      county: stored.county,
      tax_id: stored.tax_id,
      contacts: stored.contacts,
    };
    window.history.replaceState(null, "", `/klienci/${CUSTOMER_ID}`);
    stubCustomerApi({ [`GET ${CUSTOMERS_URL}/${CUSTOMER_ID}`]: { status: 200, older: olderRecord } });
    render(<App />);

    await screen.findByRole("heading", { level: 1, name: stored.name });
    expect(screen.queryByText(ARCHIVED_STATE)).not.toBeInTheDocument();
    expect(screen.getByText(ACTIVE_STATE)).toBeVisible();
    expect(restoreAction()).toBeNull();
  });

  it("edge: a double click on restore sends one POST …/restore", async () => {
    const held = deferred<CustomerReply>();
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(archived, { [`POST ${RESTORE_URL}`]: () => held.promise });

    await user.dblClick(restoreAction() as HTMLElement);
    held.resolve({ status: 200, body: stored });

    await screen.findByText(RESTORED_NOTICE);
    expect(requests(calls, "POST", RESTORE_URL)).toHaveLength(1);
  });

  it("edge: a failed restore is shown as a failure and the customer stays archived", async () => {
    const user = userEvent.setup({ delay: null });
    await openCustomer(archived, {
      [`POST ${RESTORE_URL}`]: { status: 404, body: { detail: "not found" } },
    });

    await user.click(restoreAction() as HTMLElement);

    expect(await screen.findByText("Nie udało się przywrócić klienta. Spróbuj ponownie.")).toBeVisible();
    expect(screen.queryByText(RESTORED_NOTICE)).not.toBeInTheDocument();
    expect(screen.getByText(ARCHIVED_STATE)).toBeVisible();
  });
});

describe("K-07 floor (G-1 A): the archive and restore texts name no visits and no actions", () => {
  it("the confirmation and both notices contain neither 'wizyt' nor 'zada'", async () => {
    const user = userEvent.setup({ delay: null });
    const { calls } = await openCustomer(stored, {
      [`POST ${ARCHIVE_URL}`]: { status: 200, body: archived },
      [`POST ${RESTORE_URL}`]: { status: 200, body: stored },
    });
    const shown: string[] = [];

    await user.click(archiveAction() as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: ARCHIVE_TITLE });
    shown.push(dialog.textContent);
    await user.click(within(dialog).getByRole("button", { name: "Archiwizuj klienta" }));
    shown.push((await screen.findByText(ARCHIVED_NOTICE)).textContent);
    await user.click(restoreAction() as HTMLElement);
    shown.push((await screen.findByText(RESTORED_NOTICE)).textContent);

    expect(writes(calls)).toHaveLength(2);
    for (const text of shown) {
      expect(text).not.toBe("");
      expect(text.toLowerCase()).not.toMatch(/wizyt|zada/);
    }
  });
});
