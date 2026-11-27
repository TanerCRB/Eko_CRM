import { messages } from "../../i18n/pl";
import { followLink } from "../../routing/location";
import { PLAN_VISIT_PATH } from "./paths";

export function PlanLink() {
  return (
    <a
      className="button button-primary"
      href={PLAN_VISIT_PATH}
      onClick={(event) => {
        followLink(event, PLAN_VISIT_PATH);
      }}
    >
      {messages.visit.plan}
    </a>
  );
}
