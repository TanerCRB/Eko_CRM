import { useId } from "react";
import "../styles/visits.css";

export interface StripDay {
  date: string;
  // The day as a screen reader names it, e.g. "niedziela, 25 października 2026".
  label: string;
  weekday: string;
  dayOfMonth: string;
  // `null` while the count is unknown (loading or failed): no number is shown then.
  count: string | null;
}

interface DateStripProps {
  label: string;
  days: readonly StripDay[];
  selected: string;
  onSelect: (date: string) => void;
}

// The P2 DateStrip: one pressed button per day, its count described, never part of its name.
export function DateStrip({ label, days, selected, onSelect }: DateStripProps) {
  const baseId = useId();
  return (
    <div className="week-strip" role="group" aria-label={label}>
      {days.map((day) => {
        const countId = `${baseId}-${day.date}`;
        return (
          <button
            key={day.date}
            type="button"
            className={day.date === selected ? "day-button selected" : "day-button"}
            aria-pressed={day.date === selected}
            aria-label={day.label}
            aria-describedby={day.count === null ? undefined : countId}
            onClick={() => {
              onSelect(day.date);
            }}
          >
            <span aria-hidden="true">
              {day.weekday} <strong>{day.dayOfMonth}</strong>
            </span>
            {day.count === null ? null : (
              <small id={countId} className="day-count">
                {day.count}
              </small>
            )}
          </button>
        );
      })}
    </div>
  );
}
