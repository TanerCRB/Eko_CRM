import { useState } from "react";
import { flushSync } from "react-dom";
import type { CustomerRecord } from "../api/customers";
import { navigateTo, useLocationPath } from "../routing/location";
import { CustomerDetail } from "./customers/CustomerDetail";
import { CustomerList } from "./customers/CustomerList";
import { NewCustomer } from "./customers/NewCustomer";
import { customerPath, CUSTOMERS_PATH, NEW_CUSTOMER_PATH } from "./customers/paths";

// The lazy customers destination: list, new customer, and one customer by its opaque id.
export default function Customers() {
  const path = useLocationPath();
  // In memory only, gone with this screen: the record the last create answered.
  const [created, setCreated] = useState<CustomerRecord | null>(null);

  if (path === CUSTOMERS_PATH || path === `${CUSTOMERS_PATH}/`) {
    return <CustomerList />;
  }
  if (path === NEW_CUSTOMER_PATH) {
    return (
      <NewCustomer
        onCreated={(customer) => {
          // Committed before the location changes, so the next screen already holds the answer.
          flushSync(() => {
            setCreated(customer);
          });
          navigateTo(customerPath(customer.id));
        }}
      />
    );
  }
  const id = path.slice(CUSTOMERS_PATH.length + 1);
  return <CustomerDetail key={id} id={id} created={created?.id === id ? created : null} />;
}
