import { useId, useState } from "react";
import type { Visit } from "../../api/visits";
import { DateStrip } from "../../components/DateStrip";
import { EmptyState } from "../../components/EmptyState";
import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { useWarsawToday } from "../../time/useWarsawToday";
import {
  dayOfMonth,
  formatDate,
  formatInstant,
  formatShortWeekday,
  formatWeekday,
  nextDays,
  warsawDateOf,
} from "../../time/warsaw";
import { LoadFailed } from "./LoadFailed";
import { VISITS_PATH } from "./paths";
import { PlanLink } from "./PlanLink";
import { useVisits } from "./useVisits";
import { shownAddress, timeRange, VisitItem } from "./VisitItem";

const STRIP_DAYS = 5;

interface MyDayProps {
  // The visit the plan form just created, in memory only: it is announced and its day selected.
  planned: Visit | null;
}

function dayLabel(date: string): string {
  return messages.visit.dayLabel(formatWeekday(date), formatDate(date));
}

function NextVisit({ visit }: { visit: Visit }) {
  const labelId = useId();
  return (
    <article className="next-visit" aria-labelledby={labelId}>
      <p id={labelId} className="next-label">
        {messages.visit.next}
      </p>
      <h3>{visit.customer.name}</h3>
      <p className="next-time">{timeRange(visit)}</p>
      <p className="address">{shownAddress(visit)}</p>
    </article>
  );
}

// My day (K-06): today and the next four Warsaw dates with their counts, the next visit of today
// as the server answers its state, and the selected day's agenda. "Today" comes from warsaw.ts and
// rolls over at Warsaw midnight; the selected day lives in memory, never in the location.
export function MyDay({ planned }: MyDayProps) {
  const today = useWarsawToday();
  const days = nextDays(today, STRIP_DAYS);
  const [chosen, setChosen] = useState<string | null>(() =>
    planned === null ? null : warsawDateOf(planned.starts_at),
  );
  // A chosen day that has left the strip (after midnight) falls back to today.
  const selected = chosen !== null && days.includes(chosen) ? chosen : today;
  const strip = useVisits({ first: today, last: days[days.length - 1] ?? today });
  const day = useVisits({ first: selected, last: selected });
  const sectionId = useId();

  const counts = new Map<string, number>();
  if (strip.state.kind === "listed") {
    for (const visit of strip.state.visits) {
      const date = warsawDateOf(visit.starts_at);
      counts.set(date, (counts.get(date) ?? 0) + 1);
    }
  }

  const isToday = selected === today;
  const visits = day.state.kind === "listed" ? day.state.visits : [];
  const next = isToday ? visits.find((visit) => visit.state === "planned") : undefined;
  const agenda = visits.filter((visit) => visit !== next);

  return (
    <>
      <div className="page-heading">
        <h1>{messages.myDay}</h1>
        <p>{dayLabel(selected)}</p>
      </div>
      <p>
        <PlanLink />
      </p>
      {planned === null ? null : (
        <p role="status" className="notice">
          {messages.visit.plannedNotice(planned.customer.name, formatInstant(planned.starts_at))}
        </p>
      )}
      <DateStrip
        label={messages.visit.chooseDay}
        selected={selected}
        onSelect={setChosen}
        days={days.map((date) => ({
          date,
          label: dayLabel(date),
          weekday: formatShortWeekday(date),
          dayOfMonth: dayOfMonth(date),
          count: strip.state.kind === "listed" ? messages.visit.count(counts.get(date) ?? 0) : null,
        }))}
      />
      {strip.state.kind === "failed" ? (
        <p role="alert" className="form-alert">
          {messages.visit.countsFailed}
        </p>
      ) : null}
      <section aria-labelledby={sectionId}>
        <h2 id={sectionId}>{isToday ? messages.visit.todayVisits : messages.visit.dayVisits}</h2>
        {day.state.kind === "loading" ? <p role="status">{messages.loading}</p> : null}
        {day.state.kind === "failed" ? (
          <LoadFailed
            onRetry={() => {
              day.retry();
              strip.retry();
            }}
          />
        ) : null}
        {day.state.kind === "listed" && visits.length === 0 ? (
          <EmptyState
            title={messages.visit.emptyTitle}
            explanation={messages.visit.emptyExplanation}
            action={<PlanLink />}
          />
        ) : null}
        {next === undefined ? null : <NextVisit visit={next} />}
        {agenda.length === 0 ? null : (
          <ol className="agenda" aria-label={messages.visit.agenda}>
            {agenda.map((visit) => (
              <VisitItem key={visit.id} visit={visit} />
            ))}
          </ol>
        )}
        <p className="eyeline">{messages.visit.heldAutomatically}</p>
        <a
          className="text-link"
          href={VISITS_PATH}
          onClick={(event) => {
            followLink(event, VISITS_PATH);
          }}
        >
          {messages.visit.showWeek}
        </a>
      </section>
    </>
  );
}
