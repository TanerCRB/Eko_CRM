// Fixed SPA locations of the customer screens; a customer's own is `customerPath(id)`.
export const CUSTOMERS_PATH = "/klienci";
export const NEW_CUSTOMER_PATH = "/klienci/nowy";

export function customerPath(id: string): string {
  return `${CUSTOMERS_PATH}/${id}`;
}
