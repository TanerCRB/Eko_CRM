import type { Visit } from "../../api/visits";
import { StatusBadge } from "../../components/StatusBadge";
import { messages } from "../../i18n/pl";
import { formatInstantTime } from "../../time/warsaw";
import "../../styles/visits.css";

// The visit's own address when it has one, else the customer's current address (VIS-3, G-8 A).
export function shownAddress(visit: Visit): string {
  if (visit.own_address !== null) {
    return visit.own_address;
  }
  const { street, postal_code, town } = visit.customer;
  const place = [postal_code, town].filter((part) => part !== null && part !== "").join(" ");
  const parts = [street ?? "", place].filter((part) => part !== "");
  return parts.length === 0 ? messages.visit.noAddress : parts.join(", ");
}

export function timeRange(visit: Visit): string {
  return messages.visit.timeRange(
    formatInstantTime(visit.starts_at),
    formatInstantTime(visit.ends_at),
  );
}

// The P2 AgendaRow: Warsaw times, the customer, the address shown and the server's state.
// `level`: the heading level of the customer name, one below the list's own heading.
export function VisitItem({ visit, level = 3 }: { visit: Visit; level?: 3 | 4 }) {
  const Heading = level === 3 ? "h3" : "h4";
  return (
    <li className={`agenda-row is-${visit.state}`}>
      <p className="agenda-time">{timeRange(visit)}</p>
      <div className="agenda-detail">
        <Heading>{visit.customer.name}</Heading>
        <p>{shownAddress(visit)}</p>
        <StatusBadge state={visit.state} />
      </div>
    </li>
  );
}
