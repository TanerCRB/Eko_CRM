import { useEffect, useRef } from "react";

// A screen's heading takes focus when the screen appears, so a route change is announced and the
// keyboard starts from the new content; the element needs tabIndex={-1}.
export function useMountFocus<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return ref;
}
