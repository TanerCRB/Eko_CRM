import { useId, useState } from "react";
import type { Visit } from "../../api/visits";
import { EmptyState } from "../../components/EmptyState";
import { messages } from "../../i18n/pl";
import { useWarsawToday } from "../../time/useWarsawToday";
import {
  formatDate,
  formatDayMonth,
  formatWeekday,
  nextDays,
  warsawDateOf,
  weekOf,
} from "../../time/warsaw";
import { LoadFailed } from "./LoadFailed";
import { PlanLink } from "./PlanLink";
import { useVisits } from "./useVisits";
import { VisitItem } from "./VisitItem";

type Layout = "week" | "all";

const LAYOUTS: readonly { value: Layout; label: string }[] = [
  { value: "week", label: messages.visit.week },
  { value: "all", label: messages.visit.all },
];

// Visits already in start order, by the Warsaw date of each start; dates ascend with them.
function byWarsawDay(visits: readonly Visit[]): Map<string, Visit[]> {
  const days = new Map<string, Visit[]>();
  for (const visit of visits) {
    const date = warsawDateOf(visit.starts_at);
    const day = days.get(date);
    if (day === undefined) {
      days.set(date, [visit]);
    } else {
      day.push(visit);
    }
  }
  return days;
}

interface DayProps {
  heading: string;
  visits: readonly Visit[];
  today: boolean;
}

function Day({ heading, visits, today }: DayProps) {
  const headingId = useId();
  return (
    <section
      className={today ? "week-column today" : "week-column"}
      aria-labelledby={headingId}
    >
      <h3 id={headingId}>{heading}</h3>
      {today ? <small className="eyeline">{messages.visit.today}</small> : null}
      {visits.length === 0 ? (
        <p className="eyeline">{messages.visit.noVisitsThatDay}</p>
      ) : (
        <ol className="agenda">
          {visits.map((visit) => (
            <VisitItem key={visit.id} visit={visit} level={4} />
          ))}
        </ol>
      )}
    </section>
  );
}

function Week({ today }: { today: string }) {
  const week = weekOf(today);
  const { state, retry } = useVisits(week);
  const days = state.kind === "listed" ? byWarsawDay(state.visits) : new Map<string, Visit[]>();
  return (
    <>
      <p>
        <strong>
          {messages.visit.weekRange(formatDate(week.first), formatDate(week.last))}
        </strong>
      </p>
      <div className="board-scroll" role="region" aria-label={messages.visit.weekBoard}>
        {state.kind === "loading" ? <p role="status">{messages.loading}</p> : null}
        {state.kind === "failed" ? <LoadFailed onRetry={retry} /> : null}
        {state.kind === "listed" ? (
          <div className="week-board">
            {nextDays(week.first, 7).map((date) => (
              <Day
                key={date}
                heading={messages.visit.dayLabel(formatWeekday(date), formatDayMonth(date))}
                visits={days.get(date) ?? []}
                today={date === today}
              />
            ))}
          </div>
        ) : null}
      </div>
    </>
  );
}

function AllVisits({ today }: { today: string }) {
  const { state, retry } = useVisits(null);
  return (
    <section role="region" aria-label={messages.visit.all}>
      {state.kind === "loading" ? <p role="status">{messages.loading}</p> : null}
      {state.kind === "failed" ? <LoadFailed onRetry={retry} /> : null}
      {state.kind === "listed" && state.visits.length === 0 ? (
        <EmptyState
          title={messages.visit.noVisitsTitle}
          explanation={messages.visit.noVisitsExplanation}
          action={<PlanLink />}
        />
      ) : null}
      {state.kind === "listed"
        ? [...byWarsawDay(state.visits)].map(([date, visits]) => (
            <div key={date} className="day-group">
              <Day
                heading={messages.visit.dayLabel(formatWeekday(date), formatDate(date))}
                visits={visits}
                today={date === today}
              />
            </div>
          ))
        : null}
    </section>
  );
}

// The Visits list (K-06): the Monday-to-Sunday Warsaw week holding today (ADR-0001-C14), or every
// visit the server answers, grouped by Warsaw day. The layout lives in memory only.
export function VisitSchedule() {
  const today = useWarsawToday();
  const [layout, setLayout] = useState<Layout>("week");
  return (
    <>
      <div className="page-heading">
        <h1>{messages.visits}</h1>
        <p>{messages.visit.listIntro}</p>
      </div>
      <div className="toolbar">
        <PlanLink />
        <div className="segments" role="group" aria-label={messages.visit.layout}>
          {LAYOUTS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={layout === option.value ? "active" : undefined}
              aria-pressed={layout === option.value}
              onClick={() => {
                setLayout(option.value);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      {layout === "week" ? <Week today={today} /> : <AllVisits today={today} />}
    </>
  );
}
