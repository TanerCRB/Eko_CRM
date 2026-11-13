// Full page loads only: a login hop or a logout must leave no in-memory per-user state behind.
export const pageNavigation = {
  assign(url: string): void {
    window.location.assign(url);
  },
};

// The backend accepts only an SPA path here and falls back to "/" otherwise.
export function loginUrl(pathname: string, search: string): string {
  return `/api/auth/login?return_to=${encodeURIComponent(pathname + search)}`;
}

export function redirectToLogin(): void {
  pageNavigation.assign(loginUrl(window.location.pathname, window.location.search));
}
