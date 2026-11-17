import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { pageNavigation } from "../../../src/api/navigation";
import { SessionGate } from "../../../src/features/session/SessionGate";
import { LOGOUT_URL, SESSION_URL, respond } from "../../support/http";

// QA (EKO-2-02 K-08): the no-role screen's double-submit guard has two parts, the in-flight ref
// and the disabled button. The developer's double-click test lets React commit `disabled`
// between the clicks, so it cannot tell the parts apart, and today the ref is proven only through
// the account panel, which shares the hook. Here, on the no-role screen itself: two clicks in one
// task reach the handler twice and only the ref stops the second logout; and while the logout is
// in flight the button is disabled and busy, so a removed `disabled` is seen as well.

let assign: MockInstance<(url: string) => void>;

beforeEach(() => {
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
}

// The session read answers 403; the logout stays pending, so the screen stays in flight.
function stubNoRoleWithPendingLogout() {
  const logouts: string[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    if (url === SESSION_URL) {
      return respond({ status: 403, body: { detail: "no application role" } });
    }
    if (url === LOGOUT_URL) {
      logouts.push(url);
      return new Promise<Response>(() => undefined);
    }
    return Promise.reject(new Error(`Unexpected request to ${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { logouts };
}

const findLogoutButton = () => screen.findByRole("button", { name: "Wyloguj się" });
const logoutButton = () => screen.getByRole("button", { name: "Wyloguj się" });

function renderGate() {
  return render(<SessionGate retryDelaysMs={[]}>{() => <p>shell</p>}</SessionGate>);
}

describe("QA K-08: one logout per user action on the no-role screen", () => {
  it("sends one logout for two clicks in the same task, before the disabled state renders", async () => {
    const { logouts } = stubNoRoleWithPendingLogout();
    renderGate();
    const button = await findLogoutButton();

    act(() => {
      button.click();
      expect(button).not.toBeDisabled();
      button.click();
    });

    expect(logouts).toEqual([LOGOUT_URL]);
  });

  it("disables the logout button and marks it busy while the logout is in flight", async () => {
    stubNoRoleWithPendingLogout();
    const user = userEvent.setup();
    renderGate();
    const button = await findLogoutButton();
    // Contrast: before the click the same button is enabled and not busy.
    expect(button).toBeEnabled();
    expect(button).toHaveAttribute("aria-busy", "false");

    await user.click(button);

    expect(logoutButton()).toBeDisabled();
    expect(logoutButton()).toHaveAttribute("aria-busy", "true");
    expect(assign).not.toHaveBeenCalled();
  });
});
