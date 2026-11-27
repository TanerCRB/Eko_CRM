import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { pageNavigation } from "../../../src/api/navigation";
import {
  listOf,
  mountListScreen,
  NOTHING,
  POINTER_TITLE,
  settle,
  stateButton,
  stubListScreen,
  unmountListScreen,
} from "../../support/customer-list-screen";

// EKO-3-10 K-06: the Aktywni view shows exactly the default answer's items; the archived answer
// adds no item, name or count to the screen, the location or browser storage.

const ARCHIVED_NAME = "Nowak Farma";
const MARKUP_NAME = "<b>Żółta Łąka</b>";

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  unmountListScreen();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("K-06: the default view shows only what the default answer holds", () => {
  it("a non-empty default answer is shown as it is, from a request with no `state`", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "||archived": listOf([ARCHIVED_NAME, true]),
      "||both": listOf(["Kowal Agro", false], [ARCHIVED_NAME, true]),
    });
    mountListScreen();

    expect(await screen.findByRole("link", { name: "Kowal Agro" })).toBeVisible();
    await settle();
    const list = screen.getByRole("list", { name: "Lista klientów" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.queryByText(ARCHIVED_NAME)).not.toBeInTheDocument();
    expect(lists[0]?.searchParams.has("state")).toBe(false);
    expect(lists.map((url) => url.search)).toEqual(["", ""]);
  });

  it("an empty default answer with archived customers shows no archived name, no number, nothing stored", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": NOTHING,
      "||archived": listOf([ARCHIVED_NAME, true], [MARKUP_NAME, true], ["Sad Trzeci", true]),
    });
    mountListScreen();

    expect(await screen.findByRole("heading", { name: POINTER_TITLE })).toBeVisible();
    const main = screen.getByRole("main");
    for (const name of [ARCHIVED_NAME, MARKUP_NAME, "Żółta Łąka", "Sad Trzeci"]) {
      expect(main.textContent).not.toContain(name);
    }
    expect(main.textContent).not.toMatch(/\d/);
    expect(main.querySelector("b")).toBeNull();
    expect(screen.queryByRole("list", { name: "Lista klientów" })).not.toBeInTheDocument();
    expect(lists[0]?.searchParams.has("state")).toBe(false);

    const href = decodeURIComponent(window.location.href);
    for (const value of [ARCHIVED_NAME, "Żółta Łąka", "state", "archived"]) {
      expect(href).not.toContain(value);
    }
    expect(window.location.search).toBe("");
    expect(window.location.hash).toBe("");
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
  });

  it("contrast: picking Wszyscy shows the archived customer with its mark", async () => {
    stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "||both": listOf(["Kowal Agro", false], [ARCHIVED_NAME, true]),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });

    await user.click(stateButton("Wszyscy"));

    const link = await screen.findByRole("link", { name: ARCHIVED_NAME });
    await waitFor(() => {
      expect(link.closest("li")).toHaveTextContent("Zarchiwizowany");
    });
  });
});
