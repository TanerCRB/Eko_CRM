import {
  ADDRESS_PARTS,
  editCustomer,
  restoreCustomer,
  type CustomerRecord,
} from "../../api/customers";
import type { ContactDraft } from "../../components/ContactEditor";
import { messages } from "../../i18n/pl";
import { CustomerForm, emptyAddress, type AddressDraft, type CustomerDraft } from "./CustomerForm";

// The stored record as the form's starting values; null when a contact's kind is one the editor
// cannot show, so the form is not offered rather than silently changing that contact.
export function draftOf(customer: CustomerRecord): CustomerDraft | null {
  const address: AddressDraft = { ...emptyAddress };
  for (const part of ADDRESS_PARTS) {
    address[part] = customer[part] ?? "";
  }
  const contacts: ContactDraft[] = [];
  let primaryKey: number | null = null;
  for (const [key, contact] of customer.contacts.entries()) {
    if (contact.kind !== "phone" && contact.kind !== "email") {
      return null;
    }
    contacts.push({ key, kind: contact.kind, value: contact.value, note: contact.note ?? "" });
    if (contact.primary) {
      primaryKey = key;
    }
  }
  return { name: customer.name, country: customer.country, address, contacts, primaryKey };
}

interface EditCustomerProps {
  customer: CustomerRecord;
  draft: CustomerDraft;
  onSaved: (customer: CustomerRecord) => void;
  // The restore offered after a restore-first answer: the screen keeps the server's new record.
  onRestored: (customer: CustomerRecord) => void;
  onCancel: () => void;
}

export function EditCustomer({ customer, draft, onSaved, onRestored, onCancel }: EditCustomerProps) {
  const restore = async () => {
    const result = await restoreCustomer(customer.id);
    if (result.kind !== "changed" || result.customer.archived) {
      return false;
    }
    onRestored(result.customer);
    return true;
  };
  return (
    <CustomerForm
      title={messages.customer.editTitle}
      intro={messages.customer.newIntro}
      saveLabel={messages.customer.saveChanges}
      refusedMessage={messages.customer.editRefused}
      initial={draft}
      submit={(input) => editCustomer(customer.id, input)}
      onSaved={onSaved}
      cancel={{ kind: "action", onCancel }}
      restore={restore}
    />
  );
}
