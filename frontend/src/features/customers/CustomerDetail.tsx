import { useEffect, useState } from "react";
import { countryName } from "../../api/countries";
import { readCustomer, type CustomerRecord, type ReadResult } from "../../api/customers";
import { CustomerSheet } from "../../components/CustomerSheet";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { CUSTOMERS_PATH } from "./paths";

type DetailState = { kind: "loading" } | ReadResult;

interface CustomerDetailProps {
  id: string;
  // The create answer for this id, so the screen after saving shows the server's record without a
  // second request; null means read it.
  created: CustomerRecord | null;
}

// Mounted with `key={id}`, so another customer starts from a fresh state.
export function CustomerDetail({ id, created }: CustomerDetailProps) {
  const [state, setState] = useState<DetailState>(() =>
    created === null ? { kind: "loading" } : { kind: "found", customer: created },
  );
  const needsRead = created === null;

  useEffect(() => {
    if (!needsRead) {
      return;
    }
    let current = true;
    void readCustomer(id).then((result) => {
      if (current) {
        setState(result);
      }
    });
    return () => {
      current = false;
    };
  }, [id, needsRead]);

  return (
    <>
      <p>
        <a
          className="text-link"
          href={CUSTOMERS_PATH}
          onClick={(event) => {
            followLink(event, CUSTOMERS_PATH);
          }}
        >
          {messages.customer.backToList}
        </a>
      </p>
      {state.kind === "found" ? (
        <CustomerSheet
          customer={state.customer}
          countryLabel={countryName(state.customer.country)}
        />
      ) : (
        <div className="page-heading">
          <h1>{messages.customers}</h1>
        </div>
      )}
      {state.kind === "loading" ? <p role="status">{messages.loading}</p> : null}
      {state.kind === "notFound" ? <p role="alert">{messages.customer.notFound}</p> : null}
      {state.kind === "failed" ? <p role="alert">{messages.customer.readFailed}</p> : null}
    </>
  );
}
