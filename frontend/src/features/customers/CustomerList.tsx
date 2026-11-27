import { useEffect, useMemo, useRef, useState } from "react";
import { countryName } from "../../api/countries";
import { listCustomers, type CustomerListQuery, type ListResult } from "../../api/customers";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { holdsManager, useSession } from "../session/sessionContext";
import { ownerOptions } from "./ownerOptions";
import { customerPath, NEW_CUSTOMER_PATH } from "./paths";
import { useReps } from "./useReps";

type StateFilter = NonNullable<CustomerListQuery["state"]>;

// The answer remembers the term, owner and state it was asked for, so the empty state speaks of
// those and not of whatever the controls hold while the next answer is on its way.
// `archivedInScope` keeps only whether the archived answer held anything, never its items (K-06).
type ListState =
  | { kind: "loading" }
  | (ListResult & {
      term: string;
      owner: string;
      filter: StateFilter | undefined;
      archivedInScope: boolean;
    });

// `owner` is a rep's subject, "" for every owner the caller may see; `filter` is undefined until
// the user picks a state, and is then sent as picked.
interface ListRequest {
  term: string;
  owner: string;
  filter: StateFilter | undefined;
  attempt: number;
}

const STATE_FILTERS: readonly { value: StateFilter; label: string }[] = [
  { value: "active", label: messages.customer.activeFilter },
  { value: "archived", label: messages.customer.archivedFilter },
  { value: "both", label: messages.customer.bothFilter },
];

// Typing pauses this long before the term is sent; Enter sends it at once.
const SEARCH_DELAY_MS = 300;
// The server's bound after trimming (G-6 A); the field cuts a longer term instead of a 422.
const SEARCH_MAX_LENGTH = 254;

// The plain list (C-2 A), its search and a manager's owner selector (EKO-3-08): what the server
// answered, in its order; the SPA filters nothing, and the term and owner stay in this component's
// memory, never in the location (ADR-0005-C13). The selector is a convenience: the server decides
// whose customers a caller sees.
export function CustomerList() {
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [input, setInput] = useState("");
  const [request, setRequest] = useState<ListRequest>({
    term: "",
    owner: "",
    filter: undefined,
    attempt: 0,
  });
  const reps = useReps(holdsManager(useSession()));
  const options = useMemo(() => (reps === null ? null : ownerOptions(reps)), [reps]);
  const pending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Read by the delayed search too, whose closure may predate the last request.
  const requested = useRef("");

  useEffect(() => {
    let current = true;
    const query: CustomerListQuery = { q: request.term, owner: request.owner };
    if (request.filter !== undefined) {
      query.state = request.filter;
    }
    const asked = { term: request.term, owner: request.owner, filter: request.filter };
    const isDefault =
      request.term === "" && request.owner === "" && (request.filter ?? "active") === "active";
    void listCustomers(query).then((result) => {
      // An answer to a request since replaced is dropped, so a late older answer never wins.
      if (!current) {
        return;
      }
      if (!isDefault || result.kind !== "listed" || result.customers.length > 0) {
        setState({ ...result, ...asked, archivedInScope: false });
        return;
      }
      // EKO-3-10 G-1 B: the first-customer text needs the server's word that nothing is archived
      // in the caller's scope; until then the screen stays loading, and a failure is a failure.
      void listCustomers({ state: "archived" }).then((archived) => {
        if (current) {
          setState(
            archived.kind === "listed"
              ? { ...result, ...asked, archivedInScope: archived.customers.length > 0 }
              : { kind: "failed", ...asked, archivedInScope: false },
          );
        }
      });
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
    setRequest((current) => ({ ...current, term, attempt: 0 }));
  }

  function chooseOwner(owner: string) {
    setState({ kind: "loading" });
    setRequest((current) => ({ ...current, owner, attempt: 0 }));
  }

  function chooseState(filter: StateFilter) {
    if (filter === (request.filter ?? "active")) {
      return;
    }
    setState({ kind: "loading" });
    setRequest((current) => ({ ...current, filter, attempt: 0 }));
  }

  const shownFilter = request.filter ?? "active";

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
        <div className="segments" role="group" aria-label={messages.customer.stateFilter}>
          {STATE_FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={shownFilter === option.value ? "active" : undefined}
              aria-pressed={shownFilter === option.value}
              onClick={() => {
                chooseState(option.value);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        {options === null ? null : (
          <label>
            <span className="sr-only">{messages.customer.owner}</span>
            <select
              value={request.owner}
              onChange={(event) => {
                chooseOwner(event.target.value);
              }}
            >
              <option value="">{messages.customer.allOwners}</option>
              {options.map((option) => (
                <option key={option.subject} value={option.subject}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        )}
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
        state.term === "" && state.owner === "" && (state.filter ?? "active") === "active" ? (
          state.archivedInScope ? (
            <EmptyState
              title={messages.customer.noActiveTitle}
              explanation={messages.customer.noActiveExplanation}
            />
          ) : (
            <EmptyState
              title={messages.customer.emptyTitle}
              explanation={messages.customer.emptyExplanation}
            />
          )
        ) : (
          <EmptyState
            title={messages.customer.noMatchTitle}
            explanation={
              state.term === "" && (state.filter ?? "active") !== "active"
                ? messages.customer.noMatchStateExplanation
                : messages.customer.noMatchExplanation
            }
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
              {customer.archived ? (
                <span className="customer-archived-mark">{messages.customer.archivedMark}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
