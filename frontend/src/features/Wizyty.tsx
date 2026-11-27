import { useState } from "react";
import { flushSync } from "react-dom";
import type { Visit } from "../api/visits";
import { messages } from "../i18n/pl";
import { navigateTo, useLocationPath } from "../routing/location";
import { MyDay } from "./visits/MyDay";
import { MY_DAY_PATH, PLAN_VISIT_PATH, VISITS_PATH } from "./visits/paths";
import { PlanVisit } from "./visits/PlanVisit";
import { VisitSchedule } from "./visits/VisitSchedule";

// The lazy visits destination: My day, the Visits list and the plan form.
export default function Visits() {
  const path = useLocationPath();
  // In memory only, gone with this screen: the visit the last create answered.
  const [planned, setPlanned] = useState<Visit | null>(null);

  if (path === MY_DAY_PATH) {
    return <MyDay key={planned?.id ?? "none"} planned={planned} />;
  }
  if (path === VISITS_PATH || path === `${VISITS_PATH}/`) {
    return <VisitSchedule />;
  }
  if (path === PLAN_VISIT_PATH) {
    return (
      <PlanVisit
        onPlanned={(visit) => {
          // Committed before the location changes, so My day already holds the answer.
          flushSync(() => {
            setPlanned(visit);
          });
          navigateTo(MY_DAY_PATH);
        }}
      />
    );
  }
  return <p role="alert">{messages.visit.pageNotFound}</p>;
}
