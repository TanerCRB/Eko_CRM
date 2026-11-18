import { useEffect, useState } from "react";
import { countryName } from "../../api/countries";
import { listCustomers, type ListResult } from "../../api/customers";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { customerPath, NEW_CUSTOMER_PATH } from "./paths";

type ListState = { kind: "loading" } | ListResult;

// The plain list (C-2 A): what the server answered, in its order; the SPA filters nothing.
export function CustomerList() {
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    void listCustomers().then((result) => {
      if (current) {
        setState(result);
      }
    });
    return () => {
      current = false;
    };
  }, [attempt]);

  return (
    <>
      <div className="page-heading">
        <h1>{messages.customers}</h1>
        <p>{messages.customer.listIntro}</p>
      </div>
      <p>
        <a
          className="button button-primary"
          href={NEW_CUSTOMER_PATH}
          onClick={(event) => {
            followLink(event, NEW_CUSTOMER_PATH);
          }}
        >
          {messages.customer.add}
        </a>
      </p>
      {state.kind === "loading" ? <p role="status">{messages.loading}</p> : null}
      {state.kind === "failed" ? (
        <div className="form-alert" role="alert">
          <p>{messages.customer.listFailed}</p>
          <Button
            label={messages.customer.retry}
            onClick={() => {
              setState({ kind: "loading" });
              setAttempt((count) => count + 1);
            }}
          />
        </div>
      ) : null}
      {state.kind === "listed" && state.customers.length === 0 ? (
        <EmptyState
          title={messages.customer.emptyTitle}
          explanation={messages.customer.emptyExplanation}
        />
      ) : null}
      {state.kind === "listed" && state.customers.length > 0 ? (
        <ul className="customer-list" aria-label={messages.customer.list}>
          {state.customers.map((customer) => (
            <li key={customer.id} className="customer-line">
              <a
                className="customer-link"
                href={customerPath(customer.id)}
                onClick={(event) => {
                  followLink(event, customerPath(customer.id));
                }}
              >
                {customer.name}
              </a>
              <small>{countryName(customer.country)}</small>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
