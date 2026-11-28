import { useEffect, useId, useRef, useState } from "react";
import { listCustomers, type ListResult } from "../../api/customers";
import { planVisit, type Visit, type VisitInput } from "../../api/visits";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { Field } from "../../components/Field";
import { SelectField } from "../../components/SelectField";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { today } from "../../time/warsaw";
import { NEW_CUSTOMER_PATH } from "../customers/paths";
import { MY_DAY_PATH } from "./paths";

type PlanResult = Awaited<ReturnType<typeof planVisit>>;
type Rejection = Extract<PlanResult, { kind: "rejected" }>["fields"][number];
type CustomersState = { kind: "loading" } | ListResult;

// What the form says after a refused or failed create; the typed values stay as they are.
type Outcome =
  | { kind: "none" }
  | { kind: "rejected"; fields: Rejection[] }
  | { kind: "message"; text: string };

type FieldName =
  | "customer"
  | "startDate"
  | "startTime"
  | "endDate"
  | "endTime"
  | "ownAddress";

// Where each rejection is shown, and with which message. The two DST reasons of ADR-0002-C15 are
// shown at the time of their side, each with its own text.
function placed(rejection: Rejection): { field: FieldName; text: string } | null {
  if (rejection.field === "customer") {
    return { field: "customer", text: messages.visit.customerInvalid };
  }
  if (rejection.field === "ownAddress") {
    return { field: "ownAddress", text: messages.visit.ownAddressInvalid };
  }
  if (rejection.field === "request") {
    return null;
  }
  const side = rejection.field;
  const date: FieldName = side === "start" ? "startDate" : "endDate";
  const time: FieldName = side === "start" ? "startTime" : "endTime";
  if ("part" in rejection) {
    return rejection.part === "date"
      ? { field: date, text: messages.visit.dateInvalid }
      : { field: time, text: messages.visit.timeInvalid };
  }
  switch (rejection.reason) {
    case "nonexistent":
      return { field: time, text: messages.visit.nonexistentTime };
    case "ambiguous":
      return { field: time, text: messages.visit.ambiguousTime };
    case "notAfterStart":
      return { field: time, text: messages.visit.endNotAfterStart };
    case "invalid":
      return { field: date, text: messages.visit.wallTimeInvalid };
  }
}

function fieldErrors(outcome: Outcome): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {};
  if (outcome.kind !== "rejected") {
    return errors;
  }
  for (const rejection of outcome.fields) {
    const place = placed(rejection);
    if (place !== null && errors[place.field] === undefined) {
      errors[place.field] = place.text;
    }
  }
  return errors;
}

function failureText(result: Exclude<PlanResult, { kind: "planned" } | { kind: "rejected" }>) {
  switch (result.kind) {
    case "notFound":
      return messages.visit.customerNotFound;
    case "restoreFirst":
      return messages.visit.restoreFirst;
    case "refused":
      return messages.visit.refused;
    case "failed":
      return messages.visit.saveFailed;
  }
}

function useCustomerChoices(): { state: CustomersState; retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [answer, setAnswer] = useState<{ attempt: number; result: ListResult } | null>(null);
  useEffect(() => {
    let current = true;
    void listCustomers().then((result) => {
      if (current) {
        setAnswer({ attempt, result });
      }
    });
    return () => {
      current = false;
    };
  }, [attempt]);
  return {
    state: answer?.attempt === attempt ? answer.result : { kind: "loading" },
    retry: () => {
      setAttempt((count) => count + 1);
    },
  };
}

interface PlanVisitProps {
  onPlanned: (visit: Visit) => void;
}

// The plan form (K-06): the customer from the server's customer list, the start and end as a
// Europe/Warsaw date and an `HH:MM` time sent exactly as typed (ADR-0001 Constraint 3; no `Date`
// is built from them), and an optional own address. The server judges every value; its 422 is
// shown at the field it names. One create per submit: a second one waits for the first.
export function PlanVisit({ onPlanned }: PlanVisitProps) {
  const titleId = useId();
  const customers = useCustomerChoices();
  const [customerId, setCustomerId] = useState("");
  const [startDate, setStartDate] = useState(() => today());
  const [startTime, setStartTime] = useState("");
  // Until the user edits it, the end date follows the start date.
  const [endDate, setEndDate] = useState<string | null>(null);
  const [endTime, setEndTime] = useState("");
  const [ownAddress, setOwnAddress] = useState("");
  const [outcome, setOutcome] = useState<Outcome>({ kind: "none" });
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);

  const errors = fieldErrors(outcome);

  async function submit() {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setSaving(true);
    const input: VisitInput = {
      customer_id: customerId,
      start: { date: startDate, time: startTime },
      end: { date: endDate ?? startDate, time: endTime },
    };
    if (ownAddress.trim() !== "") {
      input.own_address = ownAddress;
    }
    const result = await planVisit(input);
    inFlight.current = false;
    setSaving(false);
    if (result.kind === "planned") {
      onPlanned(result.visit);
    } else if (result.kind === "rejected") {
      setOutcome({ kind: "rejected", fields: result.fields });
    } else {
      setOutcome({ kind: "message", text: failureText(result) });
    }
  }

  const heading = (
    <div className="page-heading">
      <h1 id={titleId}>{messages.visit.newTitle}</h1>
      <p>{messages.visit.newIntro}</p>
    </div>
  );

  if (customers.state.kind === "loading") {
    return (
      <>
        {heading}
        <p role="status">{messages.visit.customersLoading}</p>
      </>
    );
  }
  if (customers.state.kind !== "listed") {
    return (
      <>
        {heading}
        <div role="alert" className="form-alert">
          <p>{messages.visit.customersFailed}</p>
          <Button label={messages.visit.retry} onClick={customers.retry} />
        </div>
      </>
    );
  }
  if (customers.state.customers.length === 0) {
    return (
      <>
        {heading}
        <EmptyState
          title={messages.visit.noCustomersTitle}
          explanation={messages.visit.noCustomersExplanation}
          action={
            <a
              className="button button-primary"
              href={NEW_CUSTOMER_PATH}
              onClick={(event) => {
                followLink(event, NEW_CUSTOMER_PATH);
              }}
            >
              {messages.visit.addCustomer}
            </a>
          }
        />
      </>
    );
  }

  return (
    <form
      aria-labelledby={titleId}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {heading}
      {outcome.kind === "none" ? null : (
        <p role="alert" className="form-alert">
          {outcome.kind === "rejected" ? messages.visit.rejected : outcome.text}
        </p>
      )}
      <fieldset className="form-section" disabled={saving}>
        <SelectField
          label={messages.visit.customer}
          required
          value={customerId}
          error={errors.customer}
          options={[
            { value: "", label: messages.visit.chooseCustomer },
            ...customers.state.customers.map((customer) => ({
              value: customer.id,
              label: customer.name,
            })),
          ]}
          onChange={(event) => {
            setCustomerId(event.target.value);
          }}
        />
        <div className="form-grid">
          <Field
            type="date"
            label={messages.visit.startDate}
            required
            value={startDate}
            error={errors.startDate}
            onChange={(event) => {
              setStartDate(event.target.value);
            }}
          />
          <Field
            type="time"
            step={60}
            label={messages.visit.startTime}
            required
            value={startTime}
            error={errors.startTime}
            onChange={(event) => {
              setStartTime(event.target.value);
            }}
          />
          <Field
            type="date"
            label={messages.visit.endDate}
            required
            value={endDate ?? startDate}
            error={errors.endDate}
            onChange={(event) => {
              setEndDate(event.target.value);
            }}
          />
          <Field
            type="time"
            step={60}
            label={messages.visit.endTime}
            required
            value={endTime}
            error={errors.endTime}
            onChange={(event) => {
              setEndTime(event.target.value);
            }}
          />
        </div>
        <Field
          label={messages.visit.ownAddress}
          placeholder={messages.visit.ownAddressHint}
          value={ownAddress}
          error={errors.ownAddress}
          onChange={(event) => {
            setOwnAddress(event.target.value);
          }}
        />
      </fieldset>
      <div className="form-actions">
        <a
          className="button button-secondary"
          href={MY_DAY_PATH}
          onClick={(event) => {
            followLink(event, MY_DAY_PATH);
          }}
        >
          {messages.visit.cancel}
        </a>
        <Button
          type="submit"
          variant="primary"
          label={messages.visit.save}
          disabled={saving}
          aria-busy={saving}
        />
      </div>
    </form>
  );
}
