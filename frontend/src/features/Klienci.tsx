import { messages } from "../i18n/pl";

export default function Customers() {
  return (
    <div className="page-heading">
      <h1>{messages.customers}</h1>
      <p>{messages.lazyDestination}</p>
    </div>
  );
}
