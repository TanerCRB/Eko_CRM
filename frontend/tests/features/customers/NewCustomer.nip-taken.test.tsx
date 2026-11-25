import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../../src/App";
import type { SessionInfo } from "../../../src/api/auth";
import type { CustomerRecord, NipTakenProblem } from "../../../src/api/customers";
import { pageNavigation } from "../../../src/api/navigation";
import type { VoivodeshipList } from "../../../src/api/reference";
import { SessionContext } from "../../../src/features/session/sessionContext";
import {
  CUSTOMERS_URL,
  deferred,
  VOIVODESHIPS_URL,
  type CustomerReply,
  type RecordedCall,
} from "../../support/customers-http";

// K-07 (EKO-3-03): the create form's answer to a NIP another customer already holds. The server
// decides the refusal and whether a reference comes with it (K-01..K-03); the SPA only shows it.
// Synthetic values throughout (ADR-0005): the NIP is checksum-valid and assembled at run time from
// a `000` prefix, so no NIP-shaped literal sits in the source; e-mails end in `.invalid`.
const NEW_ID = "6e3f9a2b-4c5d-4e6f-8a7b-8c9d0e1f2a3b";
const EXISTING_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
const NAME = "Gospodarstwo Powtórzone";
const EXISTING_NAME = "Gospodarstwo Istniejące";
const STREET = "Polna 7";
const POSTAL_CODE = "00-950";
const TOWN = "Kraków";
const NIP_DIGITS = "0".repeat(3) + "123456" + "2";
const ENTERED_NIP = `PL ${NIP_DIGITS.slice(0, 3)}-${NIP_DIGITS.slice(3, 6)}-${NIP_DIGITS.slice(6, 8)}-${NIP_DIGITS.slice(8)}`;
const PHONE = "601234567";
const PHONE_NOTE = "Właściciel";
const EMAIL = "powtorzone@example.invalid";
const EMAIL_NOTE = "Faktury";

const REP_SENTENCE = "Klient z tym numerem NIP już istnieje — skontaktuj się z kierownikiem.";
const MANAGER_SENTENCE = "Klient z tym numerem NIP już istnieje.";
const OPEN_EXISTING = "Otwórz istniejącego klienta";
const SERVER_DETAIL = "a customer with this NIP already exists - contact your manager";

// The two bodies fixed at gate 1: K-02's for a rep, K-03's (with the reference) for a manager.
const repRefusal: NipTakenProblem = { detail: SERVER_DETAIL };
const managerRefusal: NipTakenProblem = { detail: SERVER_DETAIL, existing_customer_id: EXISTING_ID };

type Reply = CustomerReply | { status: 409; body: NipTakenProblem } | { status: 409; raw: string };
type Source = Reply | (() => Promise<Reply>);

const register: VoivodeshipList = {
  as_of: "2026-01-01",
  voivodeships: [{ name: "małopolskie", counties: ["krakowski", "Kraków"] }],
};

function customer(id: string, name: string): CustomerRecord {
  return {
    id,
    name,
    country: "PL",
    street: null,
    postal_code: null,
    town: null,
    voivodeship: null,
    county: null,
    tax_id: null,
    contacts: [],
    archived: false,
  };
}

const created: Reply = { status: 201, body: customer(NEW_ID, NAME) };

function session(roles: SessionInfo["roles"]): SessionInfo {
  return { subject: "synthetic-staff-0303", name: "Ewa Testowa", roles };
}
const repSession = session(["rep"]);
const managerSession = session(["rep", "manager"]);

// Typed like `stubCustomerApi`, plus the 409 this task adds; the creates are answered in order,
// the last answer repeating.
function stub(creates: readonly Source[]) {
  const calls: RecordedCall[] = [];
  let served = 0;
  const routes: Record<string, Source> = {
    [`GET ${CUSTOMERS_URL}`]: { status: 200, body: { items: [] } },
    [`GET ${VOIVODESHIPS_URL}`]: { status: 200, body: register },
    [`GET ${CUSTOMERS_URL}/${EXISTING_ID}`]: { status: 200, body: customer(EXISTING_ID, EXISTING_NAME) },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const method = init?.method ?? "GET";
      const sent = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
      calls.push({ method, url, body: sent });
      let source: Source | undefined;
      if (method === "POST" && url === CUSTOMERS_URL) {
        source = creates[Math.min(served, creates.length - 1)];
        served += 1;
      } else {
        source = routes[`${method} ${url}`];
      }
      if (source === undefined) {
        throw new Error(`Unexpected request ${method} ${url}`);
      }
      const reply = typeof source === "function" ? await source() : source;
      const text = "raw" in reply ? reply.raw : JSON.stringify("older" in reply ? reply.older : reply.body);
      return new Response(text, {
        status: reply.status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return { calls };
}

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

async function openForm(signedIn: SessionInfo) {
  const user = userEvent.setup({ delay: null });
  render(
    <SessionContext.Provider value={signedIn}>
      <App />
    </SessionContext.Provider>,
  );
  await screen.findByRole("heading", { level: 1, name: "Nowy klient" });
  return user;
}

async function enter(user: UserEvent, field: HTMLElement, value: string) {
  await user.click(field);
  await user.paste(value);
}

const label = {
  name: /^Nazwa klienta/,
  street: /^Ulica i numer/,
  postalCode: /^Kod pocztowy/,
  town: /^Miejscowość/,
  voivodeship: /^Województwo/,
  county: /^Powiat/,
  nip: /^NIP/,
};

function contactGroups() {
  return screen.getAllByRole("group", { name: /^Kontakt \d+$/ });
}

async function addContact(user: UserEvent, kind: "phone" | "email", value: string, note: string) {
  await user.click(screen.getByRole("button", { name: "Dodaj kontakt" }));
  const group = contactGroups().at(-1);
  if (group === undefined) {
    throw new Error("no contact row appeared");
  }
  const scope = within(group);
  await user.selectOptions(scope.getByLabelText("Rodzaj kontaktu"), kind);
  await enter(user, scope.getByLabelText("Numer telefonu lub adres e-mail"), value);
  await enter(user, scope.getByLabelText("Opis kontaktu"), note);
  return group;
}

interface Typed {
  name: string;
  phoneNote: string;
}

async function fillForm(user: UserEvent, typed: Typed = { name: NAME, phoneNote: PHONE_NOTE }) {
  await enter(user, screen.getByLabelText(label.name), typed.name);
  await enter(user, screen.getByLabelText(label.street), STREET);
  await enter(user, screen.getByLabelText(label.postalCode), POSTAL_CODE);
  await enter(user, screen.getByLabelText(label.town), TOWN);
  const voivodeship = screen.getByLabelText(label.voivodeship);
  await waitFor(() => {
    expect(voivodeship).toBeEnabled();
  });
  await user.selectOptions(voivodeship, "małopolskie");
  await user.selectOptions(screen.getByLabelText(label.county), "krakowski");
  await enter(user, screen.getByLabelText(label.nip), ENTERED_NIP);
  await addContact(user, "phone", PHONE, typed.phoneNote);
  const second = await addContact(user, "email", EMAIL, EMAIL_NOTE);
  await user.click(within(second).getByRole("radio", { name: "Kontakt główny" }));
}

function expectEverythingKept(typed: Typed = { name: NAME, phoneNote: PHONE_NOTE }) {
  expect(screen.getByRole("heading", { level: 1, name: "Nowy klient" })).toBeVisible();
  expect(screen.getByLabelText(label.name)).toHaveValue(typed.name);
  expect(screen.getByLabelText(label.street)).toHaveValue(STREET);
  expect(screen.getByLabelText(label.postalCode)).toHaveValue(POSTAL_CODE);
  expect(screen.getByLabelText(label.town)).toHaveValue(TOWN);
  expect(screen.getByLabelText(label.voivodeship)).toHaveValue("małopolskie");
  expect(screen.getByLabelText(label.county)).toHaveValue("krakowski");
  expect(screen.getByLabelText(label.nip)).toHaveValue(ENTERED_NIP);
  const groups = contactGroups();
  expect(groups).toHaveLength(2);
  const [phone, email] = groups.map((group) => within(group));
  expect(phone?.getByLabelText("Rodzaj kontaktu")).toHaveValue("phone");
  expect(phone?.getByLabelText("Numer telefonu lub adres e-mail")).toHaveValue(PHONE);
  expect(phone?.getByLabelText("Opis kontaktu")).toHaveValue(typed.phoneNote);
  expect(phone?.getByRole("radio", { name: "Kontakt główny" })).not.toBeChecked();
  expect(email?.getByLabelText("Rodzaj kontaktu")).toHaveValue("email");
  expect(email?.getByLabelText("Numer telefonu lub adres e-mail")).toHaveValue(EMAIL);
  expect(email?.getByLabelText("Opis kontaktu")).toHaveValue(EMAIL_NOTE);
  expect(email?.getByRole("radio", { name: "Kontakt główny" })).toBeChecked();
}

function posts(calls: readonly RecordedCall[]) {
  return calls.filter((call) => call.method === "POST" && call.url === CUSTOMERS_URL);
}

async function save(user: UserEvent) {
  await user.click(screen.getByRole("button", { name: "Zapisz klienta" }));
}

// The NIP field's own error: marked invalid and described by the sentence, not a form alert.
async function expectNipError(sentence: string) {
  const nip = screen.getByLabelText(label.nip);
  await waitFor(() => {
    expect(nip).toHaveAttribute("aria-invalid", "true");
  });
  expect(nip).toHaveAccessibleDescription(sentence);
}

const expectedBody = {
  name: NAME,
  country: "PL",
  street: STREET,
  postal_code: POSTAL_CODE,
  town: TOWN,
  voivodeship: "małopolskie",
  county: "krakowski",
  tax_id: ENTERED_NIP,
  contacts: [
    { kind: "phone", value: PHONE, note: PHONE_NOTE, primary: false },
    { kind: "email", value: EMAIL, note: EMAIL_NOTE, primary: true },
  ],
};

describe("K-07 (EKO-3-03): a rep's create refused for a taken NIP", () => {
  it("shows the rep sentence at the NIP field, keeps every typed value, contacts included, and shows no link", async () => {
    const { calls } = stub([{ status: 409, body: repRefusal }]);
    const user = await openForm(repSession);
    await fillForm(user);

    await save(user);

    await expectNipError(REP_SENTENCE);
    expectEverythingKept();
    expect(screen.queryByRole("link", { name: OPEN_EXISTING })).not.toBeInTheDocument();
    expect(screen.queryByText(MANAGER_SENTENCE)).not.toBeInTheDocument();
    expect(screen.queryByText(SERVER_DETAIL)).not.toBeInTheDocument();
    expect(posts(calls)).toHaveLength(1);
    expect(posts(calls)[0]?.body).toEqual(expectedBody);
  });

  it("a second submit after the refusal sends a new create with the kept values", async () => {
    const { calls } = stub([{ status: 409, body: repRefusal }, created]);
    const user = await openForm(repSession);
    await fillForm(user);
    await save(user);
    await expectNipError(REP_SENTENCE);

    await save(user);

    await screen.findByRole("heading", { level: 1, name: NAME });
    expect(posts(calls)).toHaveLength(2);
    expect(posts(calls)[1]?.body).toEqual(expectedBody);
    expect(window.location.pathname).toBe(`/klienci/${NEW_ID}`);
  });
});

describe("K-07 (EKO-3-03): a manager's create refused for a taken NIP", () => {
  it("shows the manager sentence at the NIP field and a link to /klienci/<reference> that opens the customer view", async () => {
    const { calls } = stub([{ status: 409, body: managerRefusal }]);
    const user = await openForm(managerSession);
    await fillForm(user);

    await save(user);

    await expectNipError(MANAGER_SENTENCE);
    expect(screen.queryByText(REP_SENTENCE)).not.toBeInTheDocument();
    expectEverythingKept();
    const link = screen.getByRole("link", { name: OPEN_EXISTING });
    expect(link).toHaveAttribute("href", `/klienci/${EXISTING_ID}`);

    await user.click(link);

    expect(await screen.findByRole("heading", { level: 1, name: EXISTING_NAME })).toBeVisible();
    expect(window.location.pathname).toBe(`/klienci/${EXISTING_ID}`);
    expect(calls.filter((call) => call.url === `${CUSTOMERS_URL}/${EXISTING_ID}`)).toHaveLength(1);
  });

  it("contrast: the same refusal without a reference shows the rep sentence and no link, even in a manager session", async () => {
    stub([{ status: 409, body: repRefusal }]);
    const user = await openForm(managerSession);
    await fillForm(user);

    await save(user);

    await expectNipError(REP_SENTENCE);
    expect(screen.queryByRole("link", { name: OPEN_EXISTING })).not.toBeInTheDocument();
  });

  it("contrast: the answer decides, not the session: a reference in the answer to a rep session gives the link", async () => {
    stub([{ status: 409, body: managerRefusal }]);
    const user = await openForm(repSession);
    await fillForm(user);

    await save(user);

    await expectNipError(MANAGER_SENTENCE);
    expect(screen.getByRole("link", { name: OPEN_EXISTING })).toHaveAttribute(
      "href",
      `/klienci/${EXISTING_ID}`,
    );
  });
});

describe("K-07 (EKO-3-03): contrast, an accepted create", () => {
  it("a 201 for the same form navigates to the new customer's view", async () => {
    const { calls } = stub([created]);
    const user = await openForm(repSession);
    await fillForm(user);

    await save(user);

    expect(await screen.findByRole("heading", { level: 1, name: NAME })).toBeVisible();
    expect(window.location.pathname).toBe(`/klienci/${NEW_ID}`);
    expect(posts(calls)).toHaveLength(1);
    expect(screen.queryByText(REP_SENTENCE)).not.toBeInTheDocument();
  });
});

describe("K-07 (EKO-3-03) edges", () => {
  it.each([
    ["not a UUID", '"not-a-customer-id"'],
    ["a UUID followed by a path", `"${EXISTING_ID}/../nowy"`],
    ["null", "null"],
    ["a number", "5"],
  ])("a reference that is %s gives the rep sentence and no link", async (_case, value) => {
    stub([{ status: 409, raw: `{"detail":"${SERVER_DETAIL}","existing_customer_id":${value}}` }]);
    const user = await openForm(managerSession);
    await fillForm(user);

    await save(user);

    await expectNipError(REP_SENTENCE);
    expect(screen.queryByRole("link", { name: OPEN_EXISTING })).not.toBeInTheDocument();
  });

  it("a double click sends one create, and the refusal is shown once it is answered", async () => {
    const held = deferred<Reply>();
    const { calls } = stub([() => held.promise]);
    const user = await openForm(repSession);
    await fillForm(user);

    await user.dblClick(screen.getByRole("button", { name: "Zapisz klienta" }));
    await save(user);
    held.resolve({ status: 409, body: repRefusal });

    await expectNipError(REP_SENTENCE);
    expect(posts(calls)).toHaveLength(1);
  });

  it("markup in typed values stays text after the refusal", async () => {
    const typed = { name: "<b>Gospodarstwo</b>", phoneNote: "<img src=x onerror=alert(1)>" };
    stub([{ status: 409, body: managerRefusal }]);
    const user = await openForm(managerSession);
    await fillForm(user, typed);

    await save(user);

    await expectNipError(MANAGER_SENTENCE);
    expectEverythingKept(typed);
    expect(document.querySelector("form b, form img")).toBeNull();
  });

  it("the location holds only /klienci/ and the reference's UUID, never a typed value", async () => {
    stub([{ status: 409, body: managerRefusal }]);
    const user = await openForm(managerSession);
    await fillForm(user);
    await save(user);
    await expectNipError(MANAGER_SENTENCE);
    expect(window.location.pathname).toBe("/klienci/nowy");

    await user.click(screen.getByRole("link", { name: OPEN_EXISTING }));
    await screen.findByRole("heading", { level: 1, name: EXISTING_NAME });

    expect(window.location.pathname).toMatch(
      /^\/klienci\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
    expect(window.location.search).toBe("");
    expect(window.location.hash).toBe("");
    const decoded = decodeURIComponent(window.location.href);
    for (const value of [NAME, STREET, TOWN, ENTERED_NIP, NIP_DIGITS, PHONE, EMAIL]) {
      expect(decoded).not.toContain(value);
    }
  });

  it("a 503 from an older backend shows as the existing save failure and keeps every value", async () => {
    stub([{ status: 503, body: { detail: "temporarily unavailable" } }]);
    const user = await openForm(managerSession);
    await fillForm(user);

    await save(user);

    expect(await screen.findByText("Nie udało się zapisać klienta. Spróbuj ponownie.")).toBeVisible();
    expect(screen.getByLabelText(label.nip)).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText(REP_SENTENCE)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: OPEN_EXISTING })).not.toBeInTheDocument();
    expectEverythingKept();
  });
});

describe("K-07 assumptions (EKO-3-03)", () => {
  it("A-01: the refusal is told at the NIP field only, with no form-level alert beside it", async () => {
    stub([{ status: 409, body: repRefusal }]);
    const user = await openForm(repSession);
    await fillForm(user);

    await save(user);

    await expectNipError(REP_SENTENCE);
    expect(screen.getAllByRole("alert").map((alert) => alert.textContent)).toEqual([REP_SENTENCE]);
  });

  it("A-02: a 409 whose body is not the refusal's shape is the existing save failure", async () => {
    stub([{ status: 409, raw: '{"existing_customer_id":"' + EXISTING_ID + '"}' }]);
    const user = await openForm(managerSession);
    await fillForm(user);

    await save(user);

    expect(await screen.findByText("Nie udało się zapisać klienta. Spróbuj ponownie.")).toBeVisible();
    expect(screen.getByLabelText(label.nip)).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByRole("link", { name: OPEN_EXISTING })).not.toBeInTheDocument();
    expectEverythingKept();
  });
});
