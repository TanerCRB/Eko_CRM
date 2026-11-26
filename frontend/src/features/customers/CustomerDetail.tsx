import { useEffect, useRef, useState } from "react";
import { countryName, POLAND } from "../../api/countries";
import {
  archiveCustomer,
  readCustomer,
  restoreCustomer,
  type CustomerRecord,
  type ReadResult,
} from "../../api/customers";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { CustomerSheet, type SheetDetail } from "../../components/CustomerSheet";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import type { CustomerDraft } from "./CustomerForm";
import { draftOf, EditCustomer } from "./EditCustomer";
import { CUSTOMERS_PATH } from "./paths";

type DetailState = { kind: "loading" } | ReadResult;

type Change = "archive" | "restore";

// What the last action on this screen came to: a success is a status, a failure an alert.
type Notice = { kind: "status" | "alert"; text: string };

interface CustomerDetailProps {
  id: string;
  // The create answer for this id, so the screen after saving shows the server's record without a
  // second request; null means read it.
  created: CustomerRecord | null;
}

// The stored address and tax ID as the server returned them; voivodeship and county exist only
// for Poland, and the tax ID is named a NIP there.
function addressDetails(customer: CustomerRecord): SheetDetail[] {
  const shown = (value: string | null | undefined) => value ?? messages.customer.notGiven;
  const polish = customer.country === POLAND;
  const details: SheetDetail[] = [
    { label: messages.customer.street, value: shown(customer.street) },
    { label: messages.customer.postalCode, value: shown(customer.postal_code) },
    { label: messages.customer.town, value: shown(customer.town) },
  ];
  if (polish) {
    details.push(
      { label: messages.customer.voivodeship, value: shown(customer.voivodeship) },
      { label: messages.customer.county, value: shown(customer.county) },
    );
  }
  details.push({
    label: polish ? messages.customer.nip : messages.customer.foreignTaxId,
    value: shown(customer.tax_id),
  });
  return details;
}

// Mounted with `key={id}`, so another customer starts from a fresh state.
export function CustomerDetail({ id, created }: CustomerDetailProps) {
  const [state, setState] = useState<DetailState>(() =>
    created === null ? { kind: "loading" } : { kind: "found", customer: created },
  );
  const needsRead = created === null;
  // The values the edit form started from, held while it is open; null when it is not.
  const [editing, setEditing] = useState<CustomerDraft | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const [pending, setPending] = useState<Change | null>(null);
  const changeInFlight = useRef(false);

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

  // One archive or restore at a time; the state shown is the one the server answered.
  const change = async (which: Change) => {
    if (changeInFlight.current) {
      return;
    }
    changeInFlight.current = true;
    setNotice(null);
    setPending(which);
    const result = await (which === "archive" ? archiveCustomer(id) : restoreCustomer(id));
    changeInFlight.current = false;
    setPending(null);
    if (result.kind === "changed" && result.customer.archived === (which === "archive")) {
      setState({ kind: "found", customer: result.customer });
      const text =
        which === "archive" ? messages.customer.archivedNotice : messages.customer.restoredNotice;
      setNotice({ kind: "status", text });
      return;
    }
    const text =
      which === "archive" ? messages.customer.archiveFailed : messages.customer.restoreFailed;
    setNotice({ kind: "alert", text });
  };

  const draft = state.kind === "found" ? draftOf(state.customer) : null;

  if (state.kind === "found" && editing !== null) {
    return (
      <EditCustomer
        customer={state.customer}
        draft={editing}
        onSaved={(customer) => {
          setState({ kind: "found", customer });
          setEditing(null);
          setNotice({ kind: "status", text: messages.customer.saved });
        }}
        onRestored={(customer) => {
          setState({ kind: "found", customer });
        }}
        onCancel={() => {
          setEditing(null);
        }}
      />
    );
  }

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
        <>
          <CustomerSheet
            customer={state.customer}
            countryLabel={countryName(state.customer.country)}
            details={addressDetails(state.customer)}
            status={state.customer.archived ? messages.customer.archived : messages.customer.active}
          />
          {notice === null ? null : <p role={notice.kind}>{notice.text}</p>}
          <div className="form-actions">
            {draft === null ? null : (
              <Button
                label={messages.customer.edit}
                disabled={pending !== null}
                onClick={() => {
                  setNotice(null);
                  setEditing(draft);
                }}
              />
            )}
            {state.customer.archived ? (
              <Button
                label={messages.customer.restore}
                variant="primary"
                disabled={pending !== null}
                aria-busy={pending === "restore"}
                onClick={() => {
                  void change("restore");
                }}
              />
            ) : (
              <Button
                label={messages.customer.archive}
                variant="danger"
                disabled={pending !== null}
                aria-busy={pending === "archive"}
                onClick={() => {
                  setNotice(null);
                  setConfirmingArchive(true);
                }}
              />
            )}
          </div>
          {confirmingArchive ? (
            <ConfirmDialog
              open
              title={messages.customer.archiveTitle}
              consequence={messages.customer.archiveConsequence}
              confirmLabel={messages.customer.archive}
              cancelLabel={messages.customer.back}
              onConfirm={() => {
                setConfirmingArchive(false);
                void change("archive");
              }}
              onCancel={() => {
                setConfirmingArchive(false);
              }}
            />
          ) : null}
        </>
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
