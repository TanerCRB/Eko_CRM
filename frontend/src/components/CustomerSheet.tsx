import { useId } from "react";
import { messages } from "../i18n/pl";
import { useMountFocus } from "./useMountFocus";
import "../styles/components.css";

export interface SheetContact {
  kind: string;
  value: string;
  note: string | null;
  primary: boolean;
}

export interface SheetDetail {
  label: string;
  value: string;
}

interface CustomerSheetProps {
  // Always the record the server returned, never the form's values (K-07).
  customer: { name: string; contacts: readonly SheetContact[] };
  // The country as display text, resolved by the feature from the record's code.
  countryLabel: string;
  // Further labelled values shown after the country, in order; each label appears once.
  details?: readonly SheetDetail[];
}

function kindLabel(kind: string): string {
  if (kind === "phone") {
    return messages.customer.phone;
  }
  return kind === "email" ? messages.customer.email : kind;
}

// P2 CustomerSheet, the part this release has: name, country, the details the feature passes
// (address and tax ID) and contacts. Every value is a text child, so markup in it is shown, never
// interpreted.
export function CustomerSheet({ customer, countryLabel, details = [] }: CustomerSheetProps) {
  const headingRef = useMountFocus<HTMLHeadingElement>();
  const contactsId = useId();

  return (
    <article className="customer-sheet">
      <div className="page-heading">
        <h1 ref={headingRef} tabIndex={-1}>
          {customer.name}
        </h1>
      </div>
      <dl className="detail-grid">
        <div>
          <dt>{messages.customer.country}</dt>
          <dd>{countryLabel}</dd>
        </div>
        {details.map((detail) => (
          <div key={detail.label}>
            <dt>{detail.label}</dt>
            <dd>{detail.value}</dd>
          </div>
        ))}
      </dl>
      <h2 id={contactsId}>{messages.customer.contactsTitle}</h2>
      {customer.contacts.length === 0 ? (
        <p className="muted">{messages.customer.noContacts}</p>
      ) : (
        <ul className="contact-list" aria-labelledby={contactsId}>
          {customer.contacts.map((contact, position) => (
            // The answer gives a contact no identity of its own; the list is read-only, in stored order.
            <li key={position} className="contact-line">
              <strong>{contact.value}</strong>
              <small>{kindLabel(contact.kind)}</small>
              {contact.note === null ? null : <span className="contact-note">{contact.note}</span>}
              {contact.primary ? (
                <span className="contact-primary-mark">{messages.customer.primary}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
