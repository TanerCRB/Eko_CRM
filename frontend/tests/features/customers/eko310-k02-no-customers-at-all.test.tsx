import { screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionInfo } from "../../../src/api/auth";
import { pageNavigation } from "../../../src/api/navigation";
import {
  FIRST_TEXT,
  FIRST_TITLE,
  listOf,
  mountListScreen,
  NOTHING,
  POINTER_TEXT,
  POINTER_TITLE,
  settle,
  stubListScreen,
  unmountListScreen,
} from "../../support/customer-list-screen";

// EKO-3-10 K-02: a caller with no customers at all, none active and none archived, still gets
// the first-customer text on the default list, once the archived request has answered empty.

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

describe("K-02: no customers at all keeps the first-customer text", () => {
  const sessions: [string, SessionInfo["roles"]][] = [
    ["rep", ["rep"]],
    ["manager", ["manager"]],
  ];

  for (const [label, roles] of sessions) {
    it(`a ${label} session whose default and archived lists both answer empty sees the first-customer text`, async () => {
      const { lists } = stubListScreen(roles, { "||": NOTHING, "||archived": NOTHING });
      mountListScreen();

      expect(await screen.findByRole("heading", { name: FIRST_TITLE })).toBeVisible();
      expect(screen.getByText(FIRST_TEXT)).toBeVisible();
      expect(screen.queryByText(POINTER_TITLE)).not.toBeInTheDocument();
      expect(screen.queryByText(POINTER_TEXT)).not.toBeInTheDocument();
      await settle();
      // StrictMode runs the mount effect twice in development: the first default request is dropped.
      expect(lists.map((url) => url.search)).toEqual(["", "", "?state=archived"]);
    });
  }

  it("contrast: one archived customer turns the first-customer text into the pointer", async () => {
    stubListScreen(["rep"], { "||": NOTHING, "||archived": listOf(["Sad Zamknięty", true]) });
    mountListScreen();

    expect(await screen.findByRole("heading", { name: POINTER_TITLE })).toBeVisible();
    expect(screen.queryByText(FIRST_TITLE)).not.toBeInTheDocument();
    expect(screen.queryByText(FIRST_TEXT)).not.toBeInTheDocument();
  });
});
