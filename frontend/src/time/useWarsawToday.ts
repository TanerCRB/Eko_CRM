import { useEffect, useState } from "react";
import { msUntilNextDay, today, type CalendarDate } from "./warsaw";

// Re-read at least this often, so a device clock set forward or a sleep that delays the timer
// still rolls the day over within a minute.
const RECHECK_MS = 60_000;

// Today's Europe/Warsaw date, rolling over at Warsaw midnight without a reload or a request.
export function useWarsawToday(): CalendarDate {
  const [day, setDay] = useState(() => today());

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      timer = setTimeout(
        () => {
          setDay(today());
          arm();
        },
        Math.min(msUntilNextDay(), RECHECK_MS),
      );
    };
    arm();
    return () => {
      clearTimeout(timer);
    };
  }, []);

  return day;
}
