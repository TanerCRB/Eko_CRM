import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { pageNavigation } from "../../../src/api/navigation";
import { LoginFailed } from "../../../src/features/session/LoginFailed";
import { stubFetch } from "../../support/http";

let assign: MockInstance<(url: string) => void>;

beforeEach(() => {
  assign = vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("R-03: the refused-login page explains the failure and offers a new login", () => {
  it("names the product and the failure in Polish, by heading", () => {
    const { calls } = stubFetch({});
    render(<LoginFailed />);

    expect(screen.getByRole("heading", { level: 1, name: "Logowanie nie powiodło się" })).toBeVisible();
    expect(screen.getByText("Eko CRM")).toBeInTheDocument();
    expect(screen.getByText(/trwało zbyt długo albo zostało przerwane/)).toBeInTheDocument();
    expect(calls).toEqual([]);
    expect(assign).not.toHaveBeenCalled();
  });

  it("starts exactly one new login to the root page from 'Spróbuj ponownie'", async () => {
    const { calls } = stubFetch({});
    const user = userEvent.setup();
    render(<LoginFailed />);

    await user.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));

    expect(assign).toHaveBeenCalledExactlyOnceWith("/api/auth/login?return_to=%2F");
    expect(calls).toEqual([]);
  });
});
