import { Button } from "../../components/Button";
import { messages } from "../../i18n/pl";

// A failed read is said as such, never shown as an empty day or list.
export function LoadFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="form-alert">
      <p>{messages.visit.loadFailed}</p>
      <Button label={messages.visit.retry} onClick={onRetry} />
    </div>
  );
}
