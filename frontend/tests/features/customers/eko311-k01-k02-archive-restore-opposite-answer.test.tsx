import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { CustomerRecord } from "../../../src/api/customers";
import { pageNavigation } from "../../../src/api/navigation";
import {
  ARCHIVE_URL,
  RESTORE_URL,
  openCustomer,
  requests,
  stored,
  storedWith,
} from "../../support/customers-edit";

// EKO-3-11 K-01/K-02 (EKO-3-05 frontend A-07): a 200 answer to an archive or restore counts as
// success only when its `archived` is the state asked for; the opposite answer is the action's
// failure and the screen keeps what it showed. Per G-4 A each answer also carries another name,
// so a screen that adopted the answer would show it in the heading. Names are invented.

const ANSWERED_NAME = "Gospodarstwo Odmienne";
const ARCHIVE_TITLE = "Zarchiwizować tego klienta?";
const ARCHIVE_FAILED = "Nie udało się zarchiwizować klienta. Spróbuj ponownie.";
const RESTORE_FAILED = "Nie udało się przywrócić klienta. Spróbuj ponownie.";
const ARCHIVED_NOTICE = "Klient zarchiwizowany. Możesz go przywrócić.";
const RESTORED_NOTICE = "Klient przywrócony. Jest znowu na liście aktywnych klientów.";
const ACTIVE_STATE = "Klient aktywny";
const ARCHIVED_STATE = "Klient zarchiwizowany";

const archived = storedWith({ archived: true });

function answered(isArchived: boolean): CustomerRecord {
  return storedWith({ name: ANSWERED_NAME, archived: isArchived });
}

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

function heading(name: string) {
  return screen.queryByRole("heading", { level: 1, name });
}

async function confirmArchive() {
  const user = userEvent.setup({ delay: null });
  await user.click(archiveAction() as HTMLElement);
  const dialog = await screen.findByRole("dialog", { name: ARCHIVE_TITLE });
  await user.click(within(dialog).getByRole("button", { name: "Archiwizuj klienta" }));
}

async function clickRestore() {
  const user = userEvent.setup({ delay: null });
  await user.click(restoreAction() as HTMLElement);
}

describe("K-01 an archive answered 200 with archived: false is the archive failure", () => {
  it("shows the archive failure alert and keeps the active customer with its pre-click name", async () => {
    const { calls } = await openCustomer(stored, {
      [`POST ${ARCHIVE_URL}`]: { status: 200, body: answered(false) },
    });

    await confirmArchive();

    expect(await screen.findByRole("alert")).toHaveTextContent(ARCHIVE_FAILED);
    expect(screen.queryByText(ARCHIVED_NOTICE)).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText(ACTIVE_STATE)).toBeVisible();
    expect(archiveAction()).toBeVisible();
    expect(restoreAction()).toBeNull();
    expect(heading(stored.name)).toBeVisible();
    expect(heading(ANSWERED_NAME)).toBeNull();
    expect(requests(calls, "POST", ARCHIVE_URL)).toHaveLength(1);
  });

  it("contrast: the same archive answered with archived: true shows the notice and the answer", async () => {
    await openCustomer(stored, {
      [`POST ${ARCHIVE_URL}`]: { status: 200, body: answered(true) },
    });

    await confirmArchive();

    expect(await screen.findByRole("status")).toHaveTextContent(ARCHIVED_NOTICE);
    expect(screen.getByText(ARCHIVED_STATE)).toBeVisible();
    expect(restoreAction()).toBeVisible();
    expect(archiveAction()).toBeNull();
    expect(heading(ANSWERED_NAME)).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("K-02 a restore answered 200 with archived: true is the restore failure", () => {
  it("shows the restore failure alert and keeps the archived customer with its pre-click name", async () => {
    const { calls } = await openCustomer(archived, {
      [`POST ${RESTORE_URL}`]: { status: 200, body: answered(true) },
    });

    await clickRestore();

    expect(await screen.findByRole("alert")).toHaveTextContent(RESTORE_FAILED);
    expect(screen.queryByText(RESTORED_NOTICE)).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText(ARCHIVED_STATE)).toBeVisible();
    expect(restoreAction()).toBeVisible();
    expect(archiveAction()).toBeNull();
    expect(heading(archived.name)).toBeVisible();
    expect(heading(ANSWERED_NAME)).toBeNull();
    expect(requests(calls, "POST", RESTORE_URL)).toHaveLength(1);
  });

  it("contrast: the same restore answered with archived: false shows the notice and the answer", async () => {
    await openCustomer(archived, {
      [`POST ${RESTORE_URL}`]: { status: 200, body: answered(false) },
    });

    await clickRestore();

    expect(await screen.findByRole("status")).toHaveTextContent(RESTORED_NOTICE);
    expect(screen.getByText(ACTIVE_STATE)).toBeVisible();
    expect(archiveAction()).toBeVisible();
    expect(restoreAction()).toBeNull();
    expect(heading(ANSWERED_NAME)).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
