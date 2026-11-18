import { useId, useRef, useState } from "react";
import { countryOptions, DEFAULT_COUNTRY } from "../../api/countries";
import {
  createCustomer,
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
import { CUSTOMERS_PATH } from "./paths";

type Outcome =
  | { kind: "editing" }
  | { kind: "saving" }
  | { kind: "rejected"; fields: RejectedField[]; sent: readonly ContactDraft[] }
  | { kind: "refused" }
  | { kind: "failed" };

interface NewCustomerProps {
  onCreated: (customer: CustomerRecord) => void;
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

// P2's customer form, the fields this release has. Nothing is checked here that the server does
// not also check: the only local rule is that a name is entered at all (K-01 holds the rule).
export function NewCustomer({ onCreated }: NewCustomerProps) {
  const headingRef = useMountFocus<HTMLHeadingElement>();
  const titleId = useId();
  const inFlight = useRef(false);
  const nextKey = useRef(0);
  const [name, setName] = useState("");
  const [nameMissing, setNameMissing] = useState(false);
  const [country, setCountry] = useState(DEFAULT_COUNTRY);
  const [contacts, setContacts] = useState<ContactDraft[]>([]);
  const [primaryKey, setPrimaryKey] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<Outcome>({ kind: "editing" });

  const rejected = outcome.kind === "rejected" ? outcome.fields : [];
  const isRejected = (field: RejectedField["field"]) => rejected.some((r) => r.field === field);
  const nameError = nameMissing
    ? messages.customer.nameRequired
    : isRejected("name")
      ? messages.customer.nameInvalid
      : undefined;
  const saving = outcome.kind === "saving";

  const submit = async () => {
    // A double click or a second submit while the first is in flight sends nothing more.
    if (inFlight.current) {
      return;
    }
    if (name.trim() === "") {
      setNameMissing(true);
      return;
    }
    inFlight.current = true;
    const sent = contacts;
    setOutcome({ kind: "saving" });
    const result = await createCustomer({
      name,
      country,
      contacts: sent.map((contact) => ({
        kind: contact.kind,
        value: contact.value,
        note: contact.note === "" ? null : contact.note,
        primary: contact.key === primaryKey,
      })),
    });
    if (result.kind === "created") {
      onCreated(result.customer);
      return;
    }
    inFlight.current = false;
    setOutcome(result.kind === "rejected" ? { ...result, sent } : result);
  };

  return (
    <form
      className="customer-form"
      noValidate
      aria-labelledby={titleId}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="page-heading">
        <h1 id={titleId} ref={headingRef} tabIndex={-1}>
          {messages.customer.newTitle}
        </h1>
        <p>{messages.customer.newIntro}</p>
      </div>
      {outcome.kind === "rejected" || outcome.kind === "refused" || outcome.kind === "failed" ? (
        <div className="form-alert" role="alert">
          <p>
            {outcome.kind === "rejected"
              ? messages.customer.rejected
              : outcome.kind === "refused"
                ? messages.customer.refused
                : messages.customer.saveFailed}
          </p>
          {isRejected("contacts") ? <p>{messages.customer.tooManyContacts}</p> : null}
        </div>
      ) : null}
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
        <a
          className="button button-secondary"
          href={CUSTOMERS_PATH}
          onClick={(event) => {
            followLink(event, CUSTOMERS_PATH);
          }}
        >
          {messages.customer.cancel}
        </a>
        <Button
          type="submit"
          variant="primary"
          label={messages.customer.save}
          disabled={saving}
          aria-busy={saving}
        />
      </div>
      {saving ? <p role="status">{messages.customer.saving}</p> : null}
    </form>
  );
}
