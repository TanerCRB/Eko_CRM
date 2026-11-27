import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionInfo } from "../../../src/api/auth";
import { pageNavigation } from "../../../src/api/navigation";
import {
  FIRST_TEXT,
  FIRST_TITLE,
  listOf,
  mountListScreen,
  NO_MATCH_TITLE,
  NOTHING,
  POINTER_TEXT,
  POINTER_TITLE,
  searchBox,
  stateButton,
  stubListScreen,
  unmountListScreen,
} from "../../support/customer-list-screen";

// EKO-3-10 K-01: an empty default list of a caller whose scope holds archived customers says
// there are no active customers and points at Archiwum / Wszyscy, never the first-customer text.

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  unmountListScreen();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

async function expectPointer() {
  const heading = await screen.findByRole("heading", { name: POINTER_TITLE });
  expect(heading).toBeVisible();
  expect(heading.textContent).toBe("Brak aktywnych klientów");
  expect(screen.getByText(POINTER_TEXT).textContent).toBe(
    "Zarchiwizowanych klientów zobaczysz po wybraniu filtru Archiwum lub Wszyscy.",
  );
  expect(screen.queryByText(FIRST_TITLE)).not.toBeInTheDocument();
  expect(screen.queryByText(FIRST_TEXT)).not.toBeInTheDocument();
}

describe("K-01: only archived customers in scope gives the no-active pointer, not the first-customer text", () => {
  const sessions: [string, SessionInfo["roles"]][] = [
    ["rep", ["rep"]],
    ["manager", ["manager"]],
    ["rep+manager", ["rep", "manager"]],
  ];

  for (const [label, roles] of sessions) {
    it(`a ${label} session with exactly one archived customer sees the pointer`, async () => {
      stubListScreen(roles, {
        "||": NOTHING,
        "||archived": listOf(["Sad Zamknięty", true]),
      });
      mountListScreen();

      await expectPointer();
    });
  }

  it("several archived customers give the same pointer", async () => {
    stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": listOf(["Sad Zamknięty", true], ["Łąka Żółta", true], ["Pole Trzecie", true]),
    });
    mountListScreen();

    await expectPointer();
  });

  it("contrast: no archived customer in scope gives the first-customer text and no pointer", async () => {
    stubListScreen(["rep"], { "||": NOTHING, "||archived": NOTHING });
    mountListScreen();

    expect(await screen.findByRole("heading", { name: FIRST_TITLE })).toBeVisible();
    expect(screen.getByText(FIRST_TEXT)).toBeVisible();
    expect(screen.queryByText(POINTER_TITLE)).not.toBeInTheDocument();
    expect(screen.queryByText(POINTER_TEXT)).not.toBeInTheDocument();
  });

  it("edge: Archiwum then Aktywni (state=active) answers as the default list does", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": listOf(["Sad Zamknięty", true]),
      "||active": NOTHING,
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await expectPointer();

    await user.click(stateButton("Archiwum"));
    expect(await screen.findByRole("link", { name: "Sad Zamknięty" })).toBeVisible();
    const before = lists.length;
    await user.click(stateButton("Aktywni"));

    await expectPointer();
    expect(lists.slice(before).map((url) => url.searchParams.getAll("state"))).toEqual([
      ["active"],
      ["archived"],
    ]);
  });

  it("edge: typing a term and clearing it, or leaving only spaces, returns to the pointer", async () => {
    stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": listOf(["Sad Zamknięty", true]),
      "kowal||": NOTHING,
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await expectPointer();

    await user.type(searchBox(), "kowal{Enter}");
    expect(await screen.findByRole("heading", { name: NO_MATCH_TITLE })).toBeVisible();
    await user.clear(searchBox());
    await user.type(searchBox(), "{Enter}");
    await expectPointer();

    await user.type(searchBox(), "kowal{Enter}");
    expect(await screen.findByRole("heading", { name: NO_MATCH_TITLE })).toBeVisible();
    await user.clear(searchBox());
    await user.type(searchBox(), "   {Enter}");
    await expectPointer();
  });
});
