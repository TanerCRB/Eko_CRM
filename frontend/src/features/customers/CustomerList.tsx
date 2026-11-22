import { useEffect, useRef, useState } from "react";
import { countryName } from "../../api/countries";
import { listCustomers, type ListResult } from "../../api/customers";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { customerPath, NEW_CUSTOMER_PATH } from "./paths";

// The answer remembers the term it was asked for, so the empty state speaks of that term and not
// of whatever the field holds while the next answer is on its way.
type ListState = { kind: "loading" } | (ListResult & { term: string });

interface ListRequest {
  term: string;
  attempt: number;
}

// Typing pauses this long before the term is sent; Enter sends it at once.
const SEARCH_DELAY_MS = 300;
// The server's bound after trimming (G-6 A); the field cuts a longer term instead of a 422.
const SEARCH_MAX_LENGTH = 254;

// The plain list (C-2 A) and its search: what the server answered, in its order; the SPA filters
// nothing, and the term stays in this component's memory, never in the location (ADR-0005-C13).
export function CustomerList() {
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [input, setInput] = useState("");
  const [request, setRequest] = useState<ListRequest>({ term: "", attempt: 0 });
  const pending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Read by the delayed search too, whose closure may predate the last request.
  const requested = useRef("");

  useEffect(() => {
    let current = true;
    void listCustomers({ q: request.term }).then((result) => {
      // An answer to a request since replaced is dropped, so a late older answer never wins.
      if (current) {
        setState({ ...result, term: request.term });
      }
    });
    return () => {
      current = false;
    };
  }, [request]);

  useEffect(
    () => () => {
      clearTimeout(pending.current);
    },
    [],
  );

  function search(value: string) {
    clearTimeout(pending.current);
    const term = value.trim();
    if (term === requested.current) {
      return;
    }
    requested.current = term;
    setState({ kind: "loading" });
    setRequest({ term, attempt: 0 });
  }

  const rejected = state.kind === "rejected";

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
      <form
        role="search"
        className="toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          search(input);
        }}
      >
        <label className="search-field">
          <svg
            className="icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="m16 16 5 5" />
          </svg>
          <span className="sr-only">{messages.customer.search}</span>
          <input
            type="search"
            value={input}
            maxLength={SEARCH_MAX_LENGTH}
            placeholder={messages.customer.searchPlaceholder}
            aria-invalid={rejected ? true : undefined}
            aria-describedby={rejected ? "customer-search-error" : undefined}
            onChange={(event) => {
              const value = event.target.value;
              setInput(value);
              clearTimeout(pending.current);
              pending.current = setTimeout(() => {
                search(value);
              }, SEARCH_DELAY_MS);
            }}
          />
        </label>
        {rejected ? (
          <small id="customer-search-error" className="field-error" role="alert">
            {messages.customer.searchRejected}
          </small>
        ) : null}
      </form>
      {state.kind === "loading" ? <p role="status">{messages.loading}</p> : null}
      {state.kind === "failed" ? (
        <div className="form-alert" role="alert">
          <p>{messages.customer.listFailed}</p>
          <Button
            label={messages.customer.retry}
            onClick={() => {
              setState({ kind: "loading" });
              setRequest((current) => ({ ...current, attempt: current.attempt + 1 }));
            }}
          />
        </div>
      ) : null}
      {state.kind === "listed" && state.customers.length === 0 ? (
        state.term === "" ? (
          <EmptyState
            title={messages.customer.emptyTitle}
            explanation={messages.customer.emptyExplanation}
          />
        ) : (
          <EmptyState
            title={messages.customer.noMatchTitle}
            explanation={messages.customer.noMatchExplanation}
          />
        )
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
