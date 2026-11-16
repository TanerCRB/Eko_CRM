import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccountPanel } from "../../../src/features/session/AccountPanel";
import { pageNavigation } from "../../../src/api/navigation";

// QA (EKO-2-01): the double-submit guard has two parts, the in-flight ref and the disabled
// button. A user-event double click lets React commit `disabled` between the two clicks, so it
// cannot tell the parts apart; two clicks dispatched in one task, before any commit, reach the
// handler twice and only the ref stops the second logout.

const session = { subject: "synthetic-subject-0001", name: "Anna Testowa" };

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const logoutButton = () => screen.getByRole("button", { name: "Wyloguj się" });

describe("QA K-03 / G-2: one logout per user action", () => {
  it("sends one logout for two clicks in the same task, before the disabled state renders", () => {
    const fetchMock = vi.fn(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetchMock);
    render(<AccountPanel session={session} />);
    const button = logoutButton();

    act(() => {
      button.click();
      expect(button).not.toBeDisabled();
      button.click();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(logoutButton()).toBeDisabled();
  });

  it("contrast: two separate user clicks after a failed logout send two logouts", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response('{"detail":"temporarily unavailable"}', { status: 503 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<AccountPanel session={session} />);

    await user.click(logoutButton());
    await vi.waitFor(() => {
      expect(logoutButton()).not.toBeDisabled();
    });
    await user.click(logoutButton());

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });
});
