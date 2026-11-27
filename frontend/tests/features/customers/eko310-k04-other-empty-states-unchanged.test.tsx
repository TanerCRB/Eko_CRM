import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { pageNavigation } from "../../../src/api/navigation";
import {
  ANNA,
  FIRST_TEXT,
  FIRST_TITLE,
  listOf,
  mountListScreen,
  NO_MATCH_TITLE,
  NOTHING,
  POINTER_TEXT,
  POINTER_TITLE,
  searchBox,
  settle,
  stateButton,
  stubListScreen,
  unmountListScreen,
} from "../../support/customer-list-screen";

// EKO-3-10 K-04: with archived customers in scope, the empty states of a search term, a
// manager's owner filter and the Archiwum and Wszyscy filters stay as they were.

const SEARCH_TEXT = "Wpisz inną nazwę, miejscowość lub dane kontaktowe.";
const STATE_TEXT = "Zmień filtr statusu lub wyszukiwanie.";
const ARCHIVED = listOf(["Sad Zamknięty", true]);

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

async function expectNoMatch(explanation: string) {
  expect(await screen.findByRole("heading", { name: NO_MATCH_TITLE })).toBeVisible();
  expect(screen.getByText(explanation)).toBeVisible();
  for (const text of [POINTER_TITLE, POINTER_TEXT, FIRST_TITLE, FIRST_TEXT]) {
    expect(screen.queryByText(text)).not.toBeInTheDocument();
  }
}

function checks(lists: readonly URL[]) {
  return lists.filter((url) => url.search === "?state=archived");
}

describe("K-04: other empty states are unchanged when archived customers exist", () => {
  for (const term of ["kowal", "  kowal  "]) {
    it(`a search for "${term}" that answers empty shows the search's empty state`, async () => {
      const { lists } = stubListScreen(["rep"], {
        "||": listOf(["Kowal Agro", false]),
        "||archived": ARCHIVED,
        "kowal||": NOTHING,
      });
      const user = userEvent.setup({ delay: null });
      mountListScreen();
      await screen.findByRole("link", { name: "Kowal Agro" });

      await user.type(searchBox(), `${term}{Enter}`);

      await expectNoMatch(SEARCH_TEXT);
      await settle();
      expect(checks(lists)).toHaveLength(0);
    });
  }

  it("a manager's owner whose answer is empty, even with archived customers, keeps today's text", async () => {
    const { lists } = stubListScreen(["manager"], {
      "||": listOf(["Kowal Agro", false]),
      "||archived": ARCHIVED,
      [`|${ANNA.subject}|`]: NOTHING,
      [`|${ANNA.subject}|archived`]: ARCHIVED,
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    await user.selectOptions(await screen.findByRole("combobox", { name: "Opiekun klienta" }), ANNA.name);

    await expectNoMatch(SEARCH_TEXT);
    await settle();
    expect(lists.filter((url) => url.searchParams.has("state"))).toHaveLength(0);
  });

  for (const [button, state] of [
    ["Archiwum", "archived"],
    ["Wszyscy", "both"],
  ] as const) {
    it(`${button} answering empty shows the state filter's empty state`, async () => {
      const { lists } = stubListScreen(["rep"], {
        "||": listOf(["Kowal Agro", false]),
        [`||${state}`]: NOTHING,
      });
      const user = userEvent.setup({ delay: null });
      mountListScreen();
      await screen.findByRole("link", { name: "Kowal Agro" });
      const before = lists.length;

      await user.click(stateButton(button));

      await expectNoMatch(STATE_TEXT);
      await settle();
      expect(lists.slice(before).map((url) => url.search)).toEqual([`?state=${state}`]);
    });
  }

  it("edge: a term plus Archiwum answering empty shows the search's empty state", async () => {
    stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "kowal||": listOf(["Kowal Agro", false]),
      "kowal||archived": NOTHING,
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.type(searchBox(), "kowal{Enter}");
    await settle();

    await user.click(stateButton("Archiwum"));

    await expectNoMatch(SEARCH_TEXT);
  });

  it("contrast: the term cleared back to an empty default list shows the pointer instead", async () => {
    stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": ARCHIVED,
      "kowal||": NOTHING,
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await settle();
    await user.type(searchBox(), "kowal{Enter}");
    await expectNoMatch(SEARCH_TEXT);

    await user.clear(searchBox());
    await user.type(searchBox(), "{Enter}");

    expect(await screen.findByRole("heading", { name: POINTER_TITLE })).toBeVisible();
    expect(screen.queryByText(NO_MATCH_TITLE)).not.toBeInTheDocument();
  });
});
