import { messages } from "../i18n/pl";

export default function Klienci() {
  return (
    <div className="page-heading">
      <h1>{messages.customers}</h1>
      <p>{messages.lazyDestination}</p>
    </div>
  );
}
