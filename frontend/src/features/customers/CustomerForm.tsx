import { useId, useRef, useState } from "react";
import { countryOptions, POLAND } from "../../api/countries";
import {
  ADDRESS_PARTS,
  type CustomerInput,
  type CustomerRecord,
  type RejectedField,
} from "../../api/customers";
import { Button } from "../../components/Button";
import { ContactEditor, type ContactDraft, type ContactErrors } from "../../components/ContactEditor";
import { Field } from "../../components/Field";
import { SelectField } from "../../components/SelectField";
import { useMountFocus } from "../../components/useMountFocus";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { customerPath } from "./paths";
import { useVoivodeships } from "./useVoivodeships";

type AddressPart = (typeof ADDRESS_PARTS)[number];
// Picked from the checked request type, so a part missing from it fails to compile here.
type AddressInput = Pick<CustomerInput, AddressPart>;
export type AddressDraft = Record<AddressPart, string>;

// What the form holds; create starts from an empty one, edit from the stored record.
export interface CustomerDraft {
  name: string;
  country: string;
  address: AddressDraft;
  contacts: ContactDraft[];
  primaryKey: number | null;
}

// How create and edit answer a save, as the form shows it.
export type FormResult =
  | { kind: "saved"; customer: CustomerRecord }
  | { kind: "rejected"; fields: RejectedField[] }
  | { kind: "refused" }
  | { kind: "notFound" }
  | { kind: "restoreFirst" }
  // Another customer holds the NIP (EKO-3-03); the reference is the answer's, never the session's.
  | { kind: "nipTaken"; existingCustomerId: string | null }
  | { kind: "failed" };

type Outcome =
  | { kind: "editing" }
  | { kind: "saving" }
  | {
      kind: "rejected";
      fields: RejectedField[];
      sent: readonly ContactDraft[];
      // The country the rejected request was judged under, which decides the message.
      sentCountry: string;
    }
  | { kind: "refused" }
  | { kind: "notFound" }
  | { kind: "nipTaken"; existingCustomerId: string | null }
  | { kind: "failed" }
  // The edit was refused until the customer is restored (D-3 F-1 A); the values stay as entered.
  | { kind: "restoreFirst" }
  | { kind: "restoring" }
  | { kind: "restoreFailed" }
  | { kind: "restored" };

export const emptyAddress: AddressDraft = {
  street: "",
  postal_code: "",
  town: "",
  voivodeship: "",
  county: "",
  tax_id: "",
};

const REGION_PARTS: readonly AddressPart[] = ["voivodeship", "county"];

// A part left empty is not sent; voivodeship and county are never sent for another country,
// where the server refuses them on fields the rep cannot see (C-3 A).
function addressInput(draft: AddressDraft, polish: boolean): AddressInput {
  const input: AddressInput = {};
  for (const part of ADDRESS_PARTS) {
    if (draft[part] !== "" && (polish || !REGION_PARTS.includes(part))) {
      input[part] = draft[part];
    }
  }
  return input;
}

function addressError(part: AddressPart, polish: boolean): string {
  switch (part) {
    case "street":
      return messages.customer.streetInvalid;
    case "postal_code":
      return polish ? messages.customer.postalCodeInvalid : messages.customer.foreignPostalCodeInvalid;
    case "town":
      return messages.customer.townInvalid;
    case "voivodeship":
      return messages.customer.voivodeshipInvalid;
    case "county":
      return messages.customer.countyInvalid;
    case "tax_id":
      return polish ? messages.customer.nipInvalid : messages.customer.foreignTaxIdInvalid;
  }
}

const countries = countryOptions().map(({ code, name }) => ({ value: code, label: name }));

function contactErrors(
  fields: readonly RejectedField[],
  sent: readonly ContactDraft[],
): Map<number, ContactErrors> {
  const errors = new Map<number, ContactErrors>();
  for (const field of fields) {
    if (field.field !== "contact") {
      continue;
    }
    const contact = sent[field.index];
    if (contact === undefined) {
      continue;
    }
    const current = errors.get(contact.key) ?? {};
    if (field.part === "note") {
      errors.set(contact.key, { ...current, note: messages.customer.noteInvalid });
    } else if (field.part === "value") {
      const message =
        contact.kind === "email" ? messages.customer.emailInvalid : messages.customer.phoneInvalid;
      errors.set(contact.key, { ...current, value: message });
    } else {
      errors.set(contact.key, { ...current, value: messages.customer.contactInvalid });
    }
  }
  return errors;
}

interface CustomerFormProps {
  title: string;
  intro: string;
  saveLabel: string;
  // What a 403 says: create and edit are refused for different reasons.
  refusedMessage: string;
  initial: CustomerDraft;
  submit: (input: CustomerInput) => Promise<FormResult>;
  onSaved: (customer: CustomerRecord) => void;
  cancel: { kind: "link"; href: string } | { kind: "action"; onCancel: () => void };
  // Offered when a save answers restore-first; true once the server says the customer is active.
  restore?: () => Promise<boolean>;
}

// P2's customer form, shared by create and edit so both map a rejection to the same message.
// Nothing is checked here that the server does not also check: the only local rule is that a name
// is entered at all (EKO-3-01 K-01 holds the rule).
export function CustomerForm({
  title,
  intro,
  saveLabel,
  refusedMessage,
  initial,
  submit,
  onSaved,
  cancel,
  restore,
}: CustomerFormProps) {
  const headingRef = useMountFocus<HTMLHeadingElement>();
  const titleId = useId();
  const inFlight = useRef(false);
  const restoreInFlight = useRef(false);
  const nextKey = useRef(initial.contacts.length);
  const [name, setName] = useState(initial.name);
  const [nameMissing, setNameMissing] = useState(false);
  const [country, setCountry] = useState(initial.country);
  const [address, setAddress] = useState<AddressDraft>(initial.address);
  const [contacts, setContacts] = useState<ContactDraft[]>(initial.contacts);
  const [primaryKey, setPrimaryKey] = useState<number | null>(initial.primaryKey);
  const [outcome, setOutcome] = useState<Outcome>({ kind: "editing" });
  const voivodeships = useVoivodeships();

  const polish = country === POLAND;
  const rejected = outcome.kind === "rejected" ? outcome.fields : [];
  const isRejected = (field: RejectedField["field"]) => rejected.some((r) => r.field === field);
  const nameError = nameMissing
    ? messages.customer.nameRequired
    : isRejected("name")
      ? messages.customer.nameInvalid
      : undefined;
  const fieldError = (part: AddressPart) =>
    outcome.kind === "rejected" && isRejected(part)
      ? addressError(part, outcome.sentCountry === POLAND)
      : undefined;
  // A rejected part whose field this country hides is told in the form alert instead.
  // The answer's reference alone picks the sentence and the link (EKO-3-03), never the session.
  const existingPath =
    outcome.kind === "nipTaken" && outcome.existingCustomerId !== null
      ? customerPath(outcome.existingCustomerId)
      : null;
  const taxIdError =
    outcome.kind !== "nipTaken"
      ? fieldError("tax_id")
      : existingPath === null
        ? messages.customer.nipTaken
        : messages.customer.nipTakenWithReference;
  const hiddenRegionRejected = !polish && REGION_PARTS.some((part) => isRejected(part));
  const saving = outcome.kind === "saving";
  const restoring = outcome.kind === "restoring";
  const offersRestore =
    restore !== undefined &&
    (outcome.kind === "restoreFirst" || restoring || outcome.kind === "restoreFailed");

  const listed = voivodeships.kind === "listed" ? voivodeships.voivodeships : [];
  const voivodeshipOptions = [
    { value: "", label: messages.customer.notSelected },
    ...listed.map((entry) => ({ value: entry.name, label: entry.name })),
  ];
  const counties = listed.find((entry) => entry.name === address.voivodeship)?.counties ?? [];
  const countyOptions =
    address.voivodeship === ""
      ? [{ value: "", label: messages.customer.countyFirst }]
      : [
          { value: "", label: messages.customer.notSelected },
          ...counties.map((county) => ({ value: county, label: county })),
        ];
  const setPart = (part: AddressPart, value: string) => {
    setAddress((current) => ({ ...current, [part]: value }));
  };

  const save = async () => {
    // A double click or a second submit while the first is in flight sends nothing more, and no
    // save goes out while a restore is on its way.
    if (inFlight.current || restoreInFlight.current) {
      return;
    }
    if (name.trim() === "") {
      setNameMissing(true);
      return;
    }
    inFlight.current = true;
    const sent = contacts;
    setOutcome({ kind: "saving" });
    const sentCountry = country;
    const result = await submit({
      name,
      country,
      ...addressInput(address, polish),
      contacts: sent.map((contact) => ({
        kind: contact.kind,
        value: contact.value,
        note: contact.note === "" ? null : contact.note,
        primary: contact.key === primaryKey,
      })),
    });
    if (result.kind === "saved") {
      onSaved(result.customer);
      return;
    }
    inFlight.current = false;
    setOutcome(result.kind === "rejected" ? { ...result, sent, sentCountry } : result);
  };

  // Sends only the restore: the entered values stay, and saving them again is the user's step.
  const restoreFirst = async () => {
    if (restore === undefined || restoreInFlight.current || inFlight.current) {
      return;
    }
    restoreInFlight.current = true;
    setOutcome({ kind: "restoring" });
    const restored = await restore();
    restoreInFlight.current = false;
    setOutcome({ kind: restored ? "restored" : "restoreFailed" });
  };

  const alert =
    outcome.kind === "rejected"
      ? messages.customer.rejected
      : outcome.kind === "refused"
        ? refusedMessage
        : outcome.kind === "notFound"
          ? messages.customer.notFound
          : outcome.kind === "failed"
            ? messages.customer.saveFailed
            : outcome.kind === "restoreFirst" || restoring
              ? messages.customer.restoreFirst
              : outcome.kind === "restoreFailed"
                ? messages.customer.restoreFailed
                : null;

  return (
    <form
      className="customer-form"
      noValidate
      aria-labelledby={titleId}
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <div className="page-heading">
        <h1 id={titleId} ref={headingRef} tabIndex={-1}>
          {title}
        </h1>
        <p>{intro}</p>
      </div>
      {alert === null ? null : (
        <div className="form-alert" role="alert">
          <p>{alert}</p>
          {isRejected("contacts") ? <p>{messages.customer.tooManyContacts}</p> : null}
          {hiddenRegionRejected ? <p>{messages.customer.regionHidden}</p> : null}
          {offersRestore ? (
            <Button
              label={messages.customer.restore}
              variant="primary"
              disabled={restoring}
              aria-busy={restoring}
              onClick={() => {
                void restoreFirst();
              }}
            />
          ) : null}
        </div>
      )}
      {outcome.kind === "restored" ? <p role="status">{messages.customer.restoredResave}</p> : null}
      <fieldset className="form-section" disabled={saving}>
        <Field
          label={messages.customer.name}
          required
          value={name}
          error={nameError}
          onChange={(event) => {
            setName(event.target.value);
            setNameMissing(false);
          }}
        />
        <SelectField
          label={messages.customer.country}
          required
          options={countries}
          value={country}
          error={isRejected("country") ? messages.customer.countryInvalid : undefined}
          onChange={(event) => {
            setCountry(event.target.value);
          }}
        />
        <Field
          label={polish ? messages.customer.nip : messages.customer.foreignTaxId}
          value={address.tax_id}
          error={taxIdError}
          onChange={(event) => {
            setPart("tax_id", event.target.value);
          }}
        />
        {existingPath === null ? null : (
          <p>
            <a
              className="text-link"
              href={existingPath}
              onClick={(event) => {
                followLink(event, existingPath);
              }}
            >
              {messages.customer.openExistingCustomer}
            </a>
          </p>
        )}
      </fieldset>
      <h2>{messages.customer.addressTitle}</h2>
      <fieldset className="form-section" disabled={saving}>
        <Field
          label={messages.customer.street}
          value={address.street}
          error={fieldError("street")}
          onChange={(event) => {
            setPart("street", event.target.value);
          }}
        />
        <div className="form-grid">
          <Field
            label={messages.customer.postalCode}
            value={address.postal_code}
            error={fieldError("postal_code")}
            onChange={(event) => {
              setPart("postal_code", event.target.value);
            }}
          />
          <Field
            label={messages.customer.town}
            value={address.town}
            error={fieldError("town")}
            onChange={(event) => {
              setPart("town", event.target.value);
            }}
          />
        </div>
        {polish ? (
          <>
            <div className="form-grid">
              <SelectField
                label={messages.customer.voivodeship}
                options={voivodeshipOptions}
                value={address.voivodeship}
                disabled={voivodeships.kind !== "listed"}
                error={fieldError("voivodeship")}
                onChange={(event) => {
                  const picked = event.target.value;
                  // A county belongs to one voivodeship, so another voivodeship clears it.
                  setAddress((current) => ({ ...current, voivodeship: picked, county: "" }));
                }}
              />
              <SelectField
                label={messages.customer.county}
                options={countyOptions}
                value={address.county}
                disabled={voivodeships.kind !== "listed" || address.voivodeship === ""}
                error={fieldError("county")}
                onChange={(event) => {
                  setPart("county", event.target.value);
                }}
              />
            </div>
            {voivodeships.kind === "loading" ? (
              <p className="field-hint">{messages.customer.voivodeshipsLoading}</p>
            ) : null}
            {voivodeships.kind === "failed" ? (
              <p className="field-error" role="alert">
                {messages.customer.voivodeshipsFailed}
              </p>
            ) : null}
          </>
        ) : null}
      </fieldset>
      <h2>{messages.customer.contacts}</h2>
      <ContactEditor
        contacts={contacts}
        primaryKey={primaryKey}
        errors={outcome.kind === "rejected" ? contactErrors(rejected, outcome.sent) : new Map()}
        disabled={saving}
        onChange={(changed) => {
          setContacts((current) =>
            current.map((contact) => (contact.key === changed.key ? changed : contact)),
          );
        }}
        onPrimary={setPrimaryKey}
        onAdd={() => {
          const key = nextKey.current;
          nextKey.current += 1;
          setContacts((current) => [...current, { key, kind: "phone", value: "", note: "" }]);
        }}
        onRemove={(key) => {
          setContacts((current) => current.filter((contact) => contact.key !== key));
          setPrimaryKey((current) => (current === key ? null : current));
        }}
      />
      <div className="form-actions">
        {cancel.kind === "link" ? (
          <a
            className="button button-secondary"
            href={cancel.href}
            onClick={(event) => {
              followLink(event, cancel.href);
            }}
          >
            {messages.customer.cancel}
          </a>
        ) : (
          <Button label={messages.customer.cancel} disabled={saving} onClick={cancel.onCancel} />
        )}
        <Button
          type="submit"
          variant="primary"
          label={saveLabel}
          disabled={saving || restoring}
          aria-busy={saving}
        />
      </div>
      {saving ? <p role="status">{messages.customer.saving}</p> : null}
    </form>
  );
}
