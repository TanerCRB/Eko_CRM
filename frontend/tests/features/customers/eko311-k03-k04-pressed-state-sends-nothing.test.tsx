import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { pageNavigation } from "../../../src/api/navigation";
import {
  type ListAnswer,
  listOf,
  mountListScreen,
  NOTHING,
  POINTER_TEXT,
  POINTER_TITLE,
  searchBox,
  settle,
  stateButton,
  stubListScreen,
  unmountListScreen,
} from "../../support/customer-list-screen";

// EKO-3-11 K-03/K-04 (EKO-3-05 frontend A-10): on a settled list, clicking the state-filter value
// already pressed sends no list request and leaves the list as shown. Every route a repeat could
// reach answers with another name, so a repeat would change what the list shows. Names are invented.

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

// Serves the answers in order, one per request; the last one repeats.
function inTurn(...answers: ListAnswer[]) {
  const queue = [...answers];
  return () => {
    const next = queue.length > 1 ? queue.shift() : queue[0];
    return next === undefined
      ? Promise.reject(new Error("no answer"))
      : Promise.resolve(next);
  };
}

function states(lists: readonly URL[]) {
  return lists.map((url) => url.searchParams.getAll("state"));
}

function link(name: string) {
  return screen.queryByRole("link", { name });
}

describe("K-03 the settled default list: clicking the pressed Aktywni sends nothing", () => {
  it("sends no list request and keeps the same item, Aktywni pressed and no loading status", async () => {
    let clicked = false;
    const { lists } = stubListScreen(["rep"], {
      // The mount's requests (two under StrictMode) get the first answer; a repeat the other one.
      "||": () => Promise.resolve(clicked ? listOf(["Powtórka Domyślna", false]) : listOf(["Kowal Agro", false])),
      "||active": listOf(["Powtórka Aktywnych", false]),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    expect(await screen.findByRole("link", { name: "Kowal Agro" })).toBeVisible();
    await settle();
    const before = lists.length;

    clicked = true;
    await user.click(stateButton("Aktywni"));
    await settle();

    expect(lists.slice(before)).toEqual([]);
    expect(link("Kowal Agro")).toBeVisible();
    expect(link("Powtórka Domyślna")).toBeNull();
    expect(link("Powtórka Aktywnych")).toBeNull();
    expect(stateButton("Aktywni")).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("contrast: clicking Archiwum on the same screen sends exactly one request with state=archived", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "||archived": listOf(["Nowak Farma", true]),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await settle();
    const before = lists.length;

    await user.click(stateButton("Archiwum"));
    expect(await screen.findByRole("link", { name: "Nowak Farma" })).toBeVisible();
    await settle();

    expect(states(lists.slice(before))).toEqual([["archived"]]);
    expect(link("Kowal Agro")).toBeNull();
  });

  it("edge: on the no-active-customers pointer, clicking Aktywni sends neither the list nor the archived check", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": NOTHING,
      "||active": NOTHING,
      "||archived": listOf(["Nowak Farma", true]),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    expect(await screen.findByRole("heading", { name: POINTER_TITLE })).toBeVisible();
    await settle();
    const before = lists.length;

    await user.click(stateButton("Aktywni"));
    await settle();

    expect(lists.slice(before)).toEqual([]);
    expect(screen.getByRole("heading", { name: POINTER_TITLE })).toBeVisible();
    expect(screen.getByText(POINTER_TEXT)).toBeVisible();
    expect(stateButton("Aktywni")).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("K-04 a state picked earlier: clicking that pressed value again sends nothing", () => {
  it("Archiwum picked, then Archiwum again: no list request, the same archived item, Archiwum pressed", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "||archived": inTurn(listOf(["Nowak Farma", true]), listOf(["Powtórka Archiwum", true])),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.click(stateButton("Archiwum"));
    expect(await screen.findByRole("link", { name: "Nowak Farma" })).toBeVisible();
    await settle();
    const before = lists.length;

    await user.click(stateButton("Archiwum"));
    await settle();

    expect(lists.slice(before)).toEqual([]);
    expect(link("Nowak Farma")).toBeVisible();
    expect(link("Powtórka Archiwum")).toBeNull();
    expect(stateButton("Archiwum")).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("contrast: Wszyscy on the same settled Archiwum screen sends exactly one request with state=both", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "||archived": listOf(["Nowak Farma", true]),
      "||both": listOf(["Kowal Agro", false], ["Nowak Farma", true], ["Wiśniewski Sad", false]),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.click(stateButton("Archiwum"));
    await screen.findByRole("link", { name: "Nowak Farma" });
    await settle();
    const before = lists.length;

    await user.click(stateButton("Wszyscy"));
    expect(await screen.findByRole("link", { name: "Wiśniewski Sad" })).toBeVisible();
    await settle();

    expect(states(lists.slice(before))).toEqual([["both"]]);
    expect(stateButton("Wszyscy")).toHaveAttribute("aria-pressed", "true");
  });

  it("edge: Archiwum, then Aktywni picked explicitly (one state=active), then Aktywni again sends nothing", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "||archived": listOf(["Nowak Farma", true]),
      "||active": inTurn(listOf(["Zielona Łąka", false]), listOf(["Powtórka Aktywnych", false])),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.click(stateButton("Archiwum"));
    await screen.findByRole("link", { name: "Nowak Farma" });
    await settle();
    const picked = lists.length;
    await user.click(stateButton("Aktywni"));
    expect(await screen.findByRole("link", { name: "Zielona Łąka" })).toBeVisible();
    await settle();
    expect(states(lists.slice(picked))).toEqual([["active"]]);
    const before = lists.length;

    await user.click(stateButton("Aktywni"));
    await settle();

    expect(lists.slice(before)).toEqual([]);
    expect(link("Zielona Łąka")).toBeVisible();
    expect(link("Powtórka Aktywnych")).toBeNull();
    expect(stateButton("Aktywni")).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("edge: with a search term in effect, clicking the pressed Archiwum again sends nothing", async () => {
    const { lists } = stubListScreen(["rep"], {
      "||": listOf(["Kowal Agro", false]),
      "kowal||": listOf(["Kowal Agro", false]),
      "kowal||archived": inTurn(listOf(["Kowalski Sad", true]), listOf(["Powtórka Szukania", true])),
    });
    const user = userEvent.setup({ delay: null });
    mountListScreen();
    await screen.findByRole("link", { name: "Kowal Agro" });
    await user.type(searchBox(), "kowal{Enter}");
    await settle();
    await user.click(stateButton("Archiwum"));
    expect(await screen.findByRole("link", { name: "Kowalski Sad" })).toBeVisible();
    await settle();
    const before = lists.length;

    await user.click(stateButton("Archiwum"));
    await settle();

    expect(lists.slice(before)).toEqual([]);
    expect(link("Kowalski Sad")).toBeVisible();
    expect(link("Powtórka Szukania")).toBeNull();
    expect(stateButton("Archiwum")).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
