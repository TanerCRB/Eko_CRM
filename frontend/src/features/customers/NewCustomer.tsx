import { DEFAULT_COUNTRY } from "../../api/countries";
import { createCustomer, type CustomerInput, type CustomerRecord } from "../../api/customers";
import { messages } from "../../i18n/pl";
import { CustomerForm, emptyAddress, type CustomerDraft, type FormResult } from "./CustomerForm";
import { CUSTOMERS_PATH } from "./paths";

interface NewCustomerProps {
  onCreated: (customer: CustomerRecord) => void;
}

const emptyDraft: CustomerDraft = {
  name: "",
  country: DEFAULT_COUNTRY,
  address: emptyAddress,
  contacts: [],
  primaryKey: null,
};

async function create(input: CustomerInput): Promise<FormResult> {
  const result = await createCustomer(input);
  return result.kind === "created" ? { kind: "saved", customer: result.customer } : result;
}

export function NewCustomer({ onCreated }: NewCustomerProps) {
  return (
    <CustomerForm
      title={messages.customer.newTitle}
      intro={messages.customer.newIntro}
      saveLabel={messages.customer.save}
      refusedMessage={messages.customer.refused}
      initial={emptyDraft}
      submit={create}
      onSaved={onCreated}
      cancel={{ kind: "link", href: CUSTOMERS_PATH }}
    />
  );
}
