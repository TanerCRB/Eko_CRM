import { useId } from "react";
import { messages } from "../i18n/pl";
import { Button } from "./Button";
import { Field } from "./Field";
import { SelectField } from "./SelectField";
import "../styles/components.css";

// The editor's own kinds; the feature builds the request from them, so the compiler checks they
// fit the contract's.
export type ContactDraftKind = "phone" | "email";

export interface ContactDraft {
  // Stable row identity for React keys and the primary choice; never sent to the API.
  key: number;
  kind: ContactDraftKind;
  value: string;
  note: string;
}

export interface ContactErrors {
  value?: string;
  note?: string;
}

interface ContactEditorProps {
  contacts: readonly ContactDraft[];
  // One key, not a flag per row: marking a contact primary clears the previous one (P2 HANDOFF).
  primaryKey: number | null;
  errors: ReadonlyMap<number, ContactErrors>;
  disabled: boolean;
  onChange: (contact: ContactDraft) => void;
  onPrimary: (key: number) => void;
  onAdd: () => void;
  onRemove: (key: number) => void;
}

const kindOptions = [
  { value: "phone", label: messages.customer.phone },
  { value: "email", label: messages.customer.email },
] as const;

function isContactKind(value: string): value is ContactDraftKind {
  return value === "phone" || value === "email";
}

// P2 ContactEditor: repeatable phone and e-mail entries, each with an optional note; one primary.
export function ContactEditor({
  contacts,
  primaryKey,
  errors,
  disabled,
  onChange,
  onPrimary,
  onAdd,
  onRemove,
}: ContactEditorProps) {
  const group = useId();

  return (
    <div className="contact-editor">
      {contacts.map((contact, position) => {
        const rowErrors = errors.get(contact.key);
        return (
          <fieldset key={contact.key} className="contact-edit" disabled={disabled}>
            <legend className="sr-only">{messages.customer.contactGroup(position + 1)}</legend>
            <div className="form-grid">
              <SelectField
                label={messages.customer.contactKind}
                options={kindOptions}
                value={contact.kind}
                onChange={(event) => {
                  const kind = event.target.value;
                  if (isContactKind(kind)) {
                    onChange({ ...contact, kind });
                  }
                }}
              />
              <Field
                label={messages.customer.contactValue}
                inputMode={contact.kind === "email" ? "email" : "tel"}
                value={contact.value}
                error={rowErrors?.value}
                onChange={(event) => {
                  onChange({ ...contact, value: event.target.value });
                }}
              />
            </div>
            <Field
              label={messages.customer.contactNote}
              value={contact.note}
              placeholder={messages.customer.contactNoteHint}
              error={rowErrors?.note}
              onChange={(event) => {
                onChange({ ...contact, note: event.target.value });
              }}
            />
            <div className="contact-edit-actions">
              <label className="contact-primary">
                <input
                  type="radio"
                  name={group}
                  checked={primaryKey === contact.key}
                  onChange={() => {
                    onPrimary(contact.key);
                  }}
                />
                {messages.customer.primary}
              </label>
              <Button
                label={messages.customer.removeContact}
                variant="ghost"
                onClick={() => {
                  onRemove(contact.key);
                }}
              />
            </div>
          </fieldset>
        );
      })}
      <Button label={messages.customer.addContact} disabled={disabled} onClick={onAdd} />
      <p className="field-hint">{messages.customer.phoneHint}</p>
    </div>
  );
}
