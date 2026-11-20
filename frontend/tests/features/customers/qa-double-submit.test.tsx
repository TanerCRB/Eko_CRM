import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import { pageNavigation } from "../../../src/api/navigation";
import type { CustomerRecord } from "../../../src/api/customers";
import {
  CUSTOMERS_URL,
  deferred,
  stubCustomerApi,
  type CustomerReply,
  type RecordedCall,
} from "../../support/customers-http";

// QA, K-07 double-click edge (EKO-3-01): the save is guarded twice, by an in-flight flag and by
// disabling the button while the create is in flight. The K-07 double-click test passes with
// either guard removed, so each is pinned here on its own. Synthetic values only (ADR-0005).
const NAME = "Gospodarstwo Podwojne";
const saved: CustomerRecord = {
  id: "7a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
  name: NAME,
  country: "PL",
  contacts: [],
  street: null,
  postal_code: null,
  town: null,
  voivodeship: null,
  county: null,
  tax_id: null,
};

beforeAll(async () => {
  await import("../../../src/features/Klienci");
});

beforeEach(() => {
  vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
  window.history.replaceState(null, "", "/klienci/nowy");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function posts(calls: readonly RecordedCall[]) {
  return calls.filter((call) => call.method === "POST" && call.url === CUSTOMERS_URL);
}

async function heldCreate() {
  const held = deferred<CustomerReply>();
  const { calls } = stubCustomerApi({ [`POST ${CUSTOMERS_URL}`]: () => held.promise });
  const user = userEvent.setup({ delay: null });
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: "Nowy klient" });
  await user.click(screen.getByLabelText(/Nazwa klienta/));
  await user.paste(NAME);
  return { calls, held, user };
}

describe("QA: each double-submit guard of the customer form holds on its own", () => {
  it("while the create is in flight the save button is disabled", async () => {
    const { calls, held, user } = await heldCreate();
    const save = screen.getByRole("button", { name: "Zapisz klienta" });
    expect(save).toBeEnabled();

    await user.click(save);

    expect(screen.getByRole("button", { name: "Zapisz klienta" })).toBeDisabled();
    expect(posts(calls)).toHaveLength(1);
    held.resolve({ status: 201, body: saved });
    await screen.findByRole("heading", { level: 1, name: NAME });
  });

  it("a second submit of the form while the first is in flight sends nothing", async () => {
    const { calls, held } = await heldCreate();
    const form = screen.getByRole("form", { name: "Nowy klient" });

    // Two submits reach the form directly; a disabled button cannot stop a submit event.
    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(posts(calls)).toHaveLength(1);
    held.resolve({ status: 201, body: saved });
    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)).toHaveLength(1);
  });

  it("contrast: after a refused create the form submits again", async () => {
    const replies: CustomerReply[] = [
      { status: 403, body: { detail: "not permitted" } },
      { status: 201, body: saved },
    ];
    const { calls } = stubCustomerApi({
      [`POST ${CUSTOMERS_URL}`]: () => {
        const reply = replies.shift();
        if (reply === undefined) {
          throw new Error("more creates than replies");
        }
        return Promise.resolve(reply);
      },
    });
    const user = userEvent.setup({ delay: null });
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "Nowy klient" });
    await user.click(screen.getByLabelText(/Nazwa klienta/));
    await user.paste(NAME);

    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
    expect(await screen.findByText("Twoje konto nie może dodawać klientów.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)).toHaveLength(2);
  });
});
